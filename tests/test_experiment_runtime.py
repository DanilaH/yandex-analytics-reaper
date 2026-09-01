from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from yandex_analytics_reaper.experiment_runtime import (
    AnalystExperimentRunState,
    ExperimentEventEmitter,
    ExperimentRuntimeError,
    ExperimentTimingRecorder,
    WorkdirLock,
    write_run_state,
)


def test_run_state_round_trips_as_immutable_identity(tmp_path: Path) -> None:
    state = AnalystExperimentRunState(
        experiment_id="runner-e2e",
        run_id="20260901T010203Z",
        started_at=datetime(2026, 9, 1, 1, 2, 3, tzinfo=UTC),
        manifest_sha256="a" * 64,
    )
    path = tmp_path / "run-state.json"

    write_run_state(path, state)

    loaded = AnalystExperimentRunState.model_validate_json(path.read_bytes())
    assert loaded == state
    assert not path.with_name("run-state.json.tmp").exists()


def test_workdir_lock_rejects_second_live_owner_and_can_be_reacquired(tmp_path: Path) -> None:
    path = tmp_path / "run.lock"
    first = WorkdirLock(path).acquire()
    try:
        with pytest.raises(ExperimentRuntimeError, match="locked"):
            WorkdirLock(path).acquire()
    finally:
        first.release()

    second = WorkdirLock(path).acquire()
    second.release()


def test_event_emitter_writes_coherent_jsonl_and_human_log(tmp_path: Path) -> None:
    output: list[str] = []
    emitter = ExperimentEventEmitter(
        tmp_path,
        experiment_id="runner-e2e",
        run_id="20260901T010203Z",
        output=output.append,
        heartbeat_interval_seconds=0,
        started_monotonic=10.0,
        monotonic=lambda: 12.5,
        wall_clock=lambda: datetime(2026, 9, 1, 1, 2, 3, tzinfo=UTC),
    )
    try:
        emitter.emit(
            "query_started",
            stage="search_collection",
            family_id="clean",
            query="clean",
            query_index=1,
            query_total=2,
        )
    finally:
        emitter.close()

    event_line = (tmp_path / "logs" / "events.jsonl").read_text(encoding="utf-8").strip()
    payload = json.loads(event_line)
    assert payload["experiment_id"] == "runner-e2e"
    assert payload["run_id"] == "20260901T010203Z"
    assert payload["event"] == "query_started"
    assert payload["query"] == "clean"
    assert payload["elapsed_seconds"] == 2.5
    human = (tmp_path / "logs" / "run.log").read_text(encoding="utf-8")
    assert "query_started" in human
    assert "query=clean" in human
    assert output and output[0] in human


def test_heartbeat_can_be_exercised_with_fake_monotonic_clock(tmp_path: Path) -> None:
    now = [100.0]
    emitter = ExperimentEventEmitter(
        tmp_path,
        experiment_id="runner-e2e",
        run_id="20260901T010203Z",
        output=lambda _: None,
        heartbeat_interval_seconds=15.0,
        started_monotonic=100.0,
        monotonic=lambda: now[0],
    )
    try:
        emitter.emit("stage_started", stage="search_collection")
        now[0] = 114.9
        assert emitter.emit_heartbeat_if_due() is False
        now[0] = 115.0
        assert emitter.emit_heartbeat_if_due() is True
        now[0] = 129.9
        assert emitter.emit_heartbeat_if_due() is False
    finally:
        emitter.close()

    events = [
        json.loads(line)
        for line in (tmp_path / "logs" / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [item["event"] for item in events] == ["stage_started", "heartbeat"]
    assert events[-1]["stage"] == "search_collection"


def test_timing_recorder_preserves_query_order_and_nonnegative_values() -> None:
    recorder = ExperimentTimingRecorder(monotonic=lambda: 0.0)
    recorder.record_stage("search_collection", -1.0)
    recorder.record_query(
        family_id="b",
        query="second",
        query_index=2,
        query_total=2,
        action="collected",
        elapsed_seconds=2.0,
    )
    recorder.record_query(
        family_id="a",
        query="first",
        query_index=1,
        query_total=2,
        action="collected",
        elapsed_seconds=-3.0,
    )
    recorder.record_page(query="first", page=1, page_limit=3, elapsed_seconds=-2.0)
    recorder.record_retry(unit="query", attempt=1, delay_seconds=1.0, query="first")
    recorder.record_rich_batch(
        batch_index=1,
        batch_total=1,
        listing_count=2,
        elapsed_seconds=-1.0,
    )

    report = recorder.report(
        experiment_id="runner-e2e",
        run_id="20260901T010203Z",
        invocation_mode="run",
        query_workers=1,
    )

    assert report.stages[0].elapsed_seconds == 0.0
    assert [item.query for item in report.queries] == ["first", "second"]
    assert report.queries[0].elapsed_seconds == 0.0
    assert report.pages[0].elapsed_seconds == 0.0
    assert report.rich_batches[0].elapsed_seconds == 0.0
