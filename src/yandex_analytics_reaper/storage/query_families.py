from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from yandex_analytics_reaper.domain import (
    QueryFamilyMember,
    QueryFamilyVersion,
    QueryVariantKind,
)

from .sqlite import SQLiteDatabase


class QueryFamilyStore(Protocol):
    def persist(self, family: QueryFamilyVersion) -> QueryFamilyVersion: ...

    def get(self, family_id: str, version: int) -> QueryFamilyVersion | None: ...

    def latest(self, family_id: str) -> QueryFamilyVersion | None: ...


class SQLiteQueryFamilyStore:
    """Immutable operational persistence for versioned exact query declarations."""

    def __init__(self, path: Path) -> None:
        self.database = SQLiteDatabase(path)

    @property
    def path(self) -> Path:
        return self.database.path

    def persist(self, family: QueryFamilyVersion) -> QueryFamilyVersion:
        with self.database.connect() as connection:
            existing = self._load(connection, family.family_id, family.version)
            if existing is not None:
                if existing != family:
                    raise ValueError(
                        "conflicting query-family content for existing family_id/version"
                    )
                return existing

            connection.execute(
                """
                INSERT INTO query_family_versions (
                    family_id,
                    version,
                    label,
                    source_id,
                    language,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    family.family_id,
                    family.version,
                    family.label,
                    family.source_id,
                    family.language,
                    _timestamp(family.created_at),
                ),
            )
            connection.executemany(
                """
                INSERT INTO query_family_members (
                    family_id,
                    version,
                    ordinal,
                    query_text,
                    variant_kind
                ) VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        family.family_id,
                        family.version,
                        ordinal,
                        member.query_text,
                        member.kind.value,
                    )
                    for ordinal, member in enumerate(family.members)
                ],
            )
            stored = self._load(connection, family.family_id, family.version)
            if stored is None:
                raise RuntimeError("query-family version was not persisted")
            if stored != family:
                raise RuntimeError("persisted query-family version does not round-trip exactly")
            return stored

    def get(self, family_id: str, version: int) -> QueryFamilyVersion | None:
        identity = _identity(family_id, version)
        with self.database.connect() as connection:
            return self._load(connection, identity[0], identity[1])

    def latest(self, family_id: str) -> QueryFamilyVersion | None:
        normalized_id = _family_id(family_id)
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT version
                FROM query_family_versions
                WHERE family_id = ?
                ORDER BY version DESC
                LIMIT 1
                """,
                (normalized_id,),
            ).fetchone()
            if row is None:
                return None
            return self._load(connection, normalized_id, int(row["version"]))

    @staticmethod
    def _load(
        connection: sqlite3.Connection,
        family_id: str,
        version: int,
    ) -> QueryFamilyVersion | None:
        row = connection.execute(
            """
            SELECT family_id, version, label, source_id, language, created_at
            FROM query_family_versions
            WHERE family_id = ? AND version = ?
            """,
            (family_id, version),
        ).fetchone()
        if row is None:
            return None

        member_rows = connection.execute(
            """
            SELECT ordinal, query_text, variant_kind
            FROM query_family_members
            WHERE family_id = ? AND version = ?
            ORDER BY ordinal
            """,
            (family_id, version),
        ).fetchall()
        ordinals = tuple(int(member["ordinal"]) for member in member_rows)
        if ordinals != tuple(range(len(member_rows))):
            raise RuntimeError("stored query-family member ordinals are not contiguous from zero")
        if not member_rows:
            raise RuntimeError("stored query-family version has no members")

        try:
            return QueryFamilyVersion(
                family_id=str(row["family_id"]),
                version=int(row["version"]),
                label=str(row["label"]),
                source_id=str(row["source_id"]),
                language=str(row["language"]),
                created_at=_parse_timestamp(str(row["created_at"])),
                members=tuple(
                    QueryFamilyMember(
                        query_text=str(member["query_text"]),
                        kind=QueryVariantKind(str(member["variant_kind"])),
                    )
                    for member in member_rows
                ),
            )
        except ValueError as exc:
            raise RuntimeError("stored query-family version is invalid") from exc


def _identity(family_id: str, version: int) -> tuple[str, int]:
    normalized_id = _family_id(family_id)
    if version < 1:
        raise ValueError("query-family version must be at least 1")
    return normalized_id, version


def _family_id(value: str) -> str:
    if not value:
        raise ValueError("family_id cannot be blank")
    if value != value.strip():
        raise ValueError("family_id must already be trimmed")
    return value


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("query-family timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
