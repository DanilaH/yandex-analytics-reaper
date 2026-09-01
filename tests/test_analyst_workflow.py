from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from pydantic import ValidationError

import yandex_analytics_reaper.analyst_workflow as workflow
from yandex_analytics_reaper.experiment_cli import build_parser


def _manifest() -> workflow.AnalystExperimentManifest:
    return workflow.AnalystExperimentManifest.model_validate(
        {
            "schema_version": 1,
            "experiment_id": "curiosity-payoff-sweep-v1",
            "context": {
                "pages": 3,
                "session_profile": "clean_anonymous",
                "lang": "ru",
                "device": "desktop",
                "platform": "desktop_other",
            },
            "families": [
                {"id": "clean-restore", "queries": ["clean", "уборка"]},
                {"id": "break-reveal", "queries": ["break", "ломай"]},
            ],
        }
    )


def test_experiment_manifest_is_explicit_and_strict() -> None:
    manifest = _manifest()

    assert manifest.schema_version == 1
    assert manifest.experiment_id == "curiosity-payoff-sweep-v1"
    assert [family.id for family in manifest.families] == [
        "clean-restore",
        "break-reveal",
    ]
    assert manifest.families[0].queries == ("clean", "уборка")


@pytest.mark.parametrize(
    "experiment_id",
    ["Curiosity", "../escape", "has spaces", "ends-", "-starts"],
)
def test_experiment_id_must_be_human_safe_slug(experiment_id: str) -> None:
    payload = _manifest().model_dump()
    payload["experiment_id"] = experiment_id

    with pytest.raises(ValidationError):
        workflow.AnalystExperimentManifest.model_validate(payload)


def test_experiment_manifest_rejects_duplicate_family_ids() -> None:
    payload = _manifest().model_dump()
    payload["families"][1]["id"] = "clean-restore"

    with pytest.raises(ValidationError, match="family ids must be unique"):
        workflow.AnalystExperimentManifest.model_validate(payload)


def test_experiment_manifest_rejects_query_shared_between_families() -> None:
    payload = _manifest().model_dump()
    payload["families"][1]["queries"] = ("break", "clean")

    with pytest.raises(ValidationError, match="only one experiment family"):
        workflow.AnalystExperimentManifest.model_validate(payload)


def test_query_family_mapping_does_not_infer_secondary_semantics() -> None:
    family = workflow._query_family(
        _manifest().families[0],
        language="ru",
        created_at=datetime(2026, 8, 31, tzinfo=UTC),
    )

    assert family.family_id == "clean-restore"
    assert [member.query_text for member in family.members] == ["clean", "уборка"]
    assert [member.kind.value for member in family.members] == ["seed", "other"]


def test_experiment_cli_parses_one_high_level_run_command() -> None:
    args = build_parser().parse_args(["run", "curiosity-payoff-sweep-v1.json"])

    assert args.command == "run"
    assert args.manifest == "curiosity-payoff-sweep-v1.json"


def test_find_repository_root_uses_project_marker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "repo"
    nested = root / "inputs"
    nested.mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        '[project]\nname = "yandex-analytics-reaper"\n',
        encoding="utf-8",
    )
    manifest_path = nested / "experiment.json"
    monkeypatch.chdir(nested)

    assert workflow.find_repository_root(manifest_path) == root


def test_allocate_run_paths_never_overwrites_existing_run(tmp_path: Path) -> None:
    started = datetime(2026, 8, 31, 20, 34, 12, tzinfo=UTC)

    first_id, first_work, first_artifact = workflow._allocate_run_paths(
        tmp_path,
        "curiosity-payoff-sweep-v1",
        started,
    )
    first_artifact.parent.mkdir(parents=True, exist_ok=True)
    first_artifact.write_bytes(b"existing")
    second_id, second_work, second_artifact = workflow._allocate_run_paths(
        tmp_path,
        "curiosity-payoff-sweep-v1",
        started,
    )

    assert first_id == "20260831T203412Z"
    assert second_id == "20260831T203412Z-02"
    assert first_work.is_dir()
    assert second_work.is_dir()
    assert second_artifact != first_artifact


