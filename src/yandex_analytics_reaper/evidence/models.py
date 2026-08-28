from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class Provenance(StrEnum):
    FIRST_PARTY = "first_party"
    THIRD_PARTY = "third_party"
    INTERNAL = "internal"


class MeasurementKind(StrEnum):
    OBSERVED = "observed"
    ESTIMATED = "estimated"
    DERIVED = "derived"
    INFERRED = "inferred"
    EDITORIAL = "editorial"


class SemanticConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class FreshnessStatus(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    HISTORICAL = "historical"
    UNKNOWN = "unknown"


class CoverageStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    SAMPLED = "sampled"
    UNKNOWN = "unknown"


class PointInTimeIntegrity(StrEnum):
    STRICT_POINT_IN_TIME = "strict_point_in_time"
    HISTORICAL_SNAPSHOT = "historical_snapshot"
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


class EvidenceEnvelope(BaseModel):
    """Independent evidence-quality dimensions; never collapse to one grade."""

    model_config = ConfigDict(frozen=True)

    source_id: str
    observed_at: datetime
    period_start: datetime | None = None
    period_end: datetime | None = None
    provenance: Provenance
    measurement_kind: MeasurementKind
    semantic_confidence: SemanticConfidence = SemanticConfidence.UNKNOWN
    freshness_status: FreshnessStatus = FreshnessStatus.UNKNOWN
    coverage_status: CoverageStatus = CoverageStatus.UNKNOWN
    point_in_time_integrity: PointInTimeIntegrity = PointInTimeIntegrity.UNKNOWN
    uncertainty: Uncertainty | None = None
    lineage_refs: tuple[str, ...] = ()
