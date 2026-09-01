from __future__ import annotations

from pathlib import Path

import httpx
import pytest

import yandex_analytics_reaper.analyst_workflow as workflow


class _FakeClient:
    def __init__(self, **kwargs: object) -> None:
        del kwargs

    def __enter__(self) -> _FakeClient:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        del exc_type, exc, tb


class _TransportFailingCollector:
    def __init__(self, **kwargs: object) -> None:
        del kwargs

    def collect(self, app_ids: object) -> object:
        del app_ids
        raise httpx.ConnectError("synthetic transport failure")


class _SemanticFailingCollector:
    def __init__(self, **kwargs: object) -> None:
        del kwargs

    def collect(self, app_ids: object) -> object:
        del app_ids
        raise ValueError("synthetic semantic failure")


class _Events:
    def __init__(self) -> None:
        self.records: list[tuple[str, dict[str, object]]] = []

    def emit(self, event: str, *, stage: str, **context: object) -> None:
        self.records.append((event, {"stage": stage, **context}))


class _Timings:
    def __init__(self) -> None:
        self.retries: list[dict[str, object]] = []

    def record_retry(self, **context: object) -> None:
        self.retries.append(context)

    def record_rich_batch(self, **context: object) -> None:
        raise AssertionError(f"unexpected successful batch timing: {context}")


def _call_failing_batch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    collector: type[object],
) -> tuple[_Events, _Timings]:
    monkeypatch.setattr(workflow, "YandexPublicClient", _FakeClient)
    monkeypatch.setattr(workflow, "YandexRichMetadataCollector", collector)
    events = _Events()
    timings = _Timings()
    runner = workflow.AnalystExperimentRunner(
        repository_root=tmp_path,
        sleeper=lambda _: None,
    )

    with pytest.raises((httpx.ConnectError, ValueError)):
        runner._collect_rich_batch(
            (10, 20),
            raw_store=object(),
            schema_registry=object(),
            persistence=object(),
            batch_index=1,
            batch_total=1,
            events=events,
            timings=timings,
        )
    return events, timings


def test_rich_terminal_transport_failure_reports_final_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events, timings = _call_failing_batch(
        tmp_path,
        monkeypatch,
        _TransportFailingCollector,
    )

    assert [item[0] for item in events.records] == [
        "rich_batch_started",
        "rich_batch_retry",
        "rich_batch_retry",
        "rich_batch_failed",
    ]
    failure = events.records[-1][1]
    assert failure["attempt"] == 3
    assert failure["max_attempts"] == 3
    assert len(timings.retries) == 2


def test_rich_semantic_failure_reports_first_attempt_without_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events, timings = _call_failing_batch(
        tmp_path,
        monkeypatch,
        _SemanticFailingCollector,
    )

    assert [item[0] for item in events.records] == [
        "rich_batch_started",
        "rich_batch_failed",
    ]
    failure = events.records[-1][1]
    assert failure["attempt"] == 1
    assert failure["max_attempts"] == 3
    assert timings.retries == []
