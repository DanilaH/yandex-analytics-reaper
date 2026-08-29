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
        connection.execute("DROP TABLE probe_pages")
        connection.execute("DROP TABLE probe_runs")
        connection.execute("DROP TABLE probe_contexts")
        connection.execute("PRAGMA user_version = 4")

    SQLiteProbeRunStore(path)

    listing = SQLiteIdentityStore(path).get_listing("yandex_games:438560")
    assert listing is not None
    assert listing.external_app_id == "438560"
    with sqlite3.connect(path) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()
        assert version is not None
        assert version[0] == 5
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert {"probe_contexts", "probe_runs", "probe_pages"} <= tables
