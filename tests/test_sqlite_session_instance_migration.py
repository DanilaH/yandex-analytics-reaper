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
            CREATE TABLE probe_runs (
                id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                request_key TEXT NOT NULL,
                probe_kind TEXT NOT NULL,
                context_id TEXT NOT NULL REFERENCES probe_contexts(id),
                query_text TEXT,
                requested_page_limit INTEGER NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                status TEXT NOT NULL,
                error TEXT,
                error_raw_snapshot_id TEXT,
                CHECK (requested_page_limit >= 1)
            );
            CREATE TABLE probe_pages (
                run_id TEXT NOT NULL REFERENCES probe_runs(id) ON DELETE CASCADE,
                page_index INTEGER NOT NULL,
                source_id TEXT NOT NULL,
                raw_snapshot_id TEXT NOT NULL,
                retrieved_at TEXT NOT NULL,
                request_page_id TEXT,
                request_rtx_reqid TEXT,
                response_next_page_id TEXT,
                response_rtx_reqid TEXT,
                has_next_page INTEGER NOT NULL,
                PRIMARY KEY (run_id, page_index),
                UNIQUE (source_id, raw_snapshot_id),
                CHECK (page_index >= 0),
                CHECK (has_next_page IN (0, 1))
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
        assert version[0] == 10
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
        tables = {
            str(item[0])
            for item in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert {
            "query_family_versions",
            "query_family_members",
            "comparable_set_versions",
            "listing_history_evidence",
            "collection_cadence_plans",
        } <= tables
