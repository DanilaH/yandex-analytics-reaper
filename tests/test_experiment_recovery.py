from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from yandex_analytics_reaper.experiment_recovery import (
    ExperimentRecoveryError,
    clear_derived_outputs,
    load_resume_preflight,
    prepare_temporary_artifact,
    publish_artifact_create_only,
)
from yandex_analytics_reaper.experiment_runtime import (
    AnalystExperimentRunState,
    ExperimentEventEmitter,
    write_run_state,
)


def _workdir(tmp_path: Path) -> tuple[Path, bytes, AnalystExperimentRunState]:
    workdir = tmp_path / "artifacts" / "work" / "demo" / "20260901T000000Z"
    manifest = (
        b'{"schema_version":1,"experiment_id":"demo",'
        b'"context":{"pages":1,"session_profile":"clean_anonymous",'
        b'"lang":"ru","device":"desktop","platform":"desktop_other"},'
        b'"families":[{"id":"f","queries":["q"]}]}'
    )
    (workdir / "input").mkdir(parents=True)
    (workdir / "input" / "manifest.json").write_bytes(manifest)
    state = AnalystExperimentRunState(
        experiment_id="demo",
        run_id="20260901T000000Z",
        started_at=datetime(2026, 9, 1, tzinfo=UTC),
        manifest_sha256=hashlib.sha256(manifest).hexdigest(),
    )
    write_run_state(workdir / "run-state.json", state)
    return workdir, manifest, state


def test_resume_preflight_requires_exact_path_and_manifest_identity(tmp_path: Path) -> None:
    workdir, manifest, state = _workdir(tmp_path)
    result = load_resume_preflight(tmp_path, workdir)
    assert result.state == state
    assert result.manifest_bytes == manifest
    assert result.artifact_path == (
        tmp_path / "artifacts" / "exports" / "demo" / "20260901T000000Z.zip"
    )

    (workdir / "input" / "manifest.json").write_bytes(manifest + b" ")
    with pytest.raises(ExperimentRecoveryError, match="SHA-256"):
        load_resume_preflight(tmp_path, workdir)


def test_clear_derived_outputs_preserves_evidence_and_operational_state(tmp_path: Path) -> None:
    workdir, _, _ = _workdir(tmp_path)
    for path in (workdir / "raw", workdir / "logs"):
        path.mkdir()
        (path / "keep.txt").write_text("keep", encoding="utf-8")
    (workdir / "market.sqlite3").write_bytes(b"db")
    (workdir / "reports").mkdir()
    (workdir / "reports" / "partial.json").write_text("partial", encoding="utf-8")
    (workdir / "csv").mkdir()
    (workdir / "csv" / "partial.csv").write_text("partial", encoding="utf-8")
    (workdir / "execution-summary.json").write_text("partial", encoding="utf-8")

    clear_derived_outputs(workdir)

    assert (workdir / "raw" / "keep.txt").read_text(encoding="utf-8") == "keep"
    assert (workdir / "logs" / "keep.txt").read_text(encoding="utf-8") == "keep"
    assert (workdir / "market.sqlite3").read_bytes() == b"db"
    assert list((workdir / "reports").iterdir()) == []
    assert not (workdir / "csv").exists()
    assert not (workdir / "execution-summary.json").exists()


def test_event_emitter_preserves_truncated_jsonl_tail_and_starts_new_line(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    events_path = logs / "events.jsonl"
    events_path.write_bytes(b'{"interrupted":')

    with ExperimentEventEmitter(
        tmp_path,
        experiment_id="demo",
        run_id="run",
        heartbeat_interval_seconds=0,
        output=lambda _: None,
    ) as events:
        events.emit("resume_started", stage="initialization")

    data = events_path.read_bytes()
    assert data.startswith(b'{"interrupted":\n')
    assert b'"event":"resume_started"' in data.splitlines()[-1]


def test_create_only_publication_never_overwrites_final(tmp_path: Path) -> None:
    final = tmp_path / "artifact.zip"
    temp = prepare_temporary_artifact(final)
    temp.write_bytes(b"verified")
    publish_artifact_create_only(temp, final)
    assert final.read_bytes() == b"verified"
    assert not temp.exists()

    temp = prepare_temporary_artifact(final)
    temp.write_bytes(b"new")
    with pytest.raises(ExperimentRecoveryError, match="will not be overwritten"):
        publish_artifact_create_only(temp, final)
    assert final.read_bytes() == b"verified"
