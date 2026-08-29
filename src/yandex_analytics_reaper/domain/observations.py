from __future__ import annotations

import math
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator

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
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None


class ListingStateObservation(BaseModel):
    """Platform-neutral semantic snapshot of listing fields observed at one time."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    platform_listing_id: str
    observed_at: datetime
    title: str | None = None
    developer_id: str | None = None
    developer_name: str | None = None
    first_published_at: datetime | None = None
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
    """One observed semantic numeric metric with no coercion from non-numeric input."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    platform_listing_id: str
    observed_at: datetime
    metric_name: GameMetricName
    value: int | float

    @field_validator("value", mode="before")
    @classmethod
    def require_real_number(cls, value: object) -> object:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("metric value must be an int or float, not a coerced value")
        if not math.isfinite(float(value)):
            raise ValueError("metric value must be finite")
        return value
