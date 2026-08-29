from __future__ import annotations

from pydantic import BaseModel, ConfigDict, model_validator

from yandex_analytics_reaper.domain import (
    ListingMediaObservation,
    ListingStatusObservation,
    ListingUpdateObservation,
)
from yandex_analytics_reaper.evidence import FieldLineage


class NormalizedListingUpdate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    observation: ListingUpdateObservation
    lineage: tuple[FieldLineage, ...]


class NormalizedListingStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    observation: ListingStatusObservation
    lineage: tuple[FieldLineage, ...]


class NormalizedListingMedia(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    observation: ListingMediaObservation
    lineage: tuple[FieldLineage, ...]


class NormalizedListingHistories(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    update: NormalizedListingUpdate | None = None
    status: NormalizedListingStatus | None = None
    media: NormalizedListingMedia | None = None

    @model_validator(mode="after")
    def require_history_observation(self) -> "NormalizedListingHistories":
        if self.update is None and self.status is None and self.media is None:
            raise ValueError("normalized listing histories cannot be empty")
        return self
