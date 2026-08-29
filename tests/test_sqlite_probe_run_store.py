from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from yandex_analytics_reaper.domain import (
    ProbeContext,
    ProbeKind,
    ProbePage,
    ProbeRunStatus,
)
from yandex_analytics_reaper.storage import SQLiteProbeRunStore


def _start(
    store: SQLiteProbeRunStore,
    *,
    kind: ProbeKind = ProbeKind.RECOMMENDATION_FEED,
    page_limit: int = 3,
    query: str | None = None,
    started_at: datetime | None = None,
) -> tuple[str, datetime]:
    started = started_at or datetime(2026, 8, 29, 9, 0, tzinfo=UTC)
    run = store.create_run(
        source_id="yandex_public",
        request_key=("catalogue.search" if kind is ProbeKind.SEARCH else "catalogue.feed"),
        kind=kind,
        context=ProbeContext(language="ru", device_type="desktop"),
        requested_page_limit=page_limit,
        started_at=started,
        query_text=query,
    )
    return run.id, started


def _page(
    run_id: str,
    index: int,
    retrieved_at: datetime,
    *,
    has_next: bool = True,
    raw_id: str | None = None,
) -> ProbePage:
    return ProbePage(
        run_id=run_id,
        page_index=index,
        raw_snapshot_id=raw_id or f"raw-{run_id}-{index}",
        retrieved_at=retrieved_at,
        request_page_id=(None if index == 0 else f"page-{index}"),
        request_rtx_reqid=(None if index == 0 else f"req-{index}"),
        response_next_page_id=(f"page-{index + 1}" if has_next else None),
        response_rtx_reqid=(f"req-{index + 1}" if has_next else None),
        has_next_page=has_next,
    )


def test_store_round_trips_context_run_and_ordered_pages(tmp_path: Path) -> None:
    store = SQLiteProbeRunStore(tmp_path / "market.sqlite3")
    run_id, started = _start(store)
    first = _page(run_id, 0, started + timedelta(seconds=1))
    second = _page(run_id, 1, started + timedelta(seconds=2), has_next=False)

    store.append_page(first)
    store.append_page(second)
    finished = store.finish_run(
        run_id,
        status=ProbeRunStatus.COMPLETED,
        completed_at=started + timedelta(seconds=3),
    )
    record = store.get_run(run_id)

    assert record is not None
    assert record.run == finished
    assert record.run.status is ProbeRunStatus.COMPLETED
    assert record.context == ProbeContext(language="ru", device_type="desktop")
    assert record.pages == (first, second)


def test_same_context_is_deduplicated_but_runs_remain_distinct(tmp_path: Path) -> None:
    store = SQLiteProbeRunStore(tmp_path / "market.sqlite3")
    first_id, _ = _start(store, page_limit=1)
    second_id, _ = _start(store, page_limit=1)

    first = store.get_run(first_id)
    second = store.get_run(second_id)
    assert first is not None and second is not None
    assert first.run.id != second.run.id
    assert first.run.context_id == second.run.context_id
    assert first.context == second.context


def test_exact_page_retry_is_idempotent_but_conflict_is_rejected(tmp_path: Path) -> None:
    store = SQLiteProbeRunStore(tmp_path / "market.sqlite3")
    run_id, started = _start(store)
    page = _page(run_id, 0, started + timedelta(seconds=1))

    assert store.append_page(page) == page
    assert store.append_page(page) == page

    with pytest.raises(ValueError, match="conflicting probe page"):
        store.append_page(page.model_copy(update={"raw_snapshot_id": "different"}))


def test_pages_must_be_contiguous_and_respect_limit(tmp_path: Path) -> None:
    store = SQLiteProbeRunStore(tmp_path / "market.sqlite3")
    run_id, started = _start(store, page_limit=1)

    with pytest.raises(ValueError, match="expected index 0"):
        store.append_page(_page(run_id, 1, started + timedelta(seconds=1)))

    store.append_page(_page(run_id, 0, started + timedelta(seconds=1)))
    with pytest.raises(ValueError, match="requested_page_limit"):
        store.append_page(_page(run_id, 1, started + timedelta(seconds=2)))


def test_first_page_rejects_pagination_request_tokens(tmp_path: Path) -> None:
    store = SQLiteProbeRunStore(tmp_path / "market.sqlite3")
    run_id, started = _start(store)
    page = _page(run_id, 0, started + timedelta(seconds=1)).model_copy(
        update={"request_page_id": "unexpected"}
    )

    with pytest.raises(ValueError, match="first probe page"):
        store.append_page(page)


def test_next_page_must_continue_previous_cursor_and_rtx_token(tmp_path: Path) -> None:
    store = SQLiteProbeRunStore(tmp_path / "market.sqlite3")
    run_id, started = _start(store)
    store.append_page(_page(run_id, 0, started + timedelta(seconds=1)))

    wrong_cursor = _page(run_id, 1, started + timedelta(seconds=2)).model_copy(
        update={"request_page_id": "wrong-page"}
    )
    with pytest.raises(ValueError, match="page_id does not continue"):
        store.append_page(wrong_cursor)

    wrong_rtx = _page(run_id, 1, started + timedelta(seconds=2)).model_copy(
        update={"request_rtx_reqid": "wrong-req"}
    )
    with pytest.raises(ValueError, match="rtx_reqid does not continue"):
        store.append_page(wrong_rtx)


