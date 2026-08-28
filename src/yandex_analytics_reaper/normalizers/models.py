from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from yandex_analytics_reaper.domain import (
    GameMetricObservation,
    ListingStateObservation,
    PlatformDeveloper,
    PlatformListing,
)


class NormalizationContext(BaseModel):
    """Times shared by observations emitted from one parsed source response."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    observed_at: datetime
    available_at: datetime
    retrieved_at: datetime


class NormalizedListingObservation(BaseModel):
    """Stable domain output from a source-specific listing DTO."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    listing: PlatformListing
    developer: PlatformDeveloper | None
    listing_state: ListingStateObservation
    metrics: tuple[GameMetricObservation, ...] = ()
    context: NormalizationContext
