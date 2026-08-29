from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from yandex_analytics_reaper.domain import (
    GameMetricName,
    GameMetricObservation,
    Platform,
    PlatformListing,
)
from yandex_analytics_reaper.evidence import EvidenceEnvelope, MeasurementKind, Provenance
from yandex_analytics_reaper.storage import (
    MetricWrite,
    SQLiteIdentityStore,
    SQLiteLineageStore,
    SQLiteMetricStore,
)


def test_v2_metric_database_migrates_to_lineage_schema_without_data_loss(
    tmp_path: Path,
) -> None:
    path = tmp_path / "market.sqlite3"
    observed_at = datetime(2026, 8, 29, 4, 0, tzinfo=UTC)

    SQLiteIdentityStore(path).persist_listing_identity(
        PlatformListing(
            id="yandex_games:1",
            platform=Platform.YANDEX_GAMES,
            external_app_id="1",
        ),
        None,
        observed_at,
    )
    metric_store = SQLiteMetricStore(path)
    metric_store.persist_metric(
        MetricWrite(
            metric=GameMetricObservation(
                platform_listing_id="yandex_games:1",
                observed_at=observed_at,
                metric_name=GameMetricName.YANDEX_GAMES_RATING,
                value=80,
            ),
            evidence=EvidenceEnvelope(
                source_id="yandex_public",
                observed_at=observed_at,
                available_at=observed_at,
                retrieved_at=observed_at + timedelta(seconds=1),
                provenance=Provenance.FIRST_PARTY,
                measurement_kind=MeasurementKind.OBSERVED,
            ),
            normalizer_name="YandexGameNormalizer",
            normalizer_version="2",
        )
    )

    with sqlite3.connect(path) as connection:
        connection.execute("DROP TABLE collection_cadence_plan_checkpoints")
        connection.execute("DROP TABLE collection_cadence_plan_listings")
        connection.execute("DROP TABLE collection_cadence_plans")
        connection.execute("DROP TABLE listing_media_observations")
        connection.execute("DROP TABLE listing_status_observations")
        connection.execute("DROP TABLE listing_update_observations")
        connection.execute("DROP TABLE listing_history_evidence")
        connection.execute("DROP TABLE comparable_set_member_evidence")
        connection.execute("DROP TABLE comparable_set_members")
        connection.execute("DROP TABLE comparable_set_runs")
        connection.execute("DROP TABLE comparable_set_versions")
        connection.execute("DROP TABLE query_family_members")
        connection.execute("DROP TABLE query_family_versions")
        connection.execute("DROP TABLE probe_pages")
        connection.execute("DROP TABLE probe_runs")
        connection.execute("DROP TABLE probe_contexts")
        connection.execute("DROP TABLE schema_drift_events")
        connection.execute("DROP TABLE schema_field_profiles")
        connection.execute("DROP TABLE schema_observations")
        connection.execute("DROP TABLE observation_lineage")
        connection.execute("PRAGMA user_version = 2")

    lineage_store = SQLiteLineageStore(path)

    assert len(SQLiteMetricStore(path).metric_history("yandex_games:1")) == 1
    assert lineage_store.for_observation("missing") == ()
    with sqlite3.connect(path) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()
        assert version is not None
        assert version[0] == 10
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert {
            "observation_lineage",
            "schema_observations",
            "probe_contexts",
            "query_family_versions",
            "comparable_set_versions",
            "listing_history_evidence",
            "collection_cadence_plans",
        } <= tables
