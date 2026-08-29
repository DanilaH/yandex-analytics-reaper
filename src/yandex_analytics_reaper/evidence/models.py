from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class Provenance(StrEnum):
    FIRST_PARTY = "first_party"
    THIRD_PARTY = "third_party"
    INTERNAL = "internal"


class MeasurementKind(StrEnum):
    OBSERVED = "observed"
    ESTIMATED = "estimated"
    DERIVED = "derived"
    INFERRED = "inferred"


class SemanticConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class CoverageStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    SAMPLED = "sampled"
    UNKNOWN = "unknown"


class HistoricalAvailability(StrEnum):
    POINT_IN_TIME = "point_in_time"
    RECONSTRUCTED = "reconstructed"
    UNKNOWN = "unknown"


class RevisionStatus(StrEnum):
    IMMUTABLE = "immutable"
    REVISED = "revised"
    RETROACTIVELY_RECALCULATED = "retroactively_recalculated"
    UNKNOWN = "unknown"


class MissingReason(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    NOT_SUPPORTED = "not_supported"
    NOT_OBSERVED = "not_observed"
    SOURCE_MISSING = "source_missing"
    SOURCE_ERROR = "source_error"
    PERMISSION_BLOCKED = "permission_blocked"
    UNKNOWN_SEMANTICS = "unknown_semantics"
    UNKNOWN = "unknown"


class Uncertainty(BaseModel):
    model_config = ConfigDict(frozen=True)

    lower: float | None = None
    point: float | None = None
    upper: float | None = None
    confidence_level: float | None = None


class FieldLineage(BaseModel):
    """One raw source field → persisted target field transformation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    raw_snapshot_id: str
    source_field_path: str
    target_field_path: str
    transformation_name: str
    transformation_version: str

    @field_validator(
        "raw_snapshot_id",
        "source_field_path",
        "target_field_path",
        "transformation_name",
        "transformation_version",
    )
    @classmethod
    def require_non_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("lineage fields cannot be blank")
        return stripped

    @model_validator(mode="after")
    def validate_paths(self) -> Self:
        if not self.source_field_path.startswith("$"):
            raise ValueError("source_field_path must start with '$'")
        if "." not in self.target_field_path:
            raise ValueError("target_field_path must identify a persisted table field")
        return self


class EvidenceEnvelope(BaseModel):
    """Independent evidence-quality dimensions; never collapse to one grade."""

    model_config = ConfigDict(frozen=True)

    source_id: str
    observed_at: datetime
    available_at: datetime | None = None
    retrieved_at: datetime | None = None
    period_start: datetime | None = None
    period_end: datetime | None = None
    provenance: Provenance
    measurement_kind: MeasurementKind
    semantic_confidence: SemanticConfidence = SemanticConfidence.UNKNOWN
    coverage_status: CoverageStatus = CoverageStatus.UNKNOWN
    historical_availability: HistoricalAvailability = HistoricalAvailability.UNKNOWN
    revision_status: RevisionStatus = RevisionStatus.UNKNOWN
    uncertainty: Uncertainty | None = None
    lineage_refs: tuple[str, ...] = ()
