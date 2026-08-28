from __future__ import annotations

from datetime import UTC, datetime

from yandex_analytics_reaper.evidence import (
    CoverageStatus,
    EvidenceEnvelope,
    MeasurementKind,
    PointInTimeIntegrity,
    Provenance,
    SemanticConfidence,
)


def test_evidence_dimensions_are_independent() -> None:
    evidence = EvidenceEnvelope(
        source_id="spymagic",
        observed_at=datetime(2026, 8, 28, tzinfo=UTC),
        provenance=Provenance.THIRD_PARTY,
        measurement_kind=MeasurementKind.ESTIMATED,
        semantic_confidence=SemanticConfidence.MEDIUM,
        coverage_status=CoverageStatus.PARTIAL,
        point_in_time_integrity=PointInTimeIntegrity.RETROACTIVELY_RECALCULATED,
    )

    assert evidence.provenance is Provenance.THIRD_PARTY
    assert evidence.measurement_kind is MeasurementKind.ESTIMATED
    assert evidence.point_in_time_integrity is PointInTimeIntegrity.RETROACTIVELY_RECALCULATED
