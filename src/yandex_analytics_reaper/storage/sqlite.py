from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

SCHEMA_VERSION = 3

_MIGRATIONS: dict[int, str] = {
    1: """
CREATE TABLE IF NOT EXISTS platform_listings (
    id TEXT PRIMARY KEY,
    platform TEXT NOT NULL,
    external_app_id TEXT NOT NULL,
    listing_url TEXT,
    developer_external_id TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    first_published_at TEXT,
    UNIQUE (platform, external_app_id)
);

CREATE TABLE IF NOT EXISTS platform_developers (
    id TEXT PRIMARY KEY,
    platform TEXT NOT NULL,
    external_developer_id TEXT NOT NULL,
    display_name TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    UNIQUE (platform, external_developer_id)
);

CREATE TABLE IF NOT EXISTS listing_developer_observations (
    listing_id TEXT NOT NULL REFERENCES platform_listings(id) ON DELETE CASCADE,
    developer_id TEXT NOT NULL REFERENCES platform_developers(id),
    observed_at TEXT NOT NULL,
    PRIMARY KEY (listing_id, observed_at)
);

CREATE INDEX IF NOT EXISTS idx_listing_developer_observations_developer
ON listing_developer_observations (developer_id, observed_at);
""",
    2: """
CREATE TABLE IF NOT EXISTS normalized_observations (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    observation_type TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    available_at TEXT,
    retrieved_at TEXT NOT NULL,
    normalizer_name TEXT NOT NULL,
    normalizer_version TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_normalized_observations_time
ON normalized_observations (observed_at, source_id);

CREATE TABLE IF NOT EXISTS game_metric_observations (
    observation_id TEXT PRIMARY KEY
        REFERENCES normalized_observations(id) ON DELETE CASCADE,
    platform_listing_id TEXT NOT NULL
        REFERENCES platform_listings(id) ON DELETE CASCADE,
    metric_name TEXT NOT NULL,
    period_start TEXT,
    period_end TEXT,
    value_numeric NUMERIC,
    missing_reason TEXT,
    provenance TEXT NOT NULL,
    measurement_kind TEXT NOT NULL,
    semantic_confidence TEXT NOT NULL,
    coverage_status TEXT NOT NULL,
    historical_availability TEXT NOT NULL,
    revision_status TEXT NOT NULL,
    uncertainty_json TEXT,
    lineage_refs_json TEXT NOT NULL DEFAULT '[]',
    CHECK (
        (value_numeric IS NOT NULL AND missing_reason IS NULL)
        OR (value_numeric IS NULL AND missing_reason IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_game_metric_history
ON game_metric_observations (platform_listing_id, metric_name, observation_id);
""",
    3: """
CREATE TABLE IF NOT EXISTS observation_lineage (
    normalized_observation_id TEXT NOT NULL
        REFERENCES normalized_observations(id) ON DELETE CASCADE,
    raw_snapshot_id TEXT NOT NULL,
    source_field_path TEXT NOT NULL,
    target_field_path TEXT NOT NULL,
    transformation_name TEXT NOT NULL,
    transformation_version TEXT NOT NULL,
    PRIMARY KEY (
        normalized_observation_id,
        raw_snapshot_id,
        source_field_path,
        target_field_path
    )
);

CREATE INDEX IF NOT EXISTS idx_observation_lineage_raw_snapshot
ON observation_lineage (raw_snapshot_id, normalized_observation_id);
""",
}


class SQLiteDatabase:
    """Shared versioned SQLite database used by Phase 2 operational stores."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = self._new_connection()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _new_connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def _migrate(self) -> None:
        connection = self._new_connection()
        try:
            row = connection.execute("PRAGMA user_version").fetchone()
            if row is None:
                raise RuntimeError("SQLite did not return user_version")
            current = int(row[0])
            if current > SCHEMA_VERSION:
                raise RuntimeError(
                    f"unsupported normalized-store schema version {current}; "
                    f"maximum supported is {SCHEMA_VERSION}"
                )

            for target in range(current + 1, SCHEMA_VERSION + 1):
                migration = _MIGRATIONS[target]
                connection.executescript(
                    "BEGIN IMMEDIATE;\n"
                    + migration
                    + f"\nPRAGMA user_version = {target};\nCOMMIT;"
                )
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()
