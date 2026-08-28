from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from .models import Platform


class GameMetricName(StrEnum):
    YANDEX_GAMES_RATING = "yandex_games_rating"
    PLAYER_RATING = "player_rating"
    RATING_COUNT = "rating_count"
    MIN_LOAD_TIME_SECONDS = "min_load_time_seconds"


class PlatformDeveloper(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    platform: Platform
    external_developer_id: str
    display_name: str | None = None


class ListingStateObservation(BaseModel):
    """Platform-neutral semantic snapshot of listing fields observed at one time."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    platform_listing_id: str
    observed_at: datetime
    title: str | None = None
    developer_id: str | None = None
    app_version: str | None = None
    published_at: datetime | None = None
    languages: tuple[str, ...] | None = None
    supported_platforms: tuple[str, ...] | None = None
    orientation: str | None = None
    cloud_save: bool | None = None
    leaderboards: bool | None = None
    purchases_enabled: bool | None = None
    has_products: bool | None = None
    rewarded_ads: bool | None = None
    fullscreen_ads: bool | None = None
    sticky_ads: bool | None = None


class GameMetricObservation(BaseModel):
    """One observed semantic metric; missing source values produce no metric observation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    platform_listing_id: str
    observed_at: datetime
    metric_name: GameMetricName
    value: int | float