def test_next_page_rejects_missing_previous_continuation_tokens(tmp_path: Path) -> None:
    store = SQLiteProbeRunStore(tmp_path / "market.sqlite3")
    run_id, started = _start(store)
    first = _page(run_id, 0, started + timedelta(seconds=1)).model_copy(
        update={"response_next_page_id": None}
    )
    second = _page(run_id, 1, started + timedelta(seconds=2)).model_copy(
        update={"request_page_id": None}
    )

    store.append_page(first)
    with pytest.raises(ValueError, match="omitted required continuation tokens"):
        store.append_page(second)


def test_cannot_append_after_source_exhaustion_or_with_backwards_time(tmp_path: Path) -> None:
    store = SQLiteProbeRunStore(tmp_path / "market.sqlite3")
    exhausted_id, exhausted_started = _start(store)
    store.append_page(
        _page(exhausted_id, 0, exhausted_started + timedelta(seconds=2), has_next=False)
    )
    with pytest.raises(ValueError, match="has_next_page=false"):
        store.append_page(_page(exhausted_id, 1, exhausted_started + timedelta(seconds=3)))

    timed_id, timed_started = _start(store)
    store.append_page(_page(timed_id, 0, timed_started + timedelta(seconds=2)))
    with pytest.raises(ValueError, match="cannot move backwards"):
        store.append_page(_page(timed_id, 1, timed_started + timedelta(seconds=1)))


def test_one_raw_snapshot_cannot_belong_to_two_probe_runs(tmp_path: Path) -> None:
    store = SQLiteProbeRunStore(tmp_path / "market.sqlite3")
    first_id, first_started = _start(store, page_limit=1)
    second_id, second_started = _start(store, page_limit=1)
    raw_id = "shared-raw"

    store.append_page(
        _page(first_id, 0, first_started + timedelta(seconds=1), raw_id=raw_id)
    )
    with pytest.raises(ValueError, match="already assigned"):
        store.append_page(
            _page(second_id, 0, second_started + timedelta(seconds=1), raw_id=raw_id)
        )


def test_completed_requires_requested_limit_or_source_exhaustion(tmp_path: Path) -> None:
    store = SQLiteProbeRunStore(tmp_path / "market.sqlite3")
    run_id, started = _start(store, page_limit=3)
    store.append_page(_page(run_id, 0, started + timedelta(seconds=1), has_next=True))

    with pytest.raises(ValueError, match="requested_page_limit or source exhaustion"):
        store.finish_run(
            run_id,
            status=ProbeRunStatus.COMPLETED,
            completed_at=started + timedelta(seconds=2),
        )

    partial = store.finish_run(
        run_id,
        status=ProbeRunStatus.PARTIAL,
        completed_at=started + timedelta(seconds=2),
        error="pagination stopped",
    )
    assert partial.status is ProbeRunStatus.PARTIAL


def test_failed_requires_zero_pages_and_partial_requires_pages(tmp_path: Path) -> None:
    store = SQLiteProbeRunStore(tmp_path / "market.sqlite3")
    failed_id, started = _start(store, page_limit=2)
    failed = store.finish_run(
        failed_id,
        status=ProbeRunStatus.FAILED,
        completed_at=started + timedelta(seconds=1),
        error="request failed",
    )
    assert failed.status is ProbeRunStatus.FAILED

    partial_id, partial_started = _start(store, page_limit=2)
    with pytest.raises(ValueError, match="partial probe run must contain"):
        store.finish_run(
            partial_id,
            status=ProbeRunStatus.PARTIAL,
            completed_at=partial_started + timedelta(seconds=1),
            error="nothing collected",
        )


def test_terminal_run_rejects_new_pages_and_conflicting_refinish(tmp_path: Path) -> None:
    store = SQLiteProbeRunStore(tmp_path / "market.sqlite3")
    run_id, started = _start(store, page_limit=1)
    page = _page(run_id, 0, started + timedelta(seconds=1))
    store.append_page(page)
    completed_at = started + timedelta(seconds=2)
    store.finish_run(
        run_id,
        status=ProbeRunStatus.COMPLETED,
        completed_at=completed_at,
    )

    with pytest.raises(ValueError, match="terminal"):
        store.append_page(_page(run_id, 1, started + timedelta(seconds=3)))

    same = store.finish_run(
        run_id,
        status=ProbeRunStatus.COMPLETED,
        completed_at=completed_at,
    )
    assert same.status is ProbeRunStatus.COMPLETED

    with pytest.raises(ValueError, match="different state"):
        store.finish_run(
            run_id,
            status=ProbeRunStatus.PARTIAL,
            completed_at=completed_at,
            error="changed",
        )


def test_search_run_requires_query_and_feed_rejects_query(tmp_path: Path) -> None:
    store = SQLiteProbeRunStore(tmp_path / "market.sqlite3")
    with pytest.raises(ValueError, match="requires query_text"):
        _start(store, kind=ProbeKind.SEARCH, query=None)
    with pytest.raises(ValueError, match="cannot carry query_text"):
        _start(store, kind=ProbeKind.RECOMMENDATION_FEED, query="merge")


def test_page_and_finish_timestamps_cannot_precede_run_or_last_page(tmp_path: Path) -> None:
    store = SQLiteProbeRunStore(tmp_path / "market.sqlite3")
    run_id, started = _start(store, page_limit=1)

    with pytest.raises(ValueError, match="before run start"):
        store.append_page(_page(run_id, 0, started - timedelta(seconds=1)))

    store.append_page(_page(run_id, 0, started + timedelta(seconds=2)))
    with pytest.raises(ValueError, match="earlier than the last page"):
        store.finish_run(
            run_id,
            status=ProbeRunStatus.COMPLETED,
            completed_at=started + timedelta(seconds=1),
        )
