from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from yandex_analytics_reaper.domain import (
    ListingMediaObservation,
    ListingStatus,
    ListingStatusObservation,
    ListingStatusReason,
    ListingUpdateObservation,
    Platform,
)
from yandex_analytics_reaper.evidence import FieldLineage
from yandex_analytics_reaper.sources.yandex.parsers import GameDetails, PlayPageData

from .history_models import (
    NormalizedListingHistories,
    NormalizedListingMedia,
    NormalizedListingStatus,
    NormalizedListingUpdate,
)
from .models import NormalizationContext

_NORMALIZER_VERSION = "1"
_UPDATE_VERSION_TARGET = "listing_update_observations.app_version"
_UPDATE_PUBLISHED_TARGET = "listing_update_observations.source_published_at"
_STATUS_TARGET = "listing_status_observations.status"
_MEDIA_TARGET = "listing_media_observations.manifest_hash"
_PLAY_PAGE_ROOT = "$.__playPageData__.gameData"


class YandexListingHistoryNormalizer:
    """Normalize directly observed Yandex listing history facts with raw lineage."""

    version = _NORMALIZER_VERSION

    def normalize_details(
        self,
        details: GameDetails,
        context: NormalizationContext,
    ) -> NormalizedListingHistories:
        source_path = _source_path(details)
        listing_id = _listing_id(details.app_id)
        status = NormalizedListingStatus(
            observation=ListingStatusObservation(
                platform_listing_id=listing_id,
                observed_at=context.observed_at,
                status=ListingStatus.PUBLISHED,
                reason=ListingStatusReason.OBSERVED_IN_CATALOGUE_METADATA,
            ),
            lineage=(
                _lineage(
                    context,
                    source_field_path=f"{source_path}.appID",
                    target_field_path=_STATUS_TARGET,
                    transformation_name="catalogue_presence",
                ),
            ),
        )

        media: NormalizedListingMedia | None = None
        if details.media is not None:
            media = NormalizedListingMedia(
                observation=ListingMediaObservation(
                    platform_listing_id=listing_id,
                    observed_at=context.observed_at,
                    manifest_hash=_media_hash(details.media),
                ),
                lineage=(
                    _lineage(
                        context,
                        source_field_path=f"{source_path}.media",
                        target_field_path=_MEDIA_TARGET,
                        transformation_name="canonical_media_sha256",
                    ),
                ),
            )

        return NormalizedListingHistories(status=status, media=media)

    def normalize_play_page(
        self,
        page: PlayPageData,
        context: NormalizationContext,
    ) -> NormalizedListingHistories:
        if page.app_id is None:
            raise ValueError("play-page DTO cannot produce history without app_id")
        listing_id = _listing_id(page.app_id)
        status = NormalizedListingStatus(
            observation=ListingStatusObservation(
                platform_listing_id=listing_id,
                observed_at=context.observed_at,
                status=ListingStatus.PUBLISHED,
                reason=ListingStatusReason.OBSERVED_ON_GAME_PAGE,
            ),
            lineage=(
                _lineage(
                    context,
                    source_field_path=f"{_PLAY_PAGE_ROOT}.appID",
                    target_field_path=_STATUS_TARGET,
                    transformation_name="game_page_presence",
                ),
            ),
        )

        update: NormalizedListingUpdate | None = None
        source_published_at = _unix_time(page.published_time)
        if page.app_version is not None or source_published_at is not None:
            lineage: list[FieldLineage] = []
            if page.app_version is not None:
                lineage.append(
                    _lineage(
                        context,
                        source_field_path=f"{_PLAY_PAGE_ROOT}.appVersion",
                        target_field_path=_UPDATE_VERSION_TARGET,
                        transformation_name="app_version",
                    )
                )
            if source_published_at is not None:
                lineage.append(
                    _lineage(
                        context,
                        source_field_path=f"{_PLAY_PAGE_ROOT}.publishedTime",
                        target_field_path=_UPDATE_PUBLISHED_TARGET,
                        transformation_name="unix_timestamp",
                    )
                )
            update = NormalizedListingUpdate(
                observation=ListingUpdateObservation(
                    platform_listing_id=listing_id,
                    observed_at=context.observed_at,
                    app_version=page.app_version,
                    source_published_at=source_published_at,
                ),
                lineage=tuple(lineage),
            )

        return NormalizedListingHistories(update=update, status=status)


def _source_path(details: GameDetails) -> str:
    if details.source_object_path is None:
        raise ValueError(
            "get-games DTO is missing source_object_path required for history lineage"
        )
    return details.source_object_path


def _listing_id(app_id: int) -> str:
    return f"{Platform.YANDEX_GAMES.value}:{app_id}"


def _media_hash(media: dict[str, object]) -> str:
    encoded = json.dumps(
        media,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _lineage(
    context: NormalizationContext,
    *,
    source_field_path: str,
    target_field_path: str,
    transformation_name: str,
) -> FieldLineage:
    return FieldLineage(
        raw_snapshot_id=context.raw_snapshot_id,
        source_field_path=source_field_path,
        target_field_path=target_field_path,
        transformation_name=f"YandexListingHistoryNormalizer.{transformation_name}",
        transformation_version=_NORMALIZER_VERSION,
    )


def _unix_time(value: int | None) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(value, UTC)
    except (OSError, OverflowError, ValueError) as exc:
        raise ValueError(f"invalid Unix timestamp from source: {value}") from exc
