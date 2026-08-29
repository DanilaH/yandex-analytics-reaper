from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Platform(StrEnum):
    YANDEX_GAMES = "yandex_games"
    STEAM = "steam"
    GOOGLE_PLAY = "google_play"
    APP_STORE = "app_store"
    OTHER = "other"


class Game(BaseModel):
    """Platform-neutral canonical identity."""

    model_config = ConfigDict(frozen=True)

    id: str
    canonical_name: str
    identity_status: str = "unresolved"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PlatformListing(BaseModel):
    """One platform-specific listing for a canonical game."""

    model_config = ConfigDict(frozen=True)

    id: str
    game_id: str | None = None
    platform: Platform
    external_app_id: str
    listing_url: str | None = None
    developer_external_id: str | None = None
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    first_published_at: datetime | None = None


class SessionProfile(StrEnum):
    CLEAN_ANONYMOUS = "clean_anonymous"
    PERSISTENT_ANONYMOUS = "persistent_anonymous"
    AUTHENTICATED_TEST = "authenticated_test"


class ProbeContext(BaseModel):
    """Context that may affect catalog/search/exposure observations."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    language: str = "ru"
    device_type: str = "desktop"
    platform: str = "desktop_other"
    country_observed: str | None = None
    collector_region: str | None = None
    session_profile: SessionProfile = SessionProfile.CLEAN_ANONYMOUS
    session_instance_id: str | None = Field(
        default=None,
        pattern=r"^session:[0-9a-f]{32}$",
    )
    cookie_state_hash: str | None = None
    profile_age_days: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_session_instance_semantics(self) -> Self:
        if (
            self.session_profile is SessionProfile.CLEAN_ANONYMOUS
            and self.session_instance_id is not None
        ):
            raise ValueError("clean_anonymous context cannot carry session_instance_id")
        return self
