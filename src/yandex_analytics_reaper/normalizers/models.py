from __future__ import annotations

from typing import Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, model_validator

from yandex_analytics_reaper.domain import (
    GameMetricObservation,
    ListingStateObservation,
    PlatformDeveloper,
    PlatformListing,
)


class NormalizationContext(BaseModel):
    """Times shared by observations emitted from one parsed source response."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    observed_at: AwareDatetime
    available_at: AwareDatetime
    retrieved_at: AwareDatetime

    @model_validator(mode="after")
    def validate_availability_order(self) -> Self:
        if self.available_at > self.retrieved_at:
            raise ValueError("available_at cannot be later than retrieved_at")
        return self


class NormalizedListingObservation(BaseModel):
    """Stable domain output from a source-specific listing DTO."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    listing: PlatformListing
    developer: PlatformDeveloper | None
    listing_state: ListingStateObservation
    metrics: tuple[GameMetricObservation, ...] = ()
    context: NormalizationContext
