from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from yandex_analytics_reaper.domain import (
    GameMetricName,
    GameMetricObservation,
    Platform,
    PlatformListing,
)
from yandex_analytics_reaper.evidence import (
    CoverageStatus,
    EvidenceEnvelope,
    FieldLineage,
    HistoricalAvailability,
    MeasurementKind,
    Provenance,
    RevisionStatus,
    SemanticConfidence,
)
from yandex_analytics_reaper.storage import (
    MetricWrite,
    SQLiteIdentityStore,
    SQLiteLineageStore,
    SQLiteMetricStore,
)


def _prepare(path: Path) -> SQLiteMetricStore:
    SQLiteIdentityStore(path).persist_listing_identity(
        PlatformListing(
            id="yandex_games:438560",
            platform=Platform.YANDEX_GAMES,
            external_app_id="438560",
        ),
        None,
        datetime(2026, 8, 29, 0, 0, tzinfo=UTC),
    )
    return SQLiteMetricStore(path)


def _lineage(*, version: str = "1", source_path: str | None = None) -> FieldLineage:
    return FieldLineage(
        raw_snapshot_id="20260829T000000000000Z-abc123",
        source_field_path=(source_path or "$.games[0].gqRating"),
        target_field_path="game_metric_observations.value_numeric",
        transformation_name="YandexGameNormalizer.yandex_games_rating",
        transformation_version=version,
    )


def _write(
    *,
    observed_at: datetime,
    value: int = 86,
    lineage: tuple[FieldLineage, ...] | None = None,
) -> MetricWrite:
    metric = GameMetricObservation(
        platform_listing_id="yandex_games:438560",
        observed_at=observed_at,
        metric_name=GameMetricName.YANDEX_GAMES_RATING,
        value=value,
    )
    evidence = EvidenceEnvelope(
        source_id="yandex_public",
        observed_at=observed_at,
        available_at=observed_at,
        retrieved_at=observed_at + timedelta(seconds=1),
        provenance=Provenance.FIRST_PARTY,
        measurement_kind=MeasurementKind.OBSERVED,
        semantic_confidence=SemanticConfidence.HIGH,
        coverage_status=CoverageStatus.COMPLETE,
        historical_availability=HistoricalAvailability.POINT_IN_TIME,
        revision_status=RevisionStatus.IMMUTABLE,
    )
    return MetricWrite(
        metric=metric,
        evidence=evidence,
        normalizer_name="YandexGameNormalizer",
        normalizer_version="1",
        lineage=lineage if lineage is not None else (_lineage(),),
    )


def test_metric_write_persists_field_lineage_atomically(tmp_path: Path) -> None:
    path = tmp_path / "market.sqlite3"
    metric_store = _prepare(path)
    lineage_store = SQLiteLineageStore(path)
    observed_at = datetime(2026, 8, 29, 1, 0, tzinfo=UTC)

    observation_id = metric_store.persist_metric(_write(observed_at=observed_at))
    records = lineage_store.for_observation(observation_id)

    assert len(records) == 1
    record = records[0]
    assert record.raw_snapshot_id == "20260829T000000000000Z-abc123"
    assert record.source_field_path == "$.games[0].gqRating"
    assert record.target_field_path == "game_metric_observations.value_numeric"
    assert record.transformation_name == "YandexGameNormalizer.yandex_games_rating"
    assert record.transformation_version == "1"


def test_repeated_same_metric_and_lineage_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "market.sqlite3"
    metric_store = _prepare(path)
    lineage_store = SQLiteLineageStore(path)
    write = _write(observed_at=datetime(2026, 8, 29, 1, 0, tzinfo=UTC))

    first = metric_store.persist_metric(write)
    second = metric_store.persist_metric(write)

    assert first == second
    assert len(lineage_store.for_observation(first)) == 1


def test_conflicting_transformation_cannot_rewrite_existing_lineage(tmp_path: Path) -> None:
    path = tmp_path / "market.sqlite3"
    metric_store = _prepare(path)
    lineage_store = SQLiteLineageStore(path)
    observed_at = datetime(2026, 8, 29, 1, 0, tzinfo=UTC)
    first_write = _write(observed_at=observed_at, lineage=(_lineage(version="1"),))
    observation_id = metric_store.persist_metric(first_write)

    with pytest.raises(ValueError, match="conflicting lineage transformation"):
        metric_store.persist_metric(
            _write(observed_at=observed_at, lineage=(_lineage(version="2"),))
        )

    records = lineage_store.for_observation(observation_id)
    assert len(records) == 1
    assert records[0].transformation_version == "1"


def test_duplicate_lineage_key_rolls_back_new_metric(tmp_path: Path) -> None:
    path = tmp_path / "market.sqlite3"
    metric_store = _prepare(path)
    observed_at = datetime(2026, 8, 29, 1, 0, tzinfo=UTC)
    item = _lineage()

    with pytest.raises(ValueError, match="duplicate lineage key"):
        metric_store.persist_metric(_write(observed_at=observed_at, lineage=(item, item)))

    assert metric_store.metric_history("yandex_games:438560") == ()


def test_lineage_store_rejects_unknown_observation(tmp_path: Path) -> None:
    store = SQLiteLineageStore(tmp_path / "market.sqlite3")

    with pytest.raises(ValueError, match="does not exist"):
        store.persist_lineage("metric:missing", (_lineage(),))


def test_field_lineage_requires_field_paths() -> None:
    with pytest.raises(ValueError, match="source_field_path"):
        FieldLineage(
            raw_snapshot_id="raw-1",
            source_field_path="games.gqRating",
            target_field_path="game_metric_observations.value_numeric",
            transformation_name="normalize",
            transformation_version="1",
        )
