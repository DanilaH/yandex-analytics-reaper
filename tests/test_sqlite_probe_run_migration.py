from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from yandex_analytics_reaper.domain import Platform, PlatformListing
from yandex_analytics_reaper.storage import SQLiteIdentityStore, SQLiteProbeRunStore


def test_v4_database_migrates_to_probe_run_schema_without_identity_loss(
    tmp_path: Path,
) -> None:
    path = tmp_path / "market.sqlite3"
    observed_at = datetime(2026, 8, 29, 9, 0, tzinfo=UTC)
    SQLiteIdentityStore(path).persist_listing_identity(
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
        connection.execute("DROP TABLE probe_pages")
        connection.execute("DROP TABLE probe_runs")
        connection.execute("DROP TABLE probe_contexts")
        connection.execute("DROP TABLE query_family_members")
        connection.execute("DROP TABLE query_family_versions")
        connection.execute("PRAGMA user_version = 4")

    SQLiteProbeRunStore(path)

    listing = SQLiteIdentityStore(path).get_listing("yandex_games:438560")
    assert listing is not None
    assert listing.external_app_id == "438560"
    with sqlite3.connect(path) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()
        assert version is not None
        assert version[0] == 12
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert {
            "probe_contexts",
            "probe_runs",
            "probe_pages",
            "query_family_versions",
            "query_family_members",
            "comparable_set_versions",
            "comparable_set_runs",
            "comparable_set_members",
            "comparable_set_member_evidence",
            "listing_history_evidence",
            "collection_cadence_plans",
            "listing_state_observations",
        } <= tables

        context_columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(probe_contexts)").fetchall()
        }
        assert "session_instance_id" in context_columns

        run_columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(probe_runs)").fetchall()
        }
        assert "error_raw_snapshot_id" in run_columns

        page_columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(probe_pages)").fetchall()
        }
        assert {"source_id", "raw_snapshot_id"} <= page_columns

        indexes = connection.execute("PRAGMA index_list(probe_pages)").fetchall()
        unique_column_sets: set[tuple[str, ...]] = set()
        index_columns: dict[str, tuple[str, ...]] = {}
        for index in indexes:
            index_name = str(index[1])
            columns = tuple(
                str(row[2])
                for row in connection.execute(
                    f"PRAGMA index_info('{index_name}')"
                ).fetchall()
            )
            index_columns[index_name] = columns
            if bool(index[2]):
                unique_column_sets.add(columns)

        assert ("source_id", "raw_snapshot_id") in unique_column_sets
        assert index_columns["idx_probe_pages_snapshot"] == (
            "source_id",
            "raw_snapshot_id",
            "run_id",
            "page_index",
        )
