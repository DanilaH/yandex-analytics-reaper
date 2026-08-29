from __future__ import annotations

from datetime import UTC, datetime

import pytest

from yandex_analytics_reaper.domain import ProbePage
from yandex_analytics_reaper.experiments.session_profile_stability import (
    SessionProfileEligibilityError,
    _validate_feed_request,
)


def _page(index: int) -> ProbePage:
    return ProbePage(
        run_id="probe:test",
        page_index=index,
        raw_snapshot_id=f"raw-{index}",
        retrieved_at=datetime(2026, 8, 29, 8, 0, index, tzinfo=UTC),
        request_page_id=(None if index == 0 else f"page-{index}"),
        request_rtx_reqid=(None if index == 0 else f"req-{index}"),
        response_next_page_id=None,
        response_rtx_reqid=None,
        has_next_page=False,
    )


def _request_context(**param_updates: object) -> dict[str, object]:
    params: dict[str, object] = {
        "games_count": 20,
        "with_promos": "false",
        "lang": "ru",
        "device-type": "desktop",
        "platform": "desktop_other",
    }
    params.update(param_updates)
    return {"probe_context": {}, "params": params}


def test_session_profile_rejects_changed_stable_feed_parameter() -> None:
    with pytest.raises(SessionProfileEligibilityError, match="with_promos"):
        _validate_feed_request(_request_context(with_promos="true"), _page(0))


def test_session_profile_rejects_undeclared_feed_parameter() -> None:
    with pytest.raises(SessionProfileEligibilityError, match="frozen request shape"):
        _validate_feed_request(_request_context(experiment_variant="x"), _page(0))


def test_session_profile_requires_exact_pagination_parameter_shape_and_linkage() -> None:
    with pytest.raises(SessionProfileEligibilityError, match="frozen request shape"):
        _validate_feed_request(_request_context(page_id="page-1"), _page(1))

    with pytest.raises(SessionProfileEligibilityError, match="page_id"):
        _validate_feed_request(
            _request_context(**{"page_id": "wrong", "rtx-reqid": "req-1"}),
            _page(1),
        )

    _validate_feed_request(
        _request_context(**{"page_id": "page-1", "rtx-reqid": "req-1"}),
        _page(1),
    )
