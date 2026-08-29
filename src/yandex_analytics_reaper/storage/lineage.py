from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from yandex_analytics_reaper.evidence import FieldLineage

from .sqlite import SQLiteDatabase


class LineageRecord(FieldLineage):
    normalized_observation_id: str


class LineageStore(Protocol):
    def persist_lineage(
        self,
        normalized_observation_id: str,
        inputs: Sequence[FieldLineage],
    ) -> None: ...

    def for_observation(self, normalized_observation_id: str) -> tuple[LineageRecord, ...]: ...


class SQLiteLineageStore:
    """Persistence/read API for field-level normalization lineage."""

    def __init__(self, path: Path) -> None:
        self.database = SQLiteDatabase(path)

    @property
    def path(self) -> Path:
        return self.database.path

    def persist_lineage(
        self,
        normalized_observation_id: str,
        inputs: Sequence[FieldLineage],
    ) -> None:
        with self.database.connect() as connection:
            persist_lineage_in_connection(connection, normalized_observation_id, inputs)

    def for_observation(self, normalized_observation_id: str) -> tuple[LineageRecord, ...]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    normalized_observation_id,
                    raw_snapshot_id,
                    source_field_path,
                    target_field_path,
                    transformation_name,
                    transformation_version
                FROM observation_lineage
                WHERE normalized_observation_id = ?
                ORDER BY raw_snapshot_id, source_field_path, target_field_path
                """,
                (normalized_observation_id,),
            ).fetchall()
        return tuple(
            LineageRecord(
                normalized_observation_id=str(row["normalized_observation_id"]),
                raw_snapshot_id=str(row["raw_snapshot_id"]),
                source_field_path=str(row["source_field_path"]),
                target_field_path=str(row["target_field_path"]),
                transformation_name=str(row["transformation_name"]),
                transformation_version=str(row["transformation_version"]),
            )
            for row in rows
        )


def persist_lineage_in_connection(
    connection: sqlite3.Connection,
    normalized_observation_id: str,
    inputs: Sequence[FieldLineage],
) -> None:
    if not normalized_observation_id.strip():
        raise ValueError("normalized_observation_id cannot be blank")
    observation = connection.execute(
        "SELECT id FROM normalized_observations WHERE id = ?",
        (normalized_observation_id,),
    ).fetchone()
    if observation is None:
        raise ValueError(f"normalized observation {normalized_observation_id} does not exist")

    seen_keys: set[tuple[str, str, str]] = set()
    for item in inputs:
        key = (item.raw_snapshot_id, item.source_field_path, item.target_field_path)
        if key in seen_keys:
            raise ValueError("duplicate lineage key in one write")
        seen_keys.add(key)

        connection.execute(
            """
            INSERT OR IGNORE INTO observation_lineage (
                normalized_observation_id,
                raw_snapshot_id,
                source_field_path,
                target_field_path,
                transformation_name,
                transformation_version
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                normalized_observation_id,
                item.raw_snapshot_id,
                item.source_field_path,
                item.target_field_path,
                item.transformation_name,
                item.transformation_version,
            ),
        )
        row = connection.execute(
            """
            SELECT transformation_name, transformation_version
            FROM observation_lineage
            WHERE normalized_observation_id = ?
              AND raw_snapshot_id = ?
              AND source_field_path = ?
              AND target_field_path = ?
            """,
            (
                normalized_observation_id,
                item.raw_snapshot_id,
                item.source_field_path,
                item.target_field_path,
            ),
        ).fetchone()
        if row is None or (
            str(row["transformation_name"]) != item.transformation_name
            or str(row["transformation_version"]) != item.transformation_version
        ):
            raise ValueError(
                "conflicting lineage transformation for the same source/target field"
            )
