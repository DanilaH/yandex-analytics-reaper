from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class CandidateDecision(StrEnum):
    BUILD = "build"
    WATCH = "watch"
    SKIP = "skip"


class DecisionStrength(StrEnum):
    STRONG = "strong"
    FAVORABLE = "favorable"
    MIXED = "mixed"
    WEAK = "weak"
    UNKNOWN = "unknown"


class CandidateDecisionRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidate_id: str
    decision: CandidateDecision
    decision_version: str
    decided_at: datetime
    market_prior: DecisionStrength
    production_fit: DecisionStrength
    evidence_coverage: DecisionStrength
    supporting_evidence: tuple[str, ...] = ()
    counter_evidence: tuple[str, ...] = ()
    unknowns: tuple[str, ...] = ()
    review_at: datetime | None = None
    watch_triggers: tuple[str, ...] = ()
