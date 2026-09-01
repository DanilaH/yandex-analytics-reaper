from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZipFile

import pytest

import yandex_analytics_reaper.analyst_workflow as workflow
from yandex_analytics_reaper.domain import ProbeContext
from yandex_analytics_reaper.ingestion import (
    ProbePersistenceGate,
    YandexNormalizationPersistence,
    YandexPaginatedProbeRunner,
    YandexRichMetadataCollector,
)
from yandex_analytics_reaper.schema_drift import SQLiteSchemaDriftRegistry
from yandex_analytics_reaper.sources.capabilities import CollectedResponse
from yandex_analytics_reaper.storage import FilesystemRawSnapshotStore, SQLiteProbeRunStore


class FakeSearchClient:
    source_id = "yandex_public"

    def collect_search(
        self,
        query: str,
        context: ProbeContext,
        *,
        page_id: str | None = None,
        rtx_reqid: str | None = None,
    ) -> CollectedResponse:
        del page_id, rtx_reqid
        app_ids = {
            "clean": [10, 20],
            "break": [20, 30],
        }[query]
        body = json.dumps(
            {
                "feed": [{"items": [{"appID": app_id} for app_id in app_ids]}],
                "totalGamesCount": 12 if query == "clean" else 9,
                "pageInfo": {
                    "hasNextPage": False,
                    "nextPageId": None,
                    "rtxReqId": None,
                },
            }
        ).encode()
        return CollectedResponse(
            source_id=self.source_id,
            request_key="catalogue.search",
            method="GET",
            url="https://yandex.ru/games/api/catalogue/v2/search",
            status_code=200,
            headers={"content-type": "application/json"},
            body=body,
            retrieved_at=datetime.now(UTC),
            request_context={
                "probe_context": context.model_dump(mode="json"),
                "query": query,
                "params": {"query": query, "lang": context.language},
            },
        )


class FakeGamesClient:
    source_id = "yandex_public"

    def collect_games(self, app_ids: Sequence[int]) -> CollectedResponse:
        ids = tuple(app_ids)
        body = json.dumps(
            {
                "games": [
                    {
                        "appID": app_id,
                        "title": f"Game {app_id}",
                        "developer": {"id": 1000 + app_id, "name": f"Dev {app_id}"},
                        "gqRating": 70 + app_id % 10,
                        "rating": 4.0 + (app_id % 3) / 10,
                        "ratingCount": 100 + app_id,
                        "firstPublished": 1_750_000_000 + app_id,
                    }
                    for app_id in ids
                ]
            }
        ).encode()
        return CollectedResponse(
            source_id=self.source_id,
            request_key="catalogue.get_games",
            method="POST",
            url="https://yandex.ru/games/api/catalogue/v2/get_games",
            status_code=200,
            headers={"content-type": "application/json"},
            body=body,
            retrieved_at=datetime.now(UTC),
            request_context={"app_ids": list(ids), "format": "long"},
        )


def _small_manifest() -> workflow.AnalystExperimentManifest:
    return workflow.AnalystExperimentManifest.model_validate(
        {
            "schema_version": 1,
            "experiment_id": "runner-e2e",
            "context": {
                "pages": 1,
                "session_profile": "clean_anonymous",
                "lang": "ru",
                "device": "desktop",
                "platform": "desktop_other",
            },
            "families": [
                {"id": "clean-restore", "queries": ["clean"]},
                {"id": "break-reveal", "queries": ["break"]},
            ],
        }
    )


