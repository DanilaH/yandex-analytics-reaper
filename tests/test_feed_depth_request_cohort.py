from __future__ import annotations

import pytest

from yandex_analytics_reaper.experiments.feed_depth import (
    FeedDepthEligibilityError,
    _validate_feed_request,
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


def test_feed_depth_rejects_changed_stable_feed_parameter() -> None:
    with pytest.raises(FeedDepthEligibilityError, match="with_promos"):
        _validate_feed_request(_request_context(with_promos="true"), page_index=0)


def test_feed_depth_rejects_undeclared_feed_parameter() -> None:
    with pytest.raises(FeedDepthEligibilityError, match="frozen request shape"):
        _validate_feed_request(_request_context(experiment_variant="x"), page_index=0)


def test_feed_depth_requires_exact_pagination_parameter_shape() -> None:
    with pytest.raises(FeedDepthEligibilityError, match="frozen request shape"):
        _validate_feed_request(_request_context(page_id="page-1"), page_index=1)

    paged = _request_context(**{"page_id": "page-1", "rtx-reqid": "req-1"})
    _validate_feed_request(paged, page_index=1)
