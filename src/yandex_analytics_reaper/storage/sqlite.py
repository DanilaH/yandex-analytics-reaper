from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

SCHEMA_VERSION = 9

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
    4: """
CREATE TABLE IF NOT EXISTS schema_observations (
    id TEXT PRIMARY KEY,
    raw_snapshot_id TEXT NOT NULL,
    analyzer_version TEXT NOT NULL,
    contract_id TEXT NOT NULL,
    comparison_scope_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    request_key TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    schema_hash TEXT,
    profile_status TEXT NOT NULL,
    root_type TEXT,
    error TEXT,
    UNIQUE (raw_snapshot_id, analyzer_version, contract_id, comparison_scope_id)
);

CREATE INDEX IF NOT EXISTS idx_schema_observations_source_request_time
ON schema_observations (
    source_id,
    request_key,
    analyzer_version,
    contract_id,
    comparison_scope_id,
    retrieved_at,
    raw_snapshot_id
);

CREATE TABLE IF NOT EXISTS schema_field_profiles (
    schema_observation_id TEXT NOT NULL
        REFERENCES schema_observations(id) ON DELETE CASCADE,
    field_path TEXT NOT NULL,
    value_types_json TEXT NOT NULL,
    present_count INTEGER NOT NULL,
    parent_count INTEGER NOT NULL,
    presence_ratio REAL NOT NULL,
    PRIMARY KEY (schema_observation_id, field_path),
    CHECK (present_count >= 0),
    CHECK (parent_count >= present_count),
    CHECK (presence_ratio >= 0.0 AND presence_ratio <= 1.0)
);

CREATE INDEX IF NOT EXISTS idx_schema_field_profiles_path
ON schema_field_profiles (field_path, schema_observation_id);

CREATE TABLE IF NOT EXISTS schema_drift_events (
    id TEXT PRIMARY KEY,
    schema_observation_id TEXT NOT NULL
        REFERENCES schema_observations(id) ON DELETE CASCADE,
    raw_snapshot_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    severity TEXT NOT NULL,
    field_path TEXT,
    previous_types_json TEXT NOT NULL DEFAULT '[]',
    current_types_json TEXT NOT NULL DEFAULT '[]',
    previous_presence_ratio REAL,
    current_presence_ratio REAL,
    details_json TEXT NOT NULL DEFAULT '{}',
    message TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_schema_drift_events_snapshot
ON schema_drift_events (raw_snapshot_id, severity, kind);
""",
    5: """
CREATE TABLE IF NOT EXISTS probe_contexts (
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

CREATE TABLE IF NOT EXISTS probe_runs (
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

CREATE INDEX IF NOT EXISTS idx_probe_runs_context_time
ON probe_runs (source_id, request_key, context_id, started_at, id);

CREATE TABLE IF NOT EXISTS probe_pages (
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

CREATE INDEX IF NOT EXISTS idx_probe_pages_snapshot
ON probe_pages (source_id, raw_snapshot_id, run_id, page_index);
""",
    6: """
ALTER TABLE probe_contexts ADD COLUMN session_instance_id TEXT;
""",
    7: """
CREATE TABLE IF NOT EXISTS query_family_versions (
    family_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    label TEXT NOT NULL,
    source_id TEXT NOT NULL,
    language TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (family_id, version),
    CHECK (version >= 1)
);

CREATE TABLE IF NOT EXISTS query_family_members (
    family_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    ordinal INTEGER NOT NULL,
    query_text TEXT NOT NULL,
    variant_kind TEXT NOT NULL,
    PRIMARY KEY (family_id, version, ordinal),
    UNIQUE (family_id, version, query_text),
    FOREIGN KEY (family_id, version)
        REFERENCES query_family_versions(family_id, version)
        ON DELETE CASCADE,
    CHECK (ordinal >= 0)
);

CREATE INDEX IF NOT EXISTS idx_query_family_versions_latest
ON query_family_versions (family_id, version DESC);
""",
    8: """
CREATE TABLE IF NOT EXISTS comparable_set_versions (
    set_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    construction_method TEXT NOT NULL,
    query_family_id TEXT NOT NULL,
    query_family_version INTEGER NOT NULL,
    source_id TEXT NOT NULL,
    language TEXT NOT NULL,
    context_id TEXT NOT NULL REFERENCES probe_contexts(id),
    requested_page_limit INTEGER NOT NULL,
    parser_name TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    observed_from TEXT NOT NULL,
    observed_to TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (set_id, version),
    FOREIGN KEY (query_family_id, query_family_version)
        REFERENCES query_family_versions(family_id, version),
    CHECK (version >= 1),
    CHECK (query_family_version >= 1),
    CHECK (requested_page_limit >= 1)
);

CREATE TABLE IF NOT EXISTS comparable_set_runs (
    set_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    query_ordinal INTEGER NOT NULL,
    query_text TEXT NOT NULL,
    probe_run_id TEXT NOT NULL REFERENCES probe_runs(id),
    PRIMARY KEY (set_id, version, query_ordinal),
    UNIQUE (set_id, version, query_text),
    UNIQUE (set_id, version, probe_run_id),
    FOREIGN KEY (set_id, version)
        REFERENCES comparable_set_versions(set_id, version)
        ON DELETE CASCADE,
    CHECK (query_ordinal >= 0)
);

CREATE TABLE IF NOT EXISTS comparable_set_members (
    set_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    ordinal INTEGER NOT NULL,
    platform_listing_id TEXT NOT NULL,
    PRIMARY KEY (set_id, version, ordinal),
    UNIQUE (set_id, version, platform_listing_id),
    FOREIGN KEY (set_id, version)
        REFERENCES comparable_set_versions(set_id, version)
        ON DELETE CASCADE,
    CHECK (ordinal >= 0)
);

CREATE TABLE IF NOT EXISTS comparable_set_member_evidence (
    set_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    evidence_ordinal INTEGER NOT NULL,
    platform_listing_id TEXT NOT NULL,
    probe_run_id TEXT NOT NULL REFERENCES probe_runs(id),
    raw_snapshot_id TEXT NOT NULL,
    page_index INTEGER NOT NULL,
    source_object_path TEXT NOT NULL,
    PRIMARY KEY (set_id, version, evidence_ordinal),
    UNIQUE (
        set_id,
        version,
        platform_listing_id,
        probe_run_id,
        raw_snapshot_id,
        page_index,
        source_object_path
    ),
    FOREIGN KEY (set_id, version, platform_listing_id)
        REFERENCES comparable_set_members(set_id, version, platform_listing_id)
        ON DELETE CASCADE,
    CHECK (evidence_ordinal >= 0),
    CHECK (page_index >= 0)
);

CREATE INDEX IF NOT EXISTS idx_comparable_set_versions_latest
ON comparable_set_versions (set_id, version DESC);

CREATE INDEX IF NOT EXISTS idx_comparable_set_evidence_run
ON comparable_set_member_evidence (probe_run_id, page_index, raw_snapshot_id);
""",
    9: """
CREATE TABLE IF NOT EXISTS listing_history_evidence (
    observation_id TEXT PRIMARY KEY
        REFERENCES normalized_observations(id) ON DELETE CASCADE,
    provenance TEXT NOT NULL,
    measurement_kind TEXT NOT NULL,
    semantic_confidence TEXT NOT NULL,
    coverage_status TEXT NOT NULL,
    historical_availability TEXT NOT NULL,
    revision_status TEXT NOT NULL,
    uncertainty_json TEXT,
    lineage_refs_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS listing_update_observations (
    observation_id TEXT PRIMARY KEY
        REFERENCES normalized_observations(id) ON DELETE CASCADE,
    platform_listing_id TEXT NOT NULL
        REFERENCES platform_listings(id) ON DELETE CASCADE,
    app_version TEXT,
    source_published_at TEXT,
    CHECK (app_version IS NOT NULL OR source_published_at IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_listing_update_history
ON listing_update_observations (platform_listing_id, observation_id);

CREATE TABLE IF NOT EXISTS listing_status_observations (
    observation_id TEXT PRIMARY KEY
        REFERENCES normalized_observations(id) ON DELETE CASCADE,
    platform_listing_id TEXT NOT NULL
        REFERENCES platform_listings(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    status_reason TEXT NOT NULL,
    CHECK (status = 'published'),
    CHECK (
        status_reason IN (
            'observed_in_catalogue_metadata',
            'observed_on_game_page'
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_listing_status_history
ON listing_status_observations (platform_listing_id, observation_id);

CREATE TABLE IF NOT EXISTS listing_media_observations (
    observation_id TEXT PRIMARY KEY
        REFERENCES normalized_observations(id) ON DELETE CASCADE,
    platform_listing_id TEXT NOT NULL
        REFERENCES platform_listings(id) ON DELETE CASCADE,
    manifest_hash TEXT NOT NULL,
    CHECK (length(manifest_hash) = 64),
    CHECK (manifest_hash NOT GLOB '*[^0-9a-f]*')
);

CREATE INDEX IF NOT EXISTS idx_listing_media_history
ON listing_media_observations (platform_listing_id, observation_id);
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
