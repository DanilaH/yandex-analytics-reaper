from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from yandex_analytics_reaper.domain import GameMetricName, Platform, ProbeContext, SessionProfile
from yandex_analytics_reaper.normalizers import NormalizationContext, YandexGameNormalizer
from yandex_analytics_reaper.sources.yandex.parsers import (
    Developer,
    GameCard,
    GameDetails,
    PlayPageData,
)

_RAW_SNAPSHOT_ID = "20260828T180000000000Z-test"


def _context() -> NormalizationContext:
    instant = datetime(2026, 8, 28, 18, 0, tzinfo=UTC)
    return NormalizationContext(
        raw_snapshot_id=_RAW_SNAPSHOT_ID,
        observed_at=instant,
        available_at=instant,
        retrieved_at=instant,
    )


def test_details_normalizer_converts_source_dto_to_domain_semantics() -> None:
    details = GameDetails(
        app_id=438560,
        source_object_path="$.games[0]",
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

    metrics = {item.metric.metric_name: item.metric.value for item in normalized.metrics}
    assert metrics == {
        GameMetricName.YANDEX_GAMES_RATING: 86,
        GameMetricName.PLAYER_RATING: 4.3,
        GameMetricName.RATING_COUNT: 6,
        GameMetricName.MIN_LOAD_TIME_SECONDS: 14.8,
    }

    yandex_rating = next(
        item
        for item in normalized.metrics
        if item.metric.metric_name is GameMetricName.YANDEX_GAMES_RATING
    )
    assert len(yandex_rating.lineage) == 1
    lineage = yandex_rating.lineage[0]
    assert lineage.raw_snapshot_id == _RAW_SNAPSHOT_ID
    assert lineage.source_field_path == "$.games[0].gqRating"
    assert lineage.target_field_path == "game_metric_observations.value_numeric"
    assert lineage.transformation_name == "YandexGameNormalizer.yandex_games_rating"
    assert lineage.transformation_version == YandexGameNormalizer.version


def test_card_normalizer_uses_exact_feed_items_source_path() -> None:
    card = GameCard(
        app_id=10,
        source_object_path="$.feed[1].items[2]",
        yandex_rating=81,
    )

    normalized = YandexGameNormalizer().normalize_card(card, _context())

    assert normalized.metrics[0].lineage[0].source_field_path == "$.feed[1].items[2].gqRating"


def test_normalizer_rejects_metric_dto_without_parser_source_path() -> None:
    card = GameCard(app_id=10, yandex_rating=81)

    with pytest.raises(ValueError, match="missing source_object_path"):
        YandexGameNormalizer().normalize_card(card, _context())


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
    assert (
        normalized.metrics[0].lineage[0].source_field_path
        == "$.__playPageData__.gameData.gqRating"
    )


def test_play_page_normalizer_rejects_missing_identity() -> None:
    with pytest.raises(ValueError, match="without app_id"):
        YandexGameNormalizer().normalize_play_page(PlayPageData(), _context())


def test_normalizer_rejects_invalid_source_timestamp() -> None:
    details = GameDetails(app_id=1, first_published=10**30)

    with pytest.raises(ValueError, match="invalid Unix timestamp"):
        YandexGameNormalizer().normalize_details(details, _context())


def test_normalization_context_requires_snapshot_and_aware_ordered_timestamps() -> None:
    instant = datetime(2026, 8, 28, 18, 0, tzinfo=UTC)

    with pytest.raises(ValidationError, match="raw_snapshot_id"):
        NormalizationContext(
            raw_snapshot_id="",
            observed_at=instant,
            available_at=instant,
            retrieved_at=instant,
        )

    with pytest.raises(ValidationError):
        NormalizationContext(
            raw_snapshot_id=_RAW_SNAPSHOT_ID,
            observed_at=datetime(2026, 8, 28, 18, 0),
            available_at=instant,
            retrieved_at=instant,
        )

    with pytest.raises(ValidationError, match="observed_at cannot be later"):
        NormalizationContext(
            raw_snapshot_id=_RAW_SNAPSHOT_ID,
            observed_at=instant + timedelta(seconds=1),
            available_at=instant,
            retrieved_at=instant + timedelta(seconds=2),
        )

    with pytest.raises(ValidationError, match="available_at cannot be later"):
        NormalizationContext(
            raw_snapshot_id=_RAW_SNAPSHOT_ID,
            observed_at=instant,
            available_at=instant + timedelta(seconds=1),
            retrieved_at=instant,
        )


def test_probe_context_rejects_redundant_authenticated_state() -> None:
    with pytest.raises(ValidationError, match="authenticated_state"):
        ProbeContext(authenticated_state=True)

    context = ProbeContext(session_profile=SessionProfile.AUTHENTICATED_TEST)
    assert context.session_profile is SessionProfile.AUTHENTICATED_TEST
