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
