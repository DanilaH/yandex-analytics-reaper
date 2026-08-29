from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from yandex_analytics_reaper.domain import Platform, PlatformListing
from yandex_analytics_reaper.schema_drift import SQLiteSchemaDriftRegistry
from yandex_analytics_reaper.storage import SQLiteIdentityStore


def test_v3_database_migrates_to_schema_drift_registry_without_identity_loss(
    tmp_path: Path,
) -> None:
    path = tmp_path / "market.sqlite3"
    observed_at = datetime(2026, 8, 29, 6, 0, tzinfo=UTC)
    identity_store = SQLiteIdentityStore(path)
    identity_store.persist_listing_identity(
        PlatformListing(
            id="yandex_games:438560",
            platform=Platform.YANDEX_GAMES,
            external_app_id="438560",
        ),
        None,
        observed_at,
    )

    with sqlite3.connect(path) as connection:
        connection.execute("DROP TABLE listing_state_observations")
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
        connection.execute("PRAGMA user_version = 3")

    SQLiteSchemaDriftRegistry(path)

    listing = SQLiteIdentityStore(path).get_listing("yandex_games:438560")
    assert listing is not None
    assert listing.external_app_id == "438560"
    with sqlite3.connect(path) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()
        assert version is not None
        assert version[0] == 12
        columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(schema_observations)").fetchall()
        }
        assert "comparison_scope_id" in columns
        assert "content_hash" in columns
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert {
            "probe_contexts",
            "query_family_versions",
            "comparable_set_versions",
            "listing_history_evidence",
            "collection_cadence_plans",
            "listing_state_observations",
        } <= tables
