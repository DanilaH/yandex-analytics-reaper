from __future__ import annotations

import threading
import time

import pytest

from yandex_analytics_reaper.experiment_workers import (
    ExactQueryWorkItem,
    ExactQueryWorkResult,
    run_bounded_query_workers,
    validate_query_workers,
)


def _items(count: int) -> tuple[ExactQueryWorkItem, ...]:
    return tuple(
        ExactQueryWorkItem(
            family_id="family",
            query=f"q{index}",
            query_index=index,
            query_total=count,
        )
        for index in range(1, count + 1)
    )


def test_scheduler_returns_manifest_order_independent_of_completion_order() -> None:
    items = _items(4)

    def collect(item: ExactQueryWorkItem) -> ExactQueryWorkResult:
        time.sleep((5 - item.query_index) * 0.005)
        return ExactQueryWorkResult(query_index=item.query_index, run_id=f"run-{item.query_index}")

    results = run_bounded_query_workers(items, workers=4, collect=collect)

    assert [item.query_index for item in results] == [1, 2, 3, 4]
    assert [item.run_id for item in results] == ["run-1", "run-2", "run-3", "run-4"]


def test_scheduler_never_exceeds_worker_bound() -> None:
    items = _items(8)
    lock = threading.Lock()
    active = 0
    maximum = 0

    def collect(item: ExactQueryWorkItem) -> ExactQueryWorkResult:
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
        try:
            time.sleep(0.01)
            return ExactQueryWorkResult(
                query_index=item.query_index, run_id=f"run-{item.query_index}"
            )
        finally:
            with lock:
                active -= 1

    run_bounded_query_workers(items, workers=3, collect=collect)

    assert 1 < maximum <= 3


def test_first_worker_failure_stops_new_scheduling_but_allows_active_sibling_to_finish() -> None:
    items = _items(4)
    lock = threading.Lock()
    started: list[int] = []
    sibling_finished = threading.Event()

    def collect(item: ExactQueryWorkItem) -> ExactQueryWorkResult:
        with lock:
            started.append(item.query_index)
        if item.query_index == 1:
            raise RuntimeError("boom")
        if item.query_index == 2:
            time.sleep(0.02)
            sibling_finished.set()
        return ExactQueryWorkResult(query_index=item.query_index, run_id=f"run-{item.query_index}")

    with pytest.raises(RuntimeError, match="boom"):
        run_bounded_query_workers(items, workers=2, collect=collect)

    assert sibling_finished.is_set()
    assert set(started) == {1, 2}


@pytest.mark.parametrize("workers", [0, 5])
def test_worker_count_is_strictly_bounded(workers: int) -> None:
    with pytest.raises(ValueError, match="between 1 and 4"):
        validate_query_workers(workers)


def test_one_and_four_workers_have_identical_semantic_results() -> None:
    items = _items(6)

    def collect(item: ExactQueryWorkItem) -> ExactQueryWorkResult:
        if threading.current_thread().name.startswith("query-worker"):
            time.sleep((item.query_index % 3) * 0.002)
        return ExactQueryWorkResult(
            query_index=item.query_index,
            run_id=f"run-{item.query_index}",
        )

    serial = run_bounded_query_workers(items, workers=1, collect=collect)
    parallel = run_bounded_query_workers(items, workers=4, collect=collect)

    assert parallel == serial
