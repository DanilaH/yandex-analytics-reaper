from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from pydantic import AwareDatetime, BaseModel, ConfigDict

from .sqlite import SQLiteDatabase


class StoredCollectionCadencePlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    plan_id: str
    spec_version: str
    frozen_at: AwareDatetime
    content_hash: str
    query_family_id: str
    query_family_version: int
    listing_ids: tuple[str, ...]
    checkpoint_at: tuple[AwareDatetime, ...]


class CollectionCadencePlanStore(Protocol):
    def freeze(
        self,
        *,
        plan_id: str,
        spec_version: str,
        query_family_id: str,
        query_family_version: int,
        listing_ids: Sequence[str],
        checkpoint_at: Sequence[datetime],
        latest_freeze_at: datetime,
    ) -> StoredCollectionCadencePlan: ...

    def get(self, plan_id: str) -> StoredCollectionCadencePlan | None: ...

    def current_time(self) -> datetime: ...


class SQLiteCollectionCadencePlanStore:
    """Immutable predeclaration store for collection-cadence calibration plans."""

    def __init__(self, path: Path) -> None:
        self.database = SQLiteDatabase(path)

    @property
    def path(self) -> Path:
        return self.database.path

    def current_time(self) -> datetime:
        with self.database.connect() as connection:
            return _database_now(connection)

    def freeze(
        self,
        *,
        plan_id: str,
        spec_version: str,
        query_family_id: str,
        query_family_version: int,
        listing_ids: Sequence[str],
        checkpoint_at: Sequence[datetime],
        latest_freeze_at: datetime,
    ) -> StoredCollectionCadencePlan:
        normalized_plan_id = _non_blank(plan_id, "plan_id")
        normalized_spec = _non_blank(spec_version, "spec_version")
        normalized_family_id = _non_blank(query_family_id, "query_family_id")
        if query_family_version < 1:
            raise ValueError("query_family_version must be at least 1")
        normalized_listing_ids = tuple(
            _non_blank(listing_id, "listing_id") for listing_id in listing_ids
        )
        normalized_checkpoints = tuple(_aware(value, "checkpoint_at") for value in checkpoint_at)
        if not normalized_listing_ids:
            raise ValueError("collection cadence plan requires listing IDs")
        if not normalized_checkpoints:
            raise ValueError("collection cadence plan requires checkpoints")
        latest = _aware(latest_freeze_at, "latest_freeze_at")
        content_hash = _content_hash(
            plan_id=normalized_plan_id,
            spec_version=normalized_spec,
            query_family_id=normalized_family_id,
            query_family_version=query_family_version,
            listing_ids=normalized_listing_ids,
            checkpoint_at=normalized_checkpoints,
        )

        with self.database.connect() as connection:
            existing = self._load(connection, normalized_plan_id)
            if existing is not None:
                if existing.content_hash != content_hash:
                    raise ValueError("conflicting content for existing collection cadence plan_id")
                if existing.frozen_at.astimezone(UTC) > latest:
                    raise ValueError("existing collection cadence plan was frozen after its deadline")
                return existing

            frozen_at = _database_now(connection)
            if frozen_at > latest:
                raise ValueError(
                    "collection cadence plan must be frozen before the predeclared deadline"
                )
            connection.execute(
                """
                INSERT INTO collection_cadence_plans (
                    plan_id,
                    spec_version,
                    frozen_at,
                    content_hash,
                    query_family_id,
                    query_family_version
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized_plan_id,
                    normalized_spec,
                    _timestamp(frozen_at),
                    content_hash,
                    normalized_family_id,
                    query_family_version,
                ),
            )
            connection.executemany(
                """
                INSERT INTO collection_cadence_plan_listings (
                    plan_id,
                    ordinal,
                    listing_id
                ) VALUES (?, ?, ?)
                """,
                [
                    (normalized_plan_id, ordinal, listing_id)
                    for ordinal, listing_id in enumerate(normalized_listing_ids)
                ],
            )
            connection.executemany(
                """
                INSERT INTO collection_cadence_plan_checkpoints (
                    plan_id,
                    ordinal,
                    checkpoint_at
                ) VALUES (?, ?, ?)
                """,
                [
                    (normalized_plan_id, ordinal, _timestamp(value))
                    for ordinal, value in enumerate(normalized_checkpoints)
                ],
            )
            stored = self._load(connection, normalized_plan_id)
            if stored is None:
                raise RuntimeError("collection cadence plan was not persisted")
            if stored.content_hash != content_hash:
                raise RuntimeError("persisted collection cadence plan hash changed")
            return stored

    def get(self, plan_id: str) -> StoredCollectionCadencePlan | None:
        normalized_plan_id = _non_blank(plan_id, "plan_id")
        with self.database.connect() as connection:
            return self._load(connection, normalized_plan_id)

    @staticmethod
    def _load(
        connection: sqlite3.Connection,
        plan_id: str,
    ) -> StoredCollectionCadencePlan | None:
        row = connection.execute(
            """
            SELECT
                plan_id,
                spec_version,
                frozen_at,
                content_hash,
                query_family_id,
                query_family_version
            FROM collection_cadence_plans
            WHERE plan_id = ?
            """,
            (plan_id,),
        ).fetchone()
        if row is None:
            return None

        listing_rows = connection.execute(
            """
            SELECT ordinal, listing_id
            FROM collection_cadence_plan_listings
            WHERE plan_id = ?
            ORDER BY ordinal
            """,
            (plan_id,),
        ).fetchall()
        checkpoint_rows = connection.execute(
            """
            SELECT ordinal, checkpoint_at
            FROM collection_cadence_plan_checkpoints
            WHERE plan_id = ?
            ORDER BY ordinal
            """,
            (plan_id,),
        ).fetchall()
        _require_contiguous_ordinals(listing_rows, "collection cadence listing")
        _require_contiguous_ordinals(checkpoint_rows, "collection cadence checkpoint")
        if not listing_rows or not checkpoint_rows:
            raise RuntimeError("stored collection cadence plan is incomplete")

        stored = StoredCollectionCadencePlan(
            plan_id=str(row["plan_id"]),
            spec_version=str(row["spec_version"]),
            frozen_at=_parse_timestamp(str(row["frozen_at"])),
            content_hash=str(row["content_hash"]),
            query_family_id=str(row["query_family_id"]),
            query_family_version=int(row["query_family_version"]),
            listing_ids=tuple(str(item["listing_id"]) for item in listing_rows),
            checkpoint_at=tuple(
                _parse_timestamp(str(item["checkpoint_at"])) for item in checkpoint_rows
            ),
        )
        expected_hash = _content_hash(
            plan_id=stored.plan_id,
            spec_version=stored.spec_version,
            query_family_id=stored.query_family_id,
            query_family_version=stored.query_family_version,
            listing_ids=stored.listing_ids,
            checkpoint_at=stored.checkpoint_at,
        )
        if stored.content_hash != expected_hash:
            raise RuntimeError("stored collection cadence plan content hash is invalid")
        return stored


def _require_contiguous_ordinals(rows: Sequence[sqlite3.Row], label: str) -> None:
    ordinals = tuple(int(row["ordinal"]) for row in rows)
    if ordinals != tuple(range(len(rows))):
        raise RuntimeError(f"stored {label} ordinals are not contiguous from zero")


def _content_hash(
    *,
    plan_id: str,
    spec_version: str,
    query_family_id: str,
    query_family_version: int,
    listing_ids: Sequence[str],
    checkpoint_at: Sequence[datetime],
) -> str:
    payload = {
        "plan_id": plan_id,
        "spec_version": spec_version,
        "query_family_id": query_family_id,
        "query_family_version": query_family_version,
        "listing_ids": list(listing_ids),
        "checkpoint_at": [_timestamp(value) for value in checkpoint_at],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _database_now(connection: sqlite3.Connection) -> datetime:
    row = connection.execute(
        "SELECT strftime('%Y-%m-%dT%H:%M:%fZ', 'now') AS current_time"
    ).fetchone()
    if row is None:
        raise RuntimeError("SQLite did not return current UTC time")
    return _parse_timestamp(str(row["current_time"]))


def _timestamp(value: datetime) -> str:
    return _aware(value, "timestamp").isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _aware(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def _non_blank(value: str, field: str) -> str:
    if not value:
        raise ValueError(f"{field} cannot be blank")
    if value != value.strip():
        raise ValueError(f"{field} must already be trimmed")
    return value
