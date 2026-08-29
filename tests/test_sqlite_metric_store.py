from __future__ import annotations

import sqlite3
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
    HistoricalAvailability,
    MeasurementKind,
    Provenance,
    RevisionStatus,
    SemanticConfidence,
)
from yandex_analytics_reaper.storage import MetricWrite, SQLiteIdentityStore, SQLiteMetricStore


def _listing() -> PlatformListing:
    return PlatformListing(
        id="yandex_games:438560",
        platform=Platform.YANDEX_GAMES,
        external_app_id="438560",
        listing_url="https://yandex.ru/games/app/438560",
    )


def _write(
    *,
    observed_at: datetime,
    retrieved_at: datetime | None = None,
    value: int | float = 86,
    metric_name: GameMetricName = GameMetricName.YANDEX_GAMES_RATING,
) -> MetricWrite:
    retrieved = retrieved_at or observed_at + timedelta(seconds=1)
    metric = GameMetricObservation(
        platform_listing_id="yandex_games:438560",
        observed_at=observed_at,
        metric_name=metric_name,
        value=value,
    )
    evidence = EvidenceEnvelope(
        source_id="yandex_public",
        observed_at=observed_at,
        available_at=observed_at,
        retrieved_at=retrieved,
        provenance=Provenance.FIRST_PARTY,
        measurement_kind=MeasurementKind.OBSERVED,
        semantic_confidence=SemanticConfidence.HIGH,
        coverage_status=CoverageStatus.COMPLETE,
        historical_availability=HistoricalAvailability.POINT_IN_TIME,
        revision_status=RevisionStatus.IMMUTABLE,
        lineage_refs=("raw:test",),
    )
    return MetricWrite(
        metric=metric,
        evidence=evidence,
        normalizer_name="YandexGameNormalizer",
        normalizer_version="1",
    )


def test_metric_store_round_trips_evidence_and_value(tmp_path: Path) -> None:
    path = tmp_path / "market.sqlite3"
    SQLiteIdentityStore(path).persist_listing_identity(
        _listing(),
        None,
        datetime(2026, 8, 29, 0, 0, tzinfo=UTC),
    )
    store = SQLiteMetricStore(path)
    observed_at = datetime(2026, 8, 29, 1, 0, tzinfo=UTC)

    observation_id = store.persist_metric(_write(observed_at=observed_at))
    history = store.metric_history(
        "yandex_games:438560",
        GameMetricName.YANDEX_GAMES_RATING,
    )

    assert len(history) == 1
    persisted = history[0]
    assert persisted.observation_id == observation_id
    assert persisted.metric.value == 86
    assert persisted.metric.observed_at == observed_at
    assert persisted.evidence.source_id == "yandex_public"
    assert persisted.evidence.lineage_refs == ("raw:test",)
    assert persisted.normalizer_name == "YandexGameNormalizer"
    assert persisted.normalizer_version == "1"


def test_metric_store_is_idempotent_for_same_semantic_observation(tmp_path: Path) -> None:
    path = tmp_path / "market.sqlite3"
    SQLiteIdentityStore(path).persist_listing_identity(
        _listing(),
        None,
        datetime(2026, 8, 29, 0, 0, tzinfo=UTC),
    )
    store = SQLiteMetricStore(path)
    write = _write(observed_at=datetime(2026, 8, 29, 1, 0, tzinfo=UTC))

    first = store.persist_metric(write)
    second = store.persist_metric(write)

    assert first == second
    assert len(store.metric_history("yandex_games:438560")) == 1


def test_metric_store_rejects_conflicting_value_for_same_observation(tmp_path: Path) -> None:
    path = tmp_path / "market.sqlite3"
    SQLiteIdentityStore(path).persist_listing_identity(
        _listing(),
        None,
        datetime(2026, 8, 29, 0, 0, tzinfo=UTC),
    )
    store = SQLiteMetricStore(path)
    observed_at = datetime(2026, 8, 29, 1, 0, tzinfo=UTC)
    store.persist_metric(_write(observed_at=observed_at, value=86))

    with pytest.raises(ValueError, match="conflicting metric observation"):
        store.persist_metric(_write(observed_at=observed_at, value=72))

    history = store.metric_history("yandex_games:438560")
    assert len(history) == 1
    assert history[0].metric.value == 86


def test_metric_batch_is_atomic_when_later_write_conflicts(tmp_path: Path) -> None:
    path = tmp_path / "market.sqlite3"
    SQLiteIdentityStore(path).persist_listing_identity(
        _listing(),
        None,
        datetime(2026, 8, 29, 0, 0, tzinfo=UTC),
    )
    store = SQLiteMetricStore(path)
    conflict_time = datetime(2026, 8, 29, 1, 0, tzinfo=UTC)
    store.persist_metric(_write(observed_at=conflict_time, value=86))

    new_time = conflict_time + timedelta(hours=1)
    with pytest.raises(ValueError, match="conflicting metric observation"):
        store.persist_metrics(
            (
                _write(observed_at=new_time, value=90),
                _write(observed_at=conflict_time, value=72),
            )
        )

    history = store.metric_history("yandex_games:438560")
    assert [item.metric.value for item in history] == [86]


