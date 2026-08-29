from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from yandex_analytics_reaper.domain import (
    ListingStatus,
    ListingStatusObservation,
    ListingStatusReason,
    ListingUpdateObservation,
)
from yandex_analytics_reaper.normalizers import NormalizedListingStatus


def test_update_history_rejects_silent_source_string_normalization() -> None:
    observed_at = datetime(2026, 8, 29, 10, 0, tzinfo=UTC)

    with pytest.raises(ValidationError, match="must already be trimmed"):
        ListingUpdateObservation(
            platform_listing_id="yandex_games:1",
            observed_at=observed_at,
            app_version=" 1.2.3 ",
        )

    with pytest.raises(ValidationError, match="must already be trimmed"):
        ListingUpdateObservation(
            platform_listing_id=" yandex_games:1 ",
            observed_at=observed_at,
            app_version="1.2.3",
        )


def test_normalized_history_requires_raw_lineage() -> None:
    with pytest.raises(ValidationError, match="at least 1 item"):
        NormalizedListingStatus(
            observation=ListingStatusObservation(
                platform_listing_id="yandex_games:1",
                observed_at=datetime(2026, 8, 29, 10, 0, tzinfo=UTC),
                status=ListingStatus.PUBLISHED,
                reason=ListingStatusReason.OBSERVED_ON_GAME_PAGE,
            ),
            lineage=(),
        )
