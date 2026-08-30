from __future__ import annotations

from datetime import UTC, datetime

from yandex_analytics_reaper.domain import (
    GameMetricName,
    GameMetricObservation,
    ListingStateObservation,
    Platform,
    PlatformDeveloper,
    PlatformListing,
)
from yandex_analytics_reaper.evidence import FieldLineage
from yandex_analytics_reaper.sources.yandex.parsers import GameCard, GameDetails, PlayPageData

from .models import (
    NormalizationContext,
    NormalizedListingObservation,
    NormalizedMetricObservation,
)

_METRIC_NORMALIZER_VERSION = "2"
_LISTING_STATE_NORMALIZER_VERSION = "4"
_TARGET_METRIC_VALUE = "game_metric_observations.value_numeric"
_TARGET_STATE_PREFIX = "listing_state_observations"


class YandexGameNormalizer:
    """Convert Yandex source DTOs into stable domain observations with lineage."""

    # `version` is the stable metric-transformation version retained for the
    # frozen collection-cadence-v1 evidence contract. Listing-state evolution is
    # versioned independently because adding state fields must not rewrite metric semantics.
    version = _METRIC_NORMALIZER_VERSION
    metric_version = _METRIC_NORMALIZER_VERSION
    listing_state_version = _LISTING_STATE_NORMALIZER_VERSION

    def normalize_card(
        self,
        card: GameCard,
        context: NormalizationContext,
    ) -> NormalizedListingObservation:
        listing, developer = self._identity(card, first_published=None)
        metrics = self._card_metrics(card, context)
        state = ListingStateObservation(
            platform_listing_id=listing.id,
            observed_at=context.observed_at,
            title=card.title,
            developer_id=developer.id if developer is not None else None,
            developer_name=developer.display_name if developer is not None else None,
        )
        return NormalizedListingObservation(
            listing=listing,
            developer=developer,
            listing_state=state,
            listing_state_lineage=_card_state_lineage(card, state, context),
            metrics=metrics,
            context=context,
        )

    def normalize_details(
        self,
        details: GameDetails,
        context: NormalizationContext,
    ) -> NormalizedListingObservation:
        first_published_at = _unix_time(details.first_published)
        listing, developer = self._identity(details, first_published=first_published_at)
        metrics = self._card_metrics(details, context)
        if details.min_load_time is not None:
            metrics += (
                _metric(
                    listing_id=listing.id,
                    observed_at=context.observed_at,
                    metric_name=GameMetricName.MIN_LOAD_TIME_SECONDS,
                    value=details.min_load_time,
                    context=context,
                    source_field_path=_source_field(details, "minLoadTime"),
                ),
            )

        state = ListingStateObservation(
            platform_listing_id=listing.id,
            observed_at=context.observed_at,
            title=details.title,
            developer_id=developer.id if developer is not None else None,
            developer_name=developer.display_name if developer is not None else None,
            first_published_at=first_published_at,
            languages=details.languages,
            supported_platforms=details.platforms,
            orientation=details.orientation,
            cloud_save=details.cloud_save,
            leaderboards=details.leaderboards,
            purchases_enabled=details.purchases_enabled,
            has_products=details.has_products,
        )
        return NormalizedListingObservation(
            listing=listing,
            developer=developer,
            listing_state=state,
            listing_state_lineage=_details_state_lineage(details, state, context),
            metrics=metrics,
            context=context,
        )

    def normalize_play_page(
        self,
        page: PlayPageData,
        context: NormalizationContext,
    ) -> NormalizedListingObservation:
        if page.app_id is None:
            raise ValueError("play-page DTO cannot be normalized without app_id")

        listing = _listing(page.app_id)
        metrics: tuple[NormalizedMetricObservation, ...] = ()
        if page.yandex_rating is not None:
            metrics = (
                _metric(
                    listing_id=listing.id,
                    observed_at=context.observed_at,
                    metric_name=GameMetricName.YANDEX_GAMES_RATING,
                    value=page.yandex_rating,
                    context=context,
                    source_field_path="$.__playPageData__.gameData.gqRating",
                ),
            )

        state = ListingStateObservation(
            platform_listing_id=listing.id,
            observed_at=context.observed_at,
            app_version=page.app_version,
            published_at=_unix_time(page.published_time),
            leaderboards=page.leaderboards,
            purchases_enabled=page.purchases_enabled,
            has_products=page.has_products,
            rewarded_ads=page.rewarded_ads,
            fullscreen_ads=page.fullscreen_ads,
            sticky_ads=page.sticky_ads,
        )
        return NormalizedListingObservation(
            listing=listing,
            developer=None,
            listing_state=state,
            listing_state_lineage=_play_page_state_lineage(page, context),
            metrics=metrics,
            context=context,
        )

    def _identity(
        self,
        card: GameCard,
        *,
        first_published: datetime | None,
    ) -> tuple[PlatformListing, PlatformDeveloper | None]:
        developer = _developer(card)
        listing = _listing(
            card.app_id,
            developer_external_id=(developer.external_developer_id if developer else None),
            first_published=first_published,
        )
        return listing, developer

    @staticmethod
    def _card_metrics(
        card: GameCard,
        context: NormalizationContext,
    ) -> tuple[NormalizedMetricObservation, ...]:
        listing_id = _listing_id(card.app_id)
        metrics: list[NormalizedMetricObservation] = []
        if card.yandex_rating is not None:
            metrics.append(
                _metric(
                    listing_id=listing_id,
                    observed_at=context.observed_at,
                    metric_name=GameMetricName.YANDEX_GAMES_RATING,
                    value=card.yandex_rating,
                    context=context,
                    source_field_path=_source_field(card, "gqRating"),
                )
            )
        if card.player_rating is not None:
            metrics.append(
                _metric(
                    listing_id=listing_id,
                    observed_at=context.observed_at,
                    metric_name=GameMetricName.PLAYER_RATING,
                    value=card.player_rating,
                    context=context,
                    source_field_path=_source_field(card, "rating"),
                )
            )
        if card.rating_count is not None:
            metrics.append(
                _metric(
                    listing_id=listing_id,
                    observed_at=context.observed_at,
                    metric_name=GameMetricName.RATING_COUNT,
                    value=card.rating_count,
                    context=context,
                    source_field_path=_source_field(card, "ratingCount"),
                )
            )
        return tuple(metrics)


