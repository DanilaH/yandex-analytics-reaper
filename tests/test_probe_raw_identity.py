from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from yandex_analytics_reaper.domain import ProbeContext, ProbeKind, ProbePage
from yandex_analytics_reaper.storage import SQLiteProbeRunStore


def test_probe_raw_snapshot_identity_is_scoped_by_source(tmp_path: Path) -> None:
    store = SQLiteProbeRunStore(tmp_path / "market.sqlite3")
    started_at = datetime(2026, 8, 29, 9, 0, tzinfo=UTC)
    context = ProbeContext()
    first = store.create_run(
        source_id="source_a",
        request_key="catalogue.feed",
        kind=ProbeKind.RECOMMENDATION_FEED,
        context=context,
        requested_page_limit=1,
        started_at=started_at,
    )
    second = store.create_run(
        source_id="source_b",
        request_key="catalogue.feed",
        kind=ProbeKind.RECOMMENDATION_FEED,
        context=context,
        requested_page_limit=1,
        started_at=started_at,
    )
    third = store.create_run(
        source_id="source_a",
        request_key="catalogue.feed",
        kind=ProbeKind.RECOMMENDATION_FEED,
        context=context,
        requested_page_limit=1,
        started_at=started_at,
    )

    def page(run_id: str) -> ProbePage:
        return ProbePage(
            run_id=run_id,
            page_index=0,
            raw_snapshot_id="same-snapshot-id",
            retrieved_at=started_at + timedelta(seconds=1),
            has_next_page=False,
        )

    store.append_page(page(first.id))
    store.append_page(page(second.id))

    with pytest.raises(ValueError, match="already assigned"):
        store.append_page(page(third.id))
