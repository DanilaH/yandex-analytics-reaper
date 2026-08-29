from __future__ import annotations

from typing import Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, field_validator, model_validator

from yandex_analytics_reaper.domain import (
    GameMetricObservation,
    ListingStateObservation,
    PlatformDeveloper,
    PlatformListing,
)
from yandex_analytics_reaper.evidence import FieldLineage


class NormalizationContext(BaseModel):
    """Raw snapshot identity and times shared by one normalization operation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    raw_snapshot_id: str
    observed_at: AwareDatetime
    available_at: AwareDatetime
    retrieved_at: AwareDatetime

    @field_validator("raw_snapshot_id")
    @classmethod
    def require_snapshot_id(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("raw_snapshot_id cannot be blank")
        return stripped

    @model_validator(mode="after")
    def validate_time_order(self) -> Self:
        if self.observed_at > self.available_at:
            raise ValueError("observed_at cannot be later than available_at")
        if self.available_at > self.retrieved_at:
            raise ValueError("available_at cannot be later than retrieved_at")
        return self


class NormalizedMetricObservation(BaseModel):
    """Normalized metric plus field-level source lineage created by the normalizer."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    metric: GameMetricObservation
    lineage: tuple[FieldLineage, ...]


class NormalizedListingObservation(BaseModel):
    """Stable domain output from a source-specific listing DTO."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    listing: PlatformListing
    developer: PlatformDeveloper | None
    listing_state: ListingStateObservation
    metrics: tuple[NormalizedMetricObservation, ...] = ()
    context: NormalizationContext
