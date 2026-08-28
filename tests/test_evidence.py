from __future__ import annotations

from datetime import UTC, datetime

from yandex_analytics_reaper.evidence import (
    CoverageStatus,
    EvidenceEnvelope,
    HistoricalAvailability,
    MeasurementKind,
    Provenance,
    RevisionStatus,
    SemanticConfidence,
)


def test_evidence_dimensions_are_independent() -> None:
    observed_at = datetime(2025, 5, 1, tzinfo=UTC)
    available_at = datetime(2025, 5, 3, tzinfo=UTC)
    retrieved_at = datetime(2026, 8, 28, tzinfo=UTC)

    evidence = EvidenceEnvelope(
        source_id="spymagic",
        observed_at=observed_at,
        available_at=available_at,
        retrieved_at=retrieved_at,
        provenance=Provenance.THIRD_PARTY,
        measurement_kind=MeasurementKind.ESTIMATED,
        semantic_confidence=SemanticConfidence.MEDIUM,
        coverage_status=CoverageStatus.PARTIAL,
        historical_availability=HistoricalAvailability.RECONSTRUCTED,
        revision_status=RevisionStatus.RETROACTIVELY_RECALCULATED,
    )

    assert evidence.provenance is Provenance.THIRD_PARTY
    assert evidence.measurement_kind is MeasurementKind.ESTIMATED
    assert evidence.observed_at == observed_at
    assert evidence.available_at == available_at
    assert evidence.retrieved_at == retrieved_at
    assert evidence.historical_availability is HistoricalAvailability.RECONSTRUCTED
    assert evidence.revision_status is RevisionStatus.RETROACTIVELY_RECALCULATED
