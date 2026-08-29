from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from yandex_analytics_reaper.domain import Platform, PlatformDeveloper, PlatformListing

SCHEMA_VERSION = 1

_SCHEMA_SQL = """
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
"""


class IdentityStore(Protocol):
    def persist_listing_identity(
        self,
        listing: PlatformListing,
        developer: PlatformDeveloper | None,
        observed_at: datetime,
    ) -> None: ...

    def get_listing(self, listing_id: str) -> PlatformListing | None: ...

    def get_developer(self, developer_id: str) -> PlatformDeveloper | None: ...

    def developer_assignments(self, listing_id: str) -> tuple[tuple[str, datetime], ...]: ...


class SQLiteIdentityStore:
    """Zero-ops operational store for normalized listing/developer identity data."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def persist_listing_identity(
        self,
        listing: PlatformListing,
        developer: PlatformDeveloper | None,
        observed_at: datetime,
    ) -> None:
        seen_at = _timestamp(observed_at)
        self._validate_developer_link(listing, developer)

        with self._connect() as connection:
            if developer is not None:
                self._upsert_developer(connection, developer, seen_at)
            self._upsert_listing(connection, listing, seen_at)
            if developer is not None:
                self._record_assignment(connection, listing.id, developer.id, seen_at)

    def get_listing(self, listing_id: str) -> PlatformListing | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM platform_listings WHERE id = ?",
                (listing_id,),
            ).fetchone()
        if row is None:
            return None
        return PlatformListing(
            id=str(row["id"]),
            platform=Platform(str(row["platform"])),
            external_app_id=str(row["external_app_id"]),
            listing_url=_optional_str(row["listing_url"]),
            developer_external_id=_optional_str(row["developer_external_id"]),
            first_seen_at=_parse_timestamp(str(row["first_seen_at"])),
            last_seen_at=_parse_timestamp(str(row["last_seen_at"])),
            first_published_at=_parse_optional_timestamp(row["first_published_at"]),
        )

    def get_developer(self, developer_id: str) -> PlatformDeveloper | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM platform_developers WHERE id = ?",
                (developer_id,),
            ).fetchone()
        if row is None:
            return None
        return PlatformDeveloper(
            id=str(row["id"]),
            platform=Platform(str(row["platform"])),
            external_developer_id=str(row["external_developer_id"]),
            display_name=_optional_str(row["display_name"]),
            first_seen_at=_parse_timestamp(str(row["first_seen_at"])),
            last_seen_at=_parse_timestamp(str(row["last_seen_at"])),
        )

    def developer_assignments(self, listing_id: str) -> tuple[tuple[str, datetime], ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT developer_id, observed_at
                FROM listing_developer_observations
                WHERE listing_id = ?
                ORDER BY observed_at
                """,
                (listing_id,),
            ).fetchall()
        return tuple(
            (str(row["developer_id"]), _parse_timestamp(str(row["observed_at"])))
            for row in rows
        )

    def _initialize(self) -> None:
        with self._connect() as connection:
            row = connection.execute("PRAGMA user_version").fetchone()
            if row is None:
                raise RuntimeError("SQLite did not return user_version")
            version = int(row[0])
            if version == 0:
                connection.executescript(_SCHEMA_SQL)
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            elif version != SCHEMA_VERSION:
                raise RuntimeError(
                    f"unsupported normalized-store schema version {version}; "
                    f"expected {SCHEMA_VERSION}"
                )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _validate_developer_link(
        listing: PlatformListing,
        developer: PlatformDeveloper | None,
    ) -> None:
        if developer is None:
            return
        if developer.platform != listing.platform:
            raise ValueError("listing and developer must belong to the same platform")
        if listing.developer_external_id != developer.external_developer_id:
            raise ValueError("listing developer_external_id does not match developer")

    @staticmethod
    def _upsert_listing(
        connection: sqlite3.Connection,
        listing: PlatformListing,
        seen_at: str,
    ) -> None:
        existing = connection.execute(
            "SELECT platform, external_app_id FROM platform_listings WHERE id = ?",
            (listing.id,),
        ).fetchone()
        if existing is not None and (
            str(existing["platform"]) != listing.platform.value
            or str(existing["external_app_id"]) != listing.external_app_id
        ):
            raise ValueError(f"listing identity changed for {listing.id}")

        connection.execute(
            """
            INSERT INTO platform_listings (
                id,
                platform,
                external_app_id,
                listing_url,
                developer_external_id,
                first_seen_at,
                last_seen_at,
                first_published_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                listing_url = CASE
                    WHEN excluded.last_seen_at >= platform_listings.last_seen_at
                         AND excluded.listing_url IS NOT NULL
                        THEN excluded.listing_url
                    ELSE platform_listings.listing_url
                END,
                developer_external_id = CASE
                    WHEN excluded.last_seen_at >= platform_listings.last_seen_at
                         AND excluded.developer_external_id IS NOT NULL
                        THEN excluded.developer_external_id
                    ELSE platform_listings.developer_external_id
                END,
                first_seen_at = MIN(platform_listings.first_seen_at, excluded.first_seen_at),
                last_seen_at = MAX(platform_listings.last_seen_at, excluded.last_seen_at),
                first_published_at = CASE
                    WHEN excluded.first_published_at IS NULL
                        THEN platform_listings.first_published_at
                    WHEN platform_listings.first_published_at IS NULL
                        THEN excluded.first_published_at
                    ELSE MIN(platform_listings.first_published_at, excluded.first_published_at)
                END
            """,
            (
                listing.id,
                listing.platform.value,
                listing.external_app_id,
                listing.listing_url,
                listing.developer_external_id,
                seen_at,
                seen_at,
                _optional_timestamp(listing.first_published_at),
            ),
        )

    @staticmethod
    def _upsert_developer(
        connection: sqlite3.Connection,
        developer: PlatformDeveloper,
        seen_at: str,
    ) -> None:
        existing = connection.execute(
            "SELECT platform, external_developer_id FROM platform_developers WHERE id = ?",
            (developer.id,),
        ).fetchone()
        if existing is not None and (
            str(existing["platform"]) != developer.platform.value
            or str(existing["external_developer_id"]) != developer.external_developer_id
        ):
            raise ValueError(f"developer identity changed for {developer.id}")

        connection.execute(
            """
            INSERT INTO platform_developers (
                id,
                platform,
                external_developer_id,
                display_name,
                first_seen_at,
                last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                display_name = CASE
                    WHEN excluded.last_seen_at >= platform_developers.last_seen_at
                         AND excluded.display_name IS NOT NULL
                        THEN excluded.display_name
                    ELSE platform_developers.display_name
                END,
                first_seen_at = MIN(platform_developers.first_seen_at, excluded.first_seen_at),
                last_seen_at = MAX(platform_developers.last_seen_at, excluded.last_seen_at)
            """,
            (
                developer.id,
                developer.platform.value,
                developer.external_developer_id,
                developer.display_name,
                seen_at,
                seen_at,
            ),
        )

    @staticmethod
    def _record_assignment(
        connection: sqlite3.Connection,
        listing_id: str,
        developer_id: str,
        seen_at: str,
    ) -> None:
        connection.execute(
            """
            INSERT OR IGNORE INTO listing_developer_observations (
                listing_id,
                developer_id,
                observed_at
            ) VALUES (?, ?, ?)
            """,
            (listing_id, developer_id, seen_at),
        )
        row = connection.execute(
            """
            SELECT developer_id
            FROM listing_developer_observations
            WHERE listing_id = ? AND observed_at = ?
            """,
            (listing_id, seen_at),
        ).fetchone()
        if row is None or str(row["developer_id"]) != developer_id:
            raise ValueError(
                f"conflicting developer assignment for {listing_id} at {seen_at}"
            )


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("persistence timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _optional_timestamp(value: datetime | None) -> str | None:
    return None if value is None else _timestamp(value)


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _parse_optional_timestamp(value: object) -> datetime | None:
    return None if value is None else _parse_timestamp(str(value))


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)
