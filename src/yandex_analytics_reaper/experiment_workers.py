from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass

_MIN_QUERY_WORKERS = 1
_MAX_QUERY_WORKERS = 4
DEFAULT_QUERY_WORKERS = 4


@dataclass(frozen=True, slots=True)
class ExactQueryWorkItem:
    family_id: str
    query: str
    query_index: int
    query_total: int


@dataclass(frozen=True, slots=True)
class ExactQueryWorkResult:
    query_index: int
    run_id: str


def validate_query_workers(value: int) -> int:
    if not _MIN_QUERY_WORKERS <= value <= _MAX_QUERY_WORKERS:
        raise ValueError(
            f"query workers must be between {_MIN_QUERY_WORKERS} and {_MAX_QUERY_WORKERS}"
        )
    return value


def run_bounded_query_workers(
    items: Sequence[ExactQueryWorkItem],
    *,
    workers: int,
    collect: Callable[[ExactQueryWorkItem], ExactQueryWorkResult],
) -> tuple[ExactQueryWorkResult, ...]:
    """Run at most ``workers`` independent exact queries without pre-queuing the tail.

    Only the first bounded wave is submitted eagerly. A successful completion opens one
    new scheduling slot. Once any active query fails, no new query is submitted; already
    active siblings are allowed to reach a terminal state before the first failure is
    re-raised. Results are returned in manifest/query-index order, never completion order.
    """
    worker_count = validate_query_workers(workers)
    if not items:
        return ()

    pending = iter(items)
    active: dict[Future[ExactQueryWorkResult], ExactQueryWorkItem] = {}
    results: dict[int, ExactQueryWorkResult] = {}
    first_error: Exception | None = None

    with ThreadPoolExecutor(
        max_workers=worker_count,
        thread_name_prefix="query-worker",
    ) as executor:
        for _ in range(min(worker_count, len(items))):
            item = next(pending)
            active[executor.submit(collect, item)] = item

        while active:
            done, _ = wait(tuple(active), return_when=FIRST_COMPLETED)
            completed = sorted(done, key=lambda future: active[future].query_index)
            for future in completed:
                item = active.pop(future)
                try:
                    result = future.result()
                except Exception as exc:
                    if first_error is None:
                        first_error = exc
                    continue
                if result.query_index != item.query_index:
                    raise RuntimeError(
                        "query worker returned a result for a different query index"
                    )
                if result.query_index in results:
                    raise RuntimeError("query worker returned a duplicate query index")
                results[result.query_index] = result

            if first_error is not None:
                continue

            while len(active) < worker_count:
                try:
                    item = next(pending)
                except StopIteration:
                    break
                active[executor.submit(collect, item)] = item

    if first_error is not None:
        raise first_error

    expected_indices = [item.query_index for item in items]
    if set(results) != set(expected_indices):
        raise RuntimeError("query worker scheduler finished without all expected results")
    return tuple(results[index] for index in expected_indices)
