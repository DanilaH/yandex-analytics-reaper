from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from yandex_analytics_reaper.domain import Platform, PlatformListing
from yandex_analytics_reaper.storage import SQLiteIdentityStore, SQLiteListingStateStore


def test_v10_database_migrates_to_listing_state_schema_without_identity_loss(
    tmp_path: Path,
) -> None:
    path = tmp_path / "market.sqlite3"
    SQLiteIdentityStore(path).persist_listing_identity(
        PlatformListing(
            id="yandex_games:1",
            platform=Platform.YANDEX_GAMES,
            external_app_id="1",
        ),
        None,
        datetime(2026, 8, 29, 9, 0, tzinfo=UTC),
    )

    with sqlite3.connect(path) as connection:
        connection.execute("DROP TABLE listing_state_observations")
        connection.execute("PRAGMA user_version = 10")

    SQLiteListingStateStore(path)

    listing = SQLiteIdentityStore(path).get_listing("yandex_games:1")
    assert listing is not None
    assert listing.external_app_id == "1"
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
        assert "listing_state_observations" in tables
        columns = {
            str(row[1])
            for row in connection.execute(
                "PRAGMA table_info(listing_state_observations)"
            ).fetchall()
        }
        assert {
            "title",
            "developer_id",
            "developer_name",
            "first_published_at",
            "published_at",
            "languages_json",
            "supported_platforms_json",
            "leaderboards",
            "rewarded_ads",
        } <= columns
