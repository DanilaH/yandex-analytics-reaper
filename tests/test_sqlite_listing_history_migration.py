from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from yandex_analytics_reaper.domain import Platform, PlatformListing
from yandex_analytics_reaper.storage import SQLiteIdentityStore, SQLiteListingHistoryStore


def test_v8_database_migrates_to_listing_history_schema_without_identity_loss(
    tmp_path: Path,
) -> None:
    path = tmp_path / "market.sqlite3"
    observed_at = datetime(2026, 8, 29, 9, 0, tzinfo=UTC)
    SQLiteIdentityStore(path).persist_listing_identity(
        PlatformListing(
            id="yandex_games:1",
            platform=Platform.YANDEX_GAMES,
            external_app_id="1",
        ),
        None,
        observed_at,
    )

    with sqlite3.connect(path) as connection:
        connection.execute("DROP TABLE listing_media_observations")
        connection.execute("DROP TABLE listing_status_observations")
        connection.execute("DROP TABLE listing_update_observations")
        connection.execute("DROP TABLE listing_history_evidence")
        connection.execute("PRAGMA user_version = 8")

    SQLiteListingHistoryStore(path)

    listing = SQLiteIdentityStore(path).get_listing("yandex_games:1")
    assert listing is not None
    assert listing.external_app_id == "1"
    with sqlite3.connect(path) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()
        assert version is not None
        assert version[0] == 9
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert {
            "listing_history_evidence",
            "listing_update_observations",
            "listing_status_observations",
            "listing_media_observations",
        } <= tables