def test_metric_store_orders_out_of_order_backfill_by_observed_time(tmp_path: Path) -> None:
    path = tmp_path / "market.sqlite3"
    SQLiteIdentityStore(path).persist_listing_identity(
        _listing(),
        None,
        datetime(2026, 8, 27, 0, 0, tzinfo=UTC),
    )
    store = SQLiteMetricStore(path)
    earlier = datetime(2026, 8, 28, 1, 0, tzinfo=UTC)
    later = earlier + timedelta(days=1)

    store.persist_metric(_write(observed_at=later, value=90))
    store.persist_metric(_write(observed_at=earlier, value=80))

    assert [item.metric.value for item in store.metric_history("yandex_games:438560")] == [
        80,
        90,
    ]


def test_metric_store_requires_persisted_listing(tmp_path: Path) -> None:
    store = SQLiteMetricStore(tmp_path / "market.sqlite3")

    with pytest.raises(ValueError, match="must be persisted before metrics"):
        store.persist_metric(
            _write(observed_at=datetime(2026, 8, 29, 1, 0, tzinfo=UTC))
        )


def test_metric_write_requires_matching_observation_time() -> None:
    observed_at = datetime(2026, 8, 29, 1, 0, tzinfo=UTC)
    metric = GameMetricObservation(
        platform_listing_id="yandex_games:438560",
        observed_at=observed_at,
        metric_name=GameMetricName.YANDEX_GAMES_RATING,
        value=86,
    )
    evidence = EvidenceEnvelope(
        source_id="yandex_public",
        observed_at=observed_at + timedelta(seconds=1),
        retrieved_at=observed_at + timedelta(seconds=2),
        provenance=Provenance.FIRST_PARTY,
        measurement_kind=MeasurementKind.OBSERVED,
    )

    with pytest.raises(ValueError, match="observed_at must match"):
        MetricWrite(
            metric=metric,
            evidence=evidence,
            normalizer_name="YandexGameNormalizer",
            normalizer_version="1",
        )


def test_metric_write_requires_retrieval_time() -> None:
    observed_at = datetime(2026, 8, 29, 1, 0, tzinfo=UTC)
    metric = GameMetricObservation(
        platform_listing_id="yandex_games:438560",
        observed_at=observed_at,
        metric_name=GameMetricName.YANDEX_GAMES_RATING,
        value=86,
    )
    evidence = EvidenceEnvelope(
        source_id="yandex_public",
        observed_at=observed_at,
        provenance=Provenance.FIRST_PARTY,
        measurement_kind=MeasurementKind.OBSERVED,
    )

    with pytest.raises(ValueError, match="requires retrieved_at"):
        MetricWrite(
            metric=metric,
            evidence=evidence,
            normalizer_name="YandexGameNormalizer",
            normalizer_version="1",
        )


def test_metric_write_rejects_observation_after_retrieval() -> None:
    observed_at = datetime(2026, 8, 29, 1, 0, tzinfo=UTC)

    with pytest.raises(ValueError, match="observed_at cannot be later"):
        _write(
            observed_at=observed_at,
            retrieved_at=observed_at - timedelta(seconds=1),
        )


def test_metric_domain_rejects_coerced_or_non_finite_values() -> None:
    base = {
        "platform_listing_id": "yandex_games:438560",
        "observed_at": datetime(2026, 8, 29, 1, 0, tzinfo=UTC),
        "metric_name": GameMetricName.RATING_COUNT,
    }
    for value in (True, "86", float("nan"), float("inf")):
        with pytest.raises(ValueError, match="metric value"):
            GameMetricObservation(**base, value=value)


def test_v1_identity_database_migrates_to_metric_schema_without_data_loss(
    tmp_path: Path,
) -> None:
    path = tmp_path / "market.sqlite3"
    identity = SQLiteIdentityStore(path)
    observed_at = datetime(2026, 8, 29, 0, 0, tzinfo=UTC)
    identity.persist_listing_identity(_listing(), None, observed_at)

    with sqlite3.connect(path) as connection:
        connection.execute("DROP TABLE game_metric_observations")
        connection.execute("DROP TABLE normalized_observations")
        connection.execute("PRAGMA user_version = 1")

    store = SQLiteMetricStore(path)
    store.persist_metric(_write(observed_at=observed_at + timedelta(hours=1)))

    listing = SQLiteIdentityStore(path).get_listing("yandex_games:438560")
    assert listing is not None
    assert listing.external_app_id == "438560"
    assert len(store.metric_history(listing.id)) == 1
