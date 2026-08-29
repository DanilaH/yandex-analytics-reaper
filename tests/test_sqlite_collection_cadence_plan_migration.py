from __future__ import annotations

import sqlite3
from pathlib import Path

from yandex_analytics_reaper.storage import SQLiteCollectionCadencePlanStore


def test_v9_database_migrates_to_collection_cadence_plan_schema(tmp_path: Path) -> None:
    path = tmp_path / "market.sqlite3"
    SQLiteCollectionCadencePlanStore(path)

    with sqlite3.connect(path) as connection:
        connection.execute("DROP TABLE listing_state_observations")
        connection.execute("DROP TABLE collection_cadence_plan_checkpoints")
        connection.execute("DROP TABLE collection_cadence_plan_listings")
        connection.execute("DROP TABLE collection_cadence_plans")
        connection.execute("PRAGMA user_version = 9")

    SQLiteCollectionCadencePlanStore(path)

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
            "collection_cadence_plans",
            "collection_cadence_plan_listings",
            "collection_cadence_plan_checkpoints",
            "listing_state_observations",
        } <= tables