def test_runner_executes_full_local_evidence_chain_and_cleans_workdir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _small_manifest()
    manifest_bytes = manifest.model_dump_json(indent=2).encode()
    runner = workflow.AnalystExperimentRunner(repository_root=tmp_path, sleeper=lambda _: None)

    def collect_search(
        query: str,
        *,
        context: ProbeContext,
        page_limit: int,
        raw_store: FilesystemRawSnapshotStore,
        probe_store: SQLiteProbeRunStore,
        schema_registry: SQLiteSchemaDriftRegistry,
        session_manager: object,
        persistence_gate: ProbePersistenceGate,
        family_id: str,
        query_index: int,
        query_total: int,
        worker: str,
        events: object,
        timings: object,
    ):
        del session_manager, family_id, query_index, query_total, worker, events, timings
        effective_context = context.model_copy(update={"profile_age_days": 0})
        return YandexPaginatedProbeRunner(
            client=FakeSearchClient(),
            raw_store=raw_store,
            probe_store=probe_store,
            schema_registry=schema_registry,
            persistence_gate=persistence_gate,
        ).run_search(query, effective_context, page_limit=page_limit)

    def collect_rich_batch(
        app_ids: Sequence[int],
        *,
        raw_store: FilesystemRawSnapshotStore,
        schema_registry: SQLiteSchemaDriftRegistry,
        persistence: YandexNormalizationPersistence,
        batch_index: int,
        batch_total: int,
        events: object,
        timings: object,
    ):
        del batch_index, batch_total, events, timings
        return YandexRichMetadataCollector(
            client=FakeGamesClient(),
            raw_store=raw_store,
            schema_registry=schema_registry,
            persistence=persistence,
        ).collect(app_ids)

    monkeypatch.setattr(runner, "_collect_search", collect_search)
    monkeypatch.setattr(runner, "_collect_rich_batch", collect_rich_batch)

    result = runner.run(manifest, manifest_bytes=manifest_bytes)

    artifact_path = tmp_path / result.artifact_path
    assert artifact_path.is_file()
    assert result.family_count == 2
    assert result.query_count == 2
    assert result.comparable_unique_listing_count == 3
    assert result.rich_requested_listing_count == 3
    assert result.rich_observed_listing_count == 3
    assert result.invocation_elapsed_seconds >= 0.0
    assert not (
        tmp_path / "artifacts" / "work" / result.experiment_id / result.run_id
    ).exists()

    packaged_manifest = workflow.verify_packaged_artifact(
        artifact_path,
        expected_experiment_id=result.experiment_id,
        expected_run_id=result.run_id,
    )
    assert packaged_manifest.experiment_id == result.experiment_id
    assert packaged_manifest.run_id == result.run_id

    with ZipFile(artifact_path) as archive:
        names = set(archive.namelist())
        assert {
            "input/manifest.json",
            "market.sqlite3",
            "reports/analyst-snapshot.json",
            "reports/market-export.json",
            "reports/market-features.json",
            "reports/family-coherence.json",
            "reports/verification.json",
            "reports/execution-timings.json",
            "execution-summary.json",
            "artifact-manifest.json",
        } <= names
        assert archive.read("input/manifest.json") == manifest_bytes
        assert "run-state.json" not in names
        assert "run.lock" not in names
        assert not any(name.startswith("logs/") for name in names)
        assert not any(name.startswith("sessions/") for name in names)


def test_package_workdir_removes_partial_zip_when_write_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workdir = tmp_path / "work"
    (workdir / "input").mkdir(parents=True)
    (workdir / "input" / "manifest.json").write_text("payload", encoding="utf-8")
    artifact_path = tmp_path / "artifact.zip"

    def fail_write(
        self: ZipFile,
        filename: object,
        arcname: object = None,
        **kwargs: object,
    ) -> None:
        del self, filename, arcname, kwargs
        raise OSError("synthetic package failure")

    monkeypatch.setattr(workflow.ZipFile, "write", fail_write)

    with pytest.raises(OSError, match="synthetic package failure"):
        workflow.package_workdir(workdir, artifact_path)

    assert not artifact_path.exists()


def test_finalizer_rejects_wrong_packaged_identity_and_removes_zip(tmp_path: Path) -> None:
    workdir = tmp_path / "work"
    (workdir / "input").mkdir(parents=True)
    (workdir / "input" / "manifest.json").write_text("payload", encoding="utf-8")
    expected_manifest = workflow.build_artifact_manifest(
        workdir,
        experiment_id="expected-experiment",
        run_id="20260831T203412Z",
    )
    wrong_manifest = expected_manifest.model_copy(update={"experiment_id": "other-experiment"})
    (workdir / "artifact-manifest.json").write_text(
        wrong_manifest.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    artifact_path = tmp_path / "artifact.zip"

    with pytest.raises(workflow.AnalystExperimentError, match="experiment_id"):
        workflow.finalize_verified_artifact(
            workdir,
            artifact_path,
            expected_manifest=expected_manifest,
        )

    assert not artifact_path.exists()
