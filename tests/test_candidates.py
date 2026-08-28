from __future__ import annotations

from datetime import UTC, datetime

from yandex_analytics_reaper.candidates import (
    CandidateDecision,
    CandidateDecisionRecord,
    DecisionValidationStatus,
    EvidenceCoverage,
    MarketPriorStrength,
    ProductionFit,
)


def test_candidate_decision_dimensions_are_not_interchangeable() -> None:
    decision = CandidateDecisionRecord(
        candidate_id="management-school",
        decision=CandidateDecision.WATCH,
        decision_version="1",
        validation_status=DecisionValidationStatus.HEURISTIC,
        decided_at=datetime(2026, 8, 28, tzinfo=UTC),
        market_prior=MarketPriorStrength.FAVORABLE,
        production_fit=ProductionFit.STRONG,
        evidence_coverage=EvidenceCoverage.MEDIUM,
        watch_triggers=("collect another week of market observations",),
    )

    assert decision.market_prior is MarketPriorStrength.FAVORABLE
    assert decision.production_fit is ProductionFit.STRONG
    assert decision.evidence_coverage is EvidenceCoverage.MEDIUM
    assert decision.validation_status is DecisionValidationStatus.HEURISTIC
