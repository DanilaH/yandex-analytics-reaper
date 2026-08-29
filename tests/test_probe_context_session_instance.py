from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from yandex_analytics_reaper.domain import ProbeContext, ProbeKind, SessionProfile
from yandex_analytics_reaper.storage import SQLiteProbeRunStore


def test_persistent_session_instance_round_trips_through_probe_context_store(
    tmp_path: Path,
) -> None:
    store = SQLiteProbeRunStore(tmp_path / "market.sqlite3")
    context = ProbeContext(
        session_profile=SessionProfile.PERSISTENT_ANONYMOUS,
        session_instance_id="session:0123456789abcdef0123456789abcdef",
        cookie_state_hash="a" * 64,
        profile_age_days=3,
    )

    run = store.create_run(
        source_id="yandex_public",
        request_key="catalogue.feed",
        kind=ProbeKind.RECOMMENDATION_FEED,
        context=context,
        requested_page_limit=1,
        started_at=datetime(2026, 8, 29, 9, 0, tzinfo=UTC),
    )

    record = store.get_run(run.id)
    assert record is not None
    assert record.context == context
    assert record.context.session_instance_id == context.session_instance_id
