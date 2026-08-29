from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, field_validator, model_validator


class ListingStatus(StrEnum):
    PUBLISHED = "published"
    UNKNOWN = "unknown"


class ListingStatusReason(StrEnum):
    OBSERVED_IN_CATALOGUE_METADATA = "observed_in_catalogue_metadata"
    OBSERVED_ON_GAME_PAGE = "observed_on_game_page"
    REQUESTED_BUT_NOT_RETURNED = "requested_but_not_returned"


class ListingUpdateObservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    platform_listing_id: str
    observed_at: AwareDatetime
    app_version: str | None = None
    source_published_at: AwareDatetime | None = None

    @field_validator("platform_listing_id")
    @classmethod
    def require_listing_id(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("platform_listing_id cannot be blank")
        return stripped

    @field_validator("app_version")
    @classmethod
    def validate_app_version(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("app_version cannot be blank when provided")
        return stripped

    @model_validator(mode="after")
    def require_update_field(self) -> Self:
        if self.app_version is None and self.source_published_at is None:
            raise ValueError("update observation requires app_version or source_published_at")
        return self


class ListingStatusObservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    platform_listing_id: str
    observed_at: AwareDatetime
    status: ListingStatus
    reason: ListingStatusReason

    @field_validator("platform_listing_id")
    @classmethod
    def require_listing_id(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("platform_listing_id cannot be blank")
        return stripped

    @model_validator(mode="after")
    def validate_status_reason(self) -> Self:
        if self.reason is ListingStatusReason.REQUESTED_BUT_NOT_RETURNED:
            if self.status is not ListingStatus.UNKNOWN:
                raise ValueError("requested-but-not-returned status must remain unknown")
        elif self.status is not ListingStatus.PUBLISHED:
            raise ValueError("directly observed listing presence must be published")
        return self


class ListingMediaObservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    platform_listing_id: str
    observed_at: AwareDatetime
    manifest_hash: str

    @field_validator("platform_listing_id")
    @classmethod
    def require_listing_id(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("platform_listing_id cannot be blank")
        return stripped

    @field_validator("manifest_hash")
    @classmethod
    def validate_manifest_hash(cls, value: str) -> str:
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise ValueError("manifest_hash must be a lowercase SHA-256 hex digest")
        return value