def _metric(
    *,
    listing_id: str,
    observed_at: datetime,
    metric_name: GameMetricName,
    value: int | float,
    context: NormalizationContext,
    source_field_path: str,
) -> NormalizedMetricObservation:
    transformation_name = f"YandexGameNormalizer.{metric_name.value}"
    return NormalizedMetricObservation(
        metric=GameMetricObservation(
            platform_listing_id=listing_id,
            observed_at=observed_at,
            metric_name=metric_name,
            value=value,
        ),
        lineage=(
            _lineage(
                context,
                source_field_path,
                _TARGET_METRIC_VALUE,
                transformation_name,
                transformation_version=_METRIC_NORMALIZER_VERSION,
            ),
        ),
    )


def _card_state_lineage(
    card: GameCard,
    state: ListingStateObservation,
    context: NormalizationContext,
) -> tuple[FieldLineage, ...]:
    base = _source_object_path(card)
    fields: list[tuple[str, str]] = [(f"{base}.appID", "platform_listing_id")]
    if state.title is not None:
        fields.append((f"{base}.title", "title"))
    if state.developer_id is not None:
        fields.append((f"{base}.developer.id", "developer_id"))
    if state.developer_name is not None:
        fields.append((f"{base}.developer.name", "developer_name"))
    return _state_lineage(context, fields)


