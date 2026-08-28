from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from yandex_analytics_reaper.domain import GameMetricName, Platform, ProbeContext, SessionProfile
from yandex_analytics_reaper.normalizers import NormalizationContext, YandexGameNormalizer
from yandex_analytics_reaper.sources.yandex.parsers import Developer, GameDetails, PlayPageData


def _context() -> NormalizationContext:
    instant = datetime(2026, 8, 28, 18, 0, tzinfo=UTC)
    return NormalizationContext(observed_at=instant, available_at=instant, retrieved_at=instant)


def test_details_normalizer_converts_source_dto_to_domain_semantics() -> None:
    details = GameDetails(
        app_id=438560,
        title="Example",
        developer=Developer(id=10, name="Dev"),
        yandex_rating=86,
        player_rating=4.3,
        rating_count=6,
        first_published=1750000000,
        min_load_time=14.8,
        languages=("ru", "en"),
        platforms=("desktop", "mobile"),
        orientation="any",
        cloud_save=True,
        leaderboards=True,
        purchases_enabled=True,
        has_products=False,
    )

    normalized = YandexGameNormalizer().normalize_details(details, _context())

    assert normalized.listing.id == "yandex_games:438560"
    assert normalized.listing.external_app_id == "438560"
    assert normalized.developer is not None
    assert normalized.developer.platform is Platform.YANDEX_GAMES
    assert normalized.developer.external_developer_id == "10"
    assert normalized.listing_state.developer_id == "yandex_games:10"
    assert normalized.listing_state.languages == ("ru", "en")
    assert normalized.listing_state.has_products is False
    assert normalized.listing.first_published_at == datetime.fromtimestamp(1750000000, UTC)

    metrics = {metric.metric_name: metric.value for metric in normalized.metrics}
    assert metrics == {
        GameMetricName.YANDEX_GAMES_RATING: 86,
        GameMetricName.PLAYER_RATING: 4.3,
        GameMetricName.RATING_COUNT: 6,
        GameMetricName.MIN_LOAD_TIME_SECONDS: 14.8,
    }


def test_play_page_normalizer_preserves_boolean_false_and_publish_time() -> None:
    page = PlayPageData(
        app_id=438560,
        app_version="1.2.3",
        published_time=1750000100,
        yandex_rating=86,
        rewarded_ads=True,
        fullscreen_ads=False,
        sticky_ads=False,
        leaderboards=True,
        purchases_enabled=True,
        has_products=False,
    )

    normalized = YandexGameNormalizer().normalize_play_page(page, _context())

    assert normalized.listing_state.app_version == "1.2.3"
    assert normalized.listing_state.published_at == datetime.fromtimestamp(1750000100, UTC)
    assert normalized.listing_state.fullscreen_ads is False
    assert normalized.listing_state.sticky_ads is False
    assert normalized.listing_state.has_products is False


def test_play_page_normalizer_rejects_missing_identity() -> None:
    with pytest.raises(ValueError, match="without app_id"):
        YandexGameNormalizer().normalize_play_page(PlayPageData(), _context())


def test_normalizer_rejects_invalid_source_timestamp() -> None:
    details = GameDetails(app_id=1, first_published=10**30)

    with pytest.raises(ValueError, match="invalid Unix timestamp"):
        YandexGameNormalizer().normalize_details(details, _context())


def test_normalization_context_requires_aware_ordered_timestamps() -> None:
    instant = datetime(2026, 8, 28, 18, 0, tzinfo=UTC)

    with pytest.raises(ValidationError):
        NormalizationContext(
            observed_at=datetime(2026, 8, 28, 18, 0),
            available_at=instant,
            retrieved_at=instant,
        )

    with pytest.raises(ValidationError, match="available_at cannot be later"):
        NormalizationContext(
            observed_at=instant,
            available_at=instant + timedelta(seconds=1),
            retrieved_at=instant,
        )


def test_probe_context_rejects_redundant_authenticated_state() -> None:
    with pytest.raises(ValidationError, match="authenticated_state"):
        ProbeContext(authenticated_state=True)

    context = ProbeContext(session_profile=SessionProfile.AUTHENTICATED_TEST)
    assert context.session_profile is SessionProfile.AUTHENTICATED_TEST