def test_artifact_manifest_package_and_reopen_verification(tmp_path: Path) -> None:
    workdir = tmp_path / "work"
    (workdir / "input").mkdir(parents=True)
    (workdir / "reports").mkdir()
    (workdir / "input" / "manifest.json").write_text(
        '{"schema_version":1}\n',
        encoding="utf-8",
    )
    (workdir / "reports" / "execution-timings.json").write_text(
        '{"ok":true}\n',
        encoding="utf-8",
    )

    artifact_manifest = workflow.build_artifact_manifest(
        workdir,
        experiment_id="curiosity-payoff-sweep-v1",
        run_id="20260831T203412Z",
    )
    (workdir / "artifact-manifest.json").write_text(
        artifact_manifest.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    artifact = tmp_path / "exports" / "run.zip"
    artifact.parent.mkdir()

    workflow.package_workdir(workdir, artifact)
    verified = workflow.verify_packaged_artifact(artifact)

    assert verified == artifact_manifest
    assert {item.path for item in verified.files} == {
        "input/manifest.json",
        "reports/execution-timings.json",
    }


def test_packaged_artifact_verifier_detects_payload_tampering(tmp_path: Path) -> None:
    workdir = tmp_path / "work"
    (workdir / "input").mkdir(parents=True)
    payload = workdir / "input" / "manifest.json"
    payload.write_text("original", encoding="utf-8")
    artifact_manifest = workflow.build_artifact_manifest(
        workdir,
        experiment_id="test-experiment",
        run_id="20260831T203412Z",
    )

    artifact = tmp_path / "tampered.zip"
    with ZipFile(artifact, mode="w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("input/manifest.json", "changed")
        archive.writestr(
            "artifact-manifest.json",
            artifact_manifest.model_dump_json(indent=2),
        )

    with pytest.raises(workflow.AnalystExperimentError, match="hash/size mismatch"):
        workflow.verify_packaged_artifact(artifact)


def test_yandex_app_id_and_batching_are_internal_deterministic_helpers() -> None:
    assert workflow._yandex_app_id("yandex_games:123") == 123
    assert list(workflow._batches((1, 2, 3, 4, 5), 2)) == [
        (1, 2),
        (3, 4),
        (5,),
    ]

    with pytest.raises(workflow.AnalystExperimentError):
        workflow._yandex_app_id("steam:123")


def test_existing_final_artifact_binds_manifest_payload_to_run_state(tmp_path: Path) -> None:
    workdir = tmp_path / "work"
    (workdir / "input").mkdir(parents=True)
    persisted_manifest = b'{"schema_version":1,"experiment_id":"demo"}'
    authoritative_manifest = persisted_manifest + b" "
    (workdir / "input" / "manifest.json").write_bytes(persisted_manifest)
    state = workflow.AnalystExperimentRunState(
        experiment_id="demo",
        run_id="20260901T000000Z",
        started_at=datetime(2026, 9, 1, tzinfo=UTC),
        manifest_sha256=workflow._sha256_bytes(authoritative_manifest),
    )
    digest = "0" * 64
    summary = workflow.AnalystExperimentExecutionSummary(
        workflow_version="analyst-experiment-v1.2",
        status="completed",
        experiment_id=state.experiment_id,
        run_id=state.run_id,
        started_at=state.started_at,
        completed_at=state.started_at,
        manifest_sha256=state.manifest_sha256,
        runtime=workflow.AnalystRuntimeProvenance(
            package_version="0.1.1", git_sha=None, python="3.12", platform="test"
        ),
        family_count=1,
        query_count=1,
        comparable_unique_listing_count=0,
        rich_requested_listing_count=0,
        rich_observed_listing_count=0,
        rich_missing_listing_ids=(),
        snapshot_content_hash=digest,
        market_export_content_hash=digest,
        market_features_content_hash=digest,
        final_invocation_mode="resume",
        final_invocation_started_at=state.started_at,
        final_invocation_workers=1,
        was_resumed=True,
        reused_query_count=1,
        collected_query_count=0,
        verifier_status="pass",
    )
    workflow._write_model(workdir / "execution-summary.json", summary)
    artifact_manifest = workflow.build_artifact_manifest(
        workdir, experiment_id=state.experiment_id, run_id=state.run_id
    )
    workflow._write_model(workdir / "artifact-manifest.json", artifact_manifest)
    artifact = tmp_path / "artifact.zip"
    workflow.package_workdir(workdir, artifact)

    with pytest.raises(workflow.AnalystExperimentError, match="identity"):
        workflow._result_from_existing_artifact(
            artifact,
            repository_root=tmp_path,
            state=state,
            invocation_elapsed_seconds=0.0,
        )


def _resume_fixture(
    tmp_path: Path,
) -> tuple[Path, workflow.AnalystExperimentManifest, workflow.AnalystExperimentRunState]:
    manifest = _manifest()
    run_id = "20260901T000000Z"
    workdir = tmp_path / "artifacts" / "work" / manifest.experiment_id / run_id
    manifest_bytes = manifest.model_dump_json().encode()
    (workdir / "input").mkdir(parents=True)
    (workdir / "input" / "manifest.json").write_bytes(manifest_bytes)
    state = workflow.AnalystExperimentRunState(
        experiment_id=manifest.experiment_id,
        run_id=run_id,
        started_at=datetime(2026, 9, 1, tzinfo=UTC),
        manifest_sha256=workflow._sha256_bytes(manifest_bytes),
    )
    workflow.write_run_state(workdir / "run-state.json", state)
    (workdir / "reports").mkdir()
    (workdir / "reports" / "stale.json").write_text("stale", encoding="utf-8")
    (workdir / "csv").mkdir()
    (workdir / "csv" / "stale.csv").write_text("stale", encoding="utf-8")
    return workdir, manifest, state


def test_resume_preserves_identity_and_cleans_workdir_only_after_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workdir, expected_manifest, state = _resume_fixture(tmp_path)
    observed: dict[str, object] = {}

    def fake_run_in_workdir(
        _self: object,
        manifest: workflow.AnalystExperimentManifest,
        **kwargs: object,
    ) -> workflow.AnalystExperimentResult:
        observed.update(kwargs)
        assert manifest == expected_manifest
        assert kwargs["started_at"] == state.started_at
        assert kwargs["run_id"] == state.run_id
        assert kwargs["manifest_sha256"] == state.manifest_sha256
        assert kwargs["invocation_mode"] == "resume"
        assert kwargs["allow_reuse"] is True
        assert (workdir / "reports").is_dir()
        assert list((workdir / "reports").iterdir()) == []
        assert not (workdir / "csv").exists()
        return workflow.AnalystExperimentResult(
            experiment_id=state.experiment_id,
            run_id=state.run_id,
            artifact_path=f"artifacts/exports/{state.experiment_id}/{state.run_id}.zip",
            artifact_sha256="0" * 64,
            artifact_manifest_sha256="1" * 64,
            verifier="PASS",
            family_count=len(manifest.families),
            query_count=sum(len(item.queries) for item in manifest.families),
            comparable_unique_listing_count=0,
            rich_requested_listing_count=0,
            rich_observed_listing_count=0,
            invocation_elapsed_seconds=0.0,
        )

    monkeypatch.setattr(
        workflow.AnalystExperimentRunner,
        "_run_in_workdir",
        fake_run_in_workdir,
    )
    runner = workflow.AnalystExperimentRunner(
        repository_root=tmp_path,
        output=lambda _: None,
        heartbeat_interval_seconds=0,
    )

    result = runner.resume(workdir, query_workers=3)

    assert observed
    assert observed["query_workers"] == 3
    assert result.run_id == state.run_id
    assert not workdir.exists()


def test_resume_failure_preserves_workdir_and_repeatable_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workdir, _, state = _resume_fixture(tmp_path)

    def fail_run_in_workdir(
        _self: object,
        _manifest_value: workflow.AnalystExperimentManifest,
        **_kwargs: object,
    ) -> workflow.AnalystExperimentResult:
        raise RuntimeError("boom")

    monkeypatch.setattr(
        workflow.AnalystExperimentRunner,
        "_run_in_workdir",
        fail_run_in_workdir,
    )
    runner = workflow.AnalystExperimentRunner(
        repository_root=tmp_path,
        output=lambda _: None,
        heartbeat_interval_seconds=0,
    )

    with pytest.raises(workflow.AnalystExperimentError) as raised:
        runner.resume(workdir)

    expected_target = (
        f"yandex-reaper-experiment resume artifacts/work/{state.experiment_id}/{state.run_id}"
    )
    assert expected_target in str(raised.value)
    assert workdir.is_dir()
    assert (workdir / "run-state.json").is_file()
    assert (workdir / "input" / "manifest.json").is_file()
    assert (workdir / "logs" / "events.jsonl").is_file()
