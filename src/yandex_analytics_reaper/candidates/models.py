from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class CandidateDecision(StrEnum):
    BUILD = "build"
    WATCH = "watch"
    SKIP = "skip"


class DecisionValidationStatus(StrEnum):
    HEURISTIC = "heuristic"
    BACKTEST_VALIDATED = "backtest_validated"
    PORTFOLIO_CALIBRATED = "portfolio_calibrated"


class MarketPriorStrength(StrEnum):
    STRONG_FAVORABLE = "strong_favorable"
    FAVORABLE = "favorable"
    MIXED = "mixed"
    UNFAVORABLE = "unfavorable"
    STRONG_UNFAVORABLE = "strong_unfavorable"
    UNKNOWN = "unknown"


class ProductionFit(StrEnum):
    STRONG = "strong"
    ACCEPTABLE = "acceptable"
    WEAK = "weak"
    BLOCKING = "blocking"
    UNKNOWN = "unknown"


class EvidenceCoverage(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INSUFFICIENT = "insufficient"


class CandidateDecisionRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidate_id: str
    decision: CandidateDecision
    decision_version: str
    validation_status: DecisionValidationStatus
    decided_at: datetime
    market_prior: MarketPriorStrength
    production_fit: ProductionFit
    evidence_coverage: EvidenceCoverage
    supporting_evidence: tuple[str, ...] = ()
    counter_evidence: tuple[str, ...] = ()
    unknowns: tuple[str, ...] = ()
    review_at: datetime | None = None
    watch_triggers: tuple[str, ...] = ()