def _details_state_lineage(
    details: GameDetails,
    state: ListingStateObservation,
    context: NormalizationContext,
) -> tuple[FieldLineage, ...]:
    base = _source_object_path(details)
    lineage = list(_card_state_lineage(details, state, context))
    mapping = (
        (state.first_published_at, f"{base}.firstPublished", "first_published_at"),
        (state.languages, f"{base}.features.languages", "languages"),
        (
            state.supported_platforms,
            f"{base}.features.platforms",
            "supported_platforms",
        ),
        (state.orientation, f"{base}.features.orientation", "orientation"),
        (state.cloud_save, f"{base}.features.cloud_save", "cloud_save"),
        (state.leaderboards, f"{base}.extraFeatures.leaderboards", "leaderboards"),
        (
            state.purchases_enabled,
            f"{base}.extraFeatures.purchases",
            "purchases_enabled",
        ),
        (state.has_products, f"{base}.extraFeatures.hasProducts", "has_products"),
    )
    for value, source, target in mapping:
        if value is not None:
            lineage.extend(_state_lineage(context, [(source, target)]))
    return tuple(lineage)


def _play_page_state_lineage(
    page: PlayPageData,
    context: NormalizationContext,
) -> tuple[FieldLineage, ...]:
    base = "$.__playPageData__.gameData"
    fields: list[tuple[str, str]] = [(f"{base}.appID", "platform_listing_id")]
    mapping = (
        (page.app_version, f"{base}.appVersion", "app_version"),
        (page.published_time, f"{base}.publishedTime", "published_at"),
        (page.leaderboards, f"{base}.extraFeatures.leaderboards", "leaderboards"),
        (page.purchases_enabled, f"{base}.extraFeatures.purchases", "purchases_enabled"),
        (page.has_products, f"{base}.extraFeatures.hasProducts", "has_products"),
        (page.rewarded_ads, f"{base}.advUsedBlocks.rewarded", "rewarded_ads"),
        (page.fullscreen_ads, f"{base}.advUsedBlocks.fullscreen", "fullscreen_ads"),
        (page.sticky_ads, f"{base}.settings.adv.sticky", "sticky_ads"),
    )
    fields.extend((source, target) for value, source, target in mapping if value is not None)
    return _state_lineage(context, fields)


def _state_lineage(
    context: NormalizationContext,
    fields: list[tuple[str, str]],
) -> tuple[FieldLineage, ...]:
    return tuple(
        _lineage(
            context,
            source,
            f"{_TARGET_STATE_PREFIX}.{target}",
            f"YandexGameNormalizer.listing_state.{target}",
            transformation_version=_LISTING_STATE_NORMALIZER_VERSION,
        )
        for source, target in fields
    )


def _lineage(
    context: NormalizationContext,
    source_field_path: str,
    target_field_path: str,
    transformation_name: str,
    *,
    transformation_version: str,
) -> FieldLineage:
    return FieldLineage(
        raw_snapshot_id=context.raw_snapshot_id,
        source_field_path=source_field_path,
        target_field_path=target_field_path,
        transformation_name=transformation_name,
        transformation_version=transformation_version,
    )


def _source_field(card: GameCard, field: str) -> str:
    return f"{_source_object_path(card)}.{field}"


def _source_object_path(card: GameCard) -> str:
    if card.source_object_path is None:
        raise ValueError(
            f"source DTO for app {card.app_id} is missing source_object_path required for lineage"
        )
    return card.source_object_path


def _listing_id(app_id: int) -> str:
    return f"{Platform.YANDEX_GAMES.value}:{app_id}"


def _listing(
    app_id: int,
    *,
    developer_external_id: str | None = None,
    first_published: datetime | None = None,
) -> PlatformListing:
    return PlatformListing(
        id=_listing_id(app_id),
        platform=Platform.YANDEX_GAMES,
        external_app_id=str(app_id),
        listing_url=f"https://yandex.ru/games/app/{app_id}",
        developer_external_id=developer_external_id,
        first_published_at=first_published,
    )


def _developer(card: GameCard) -> PlatformDeveloper | None:
    if card.developer is None or card.developer.id is None:
        return None
    external_id = str(card.developer.id)
    return PlatformDeveloper(
        id=f"{Platform.YANDEX_GAMES.value}:{external_id}",
        platform=Platform.YANDEX_GAMES,
        external_developer_id=external_id,
        display_name=card.developer.name,
    )


def _unix_time(value: int | None) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(value, UTC)
    except (OSError, OverflowError, ValueError) as exc:
        raise ValueError(f"invalid Unix timestamp from source: {value}") from exc
