from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from yandex_analytics_reaper.analyst import (
    AnalystEvidenceReference,
    AnalystExposureSurfaceSummary,
    AnalystListingRow,
    AnalystQuerySupplyPage,
    AnalystQuerySupplySummary,
    AnalystResolvedValue,
)
from yandex_analytics_reaper.analyst.features import AnalystFeatureError, _release_distribution

_BASE = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)


def _evidence(field: str) -> AnalystEvidenceReference:
    instant = _BASE.isoformat().replace("+00:00", "Z")
    return AnalystEvidenceReference(
        observation_id="state:one",
        observed_at=instant,
        retrieved_at=instant,
        raw_snapshot_ids=("raw:one",),
        source_field_paths=(field,),
        normalizer_name="YandexGameNormalizer",
        normalizer_version="4",
    )


def _missing() -> AnalystResolvedValue:
    return AnalystResolvedValue(missing_reason="not_observed")


def _listing_with_first_published(value: str) -> AnalystListingRow:
    missing = _missing()
    return AnalystListingRow(
        platform_listing_id="yandex_games:1",
        platform="yandex_games",
        external_app_id="1",
        canonical_url="https://yandex.ru/games/app/1",
        comparable_set_ids=("set",),
        title=missing,
        developer_id=missing,
        developer_name=missing,
        first_published_at=AnalystResolvedValue(
            value=value,
            evidence=_evidence("$.games[0].firstPublished"),
        ),
        app_version=missing,
        published_at=missing,
        languages=missing,
        supported_platforms=missing,
        orientation=missing,
        cloud_save=missing,
        leaderboards=missing,
        purchases_enabled=missing,
        has_products=missing,
        rewarded_ads=missing,
        fullscreen_ads=missing,
        sticky_ads=missing,
        yandex_games_rating=missing,
        player_rating=missing,
        rating_count=missing,
    )


def test_query_supply_marks_inconsistent_observed_pages() -> None:
    pages = (
        AnalystQuerySupplyPage(
            page_index=0,
            raw_snapshot_id="raw:zero",
            source_field_path="$.totalGamesCount",
            total_games_count=42,
        ),
        AnalystQuerySupplyPage(
            page_index=1,
            raw_snapshot_id="raw:one",
            source_field_path="$.totalGamesCount",
            total_games_count=41,
        ),
    )

    summary = AnalystQuerySupplySummary(
        query_text="merge",
        probe_run_id="probe:search",
        pages=pages,
        observed_values=(42, 41),
        distinct_observed_values=(41, 42),
        consistent_across_observed_pages=False,
    )

    assert summary.consistent_across_observed_pages is False
    assert summary.distinct_observed_values == (41, 42)


def test_feed_collected_with_zero_member_exposure_is_observed_zero() -> None:
    summary = AnalystExposureSurfaceSummary(
        evidence_available=True,
        member_count=4,
        run_count=1,
        exposure_count=0,
        exposed_member_count=0,
        unexposed_member_count=4,
        member_coverage_ratio=0.0,
    )

    assert summary.evidence_available is True
    assert summary.member_coverage_ratio == 0.0


def test_future_first_publication_fails_closed() -> None:
    future = (_BASE + timedelta(days=1)).isoformat().replace("+00:00", "Z")
    listing = _listing_with_first_published(future)

    with pytest.raises(AnalystFeatureError, match="after snapshot time"):
        _release_distribution((listing,), _BASE)
