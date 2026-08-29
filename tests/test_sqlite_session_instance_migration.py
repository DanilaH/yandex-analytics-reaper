from __future__ import annotations

import sqlite3
from pathlib import Path

from yandex_analytics_reaper.storage import SQLiteProbeRunStore


def test_v5_probe_contexts_migrate_to_nullable_session_instance_id(tmp_path: Path) -> None:
    path = tmp_path / "market.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE probe_contexts (
                id TEXT PRIMARY KEY,
                language TEXT NOT NULL,
                device_type TEXT NOT NULL,
                platform TEXT NOT NULL,
                country_observed TEXT,
                collector_region TEXT,
                session_profile TEXT NOT NULL,
                cookie_state_hash TEXT,
                profile_age_days INTEGER,
                CHECK (profile_age_days IS NULL OR profile_age_days >= 0)
            );
            INSERT INTO probe_contexts (
                id,
                language,
                device_type,
                platform,
                session_profile,
                cookie_state_hash,
                profile_age_days
            ) VALUES (
                'probe-context:legacy',
                'ru',
                'desktop',
                'desktop_other',
                'persistent_anonymous',
                'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                2
            );
            PRAGMA user_version = 5;
            """
        )

    SQLiteProbeRunStore(path)

    with sqlite3.connect(path) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()
        assert version is not None
        assert version[0] == 6
        columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(probe_contexts)").fetchall()
        }
        assert "session_instance_id" in columns
        row = connection.execute(
            "SELECT language, session_profile, cookie_state_hash, profile_age_days, "
            "session_instance_id FROM probe_contexts WHERE id = 'probe-context:legacy'"
        ).fetchone()
        assert row == (
            "ru",
            "persistent_anonymous",
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            2,
            None,
        )
