from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from yandex_analytics_reaper.domain import (
    QueryFamilyMember,
    QueryFamilyVersion,
    QueryVariantKind,
)
from yandex_analytics_reaper.storage import SQLiteComparableSetStore, SQLiteQueryFamilyStore


def test_v7_query_family_database_migrates_to_comparable_set_schema_without_loss(
    tmp_path: Path,
) -> None:
    path = tmp_path / "market.sqlite3"
    family = QueryFamilyVersion(
        family_id="merge-games",
        version=1,
        label="merge games",
        source_id="yandex_public",
        language="ru",
        created_at=datetime(2026, 8, 29, 8, 0, tzinfo=UTC),
        members=(
            QueryFamilyMember(query_text="merge", kind=QueryVariantKind.SEED),
            QueryFamilyMember(query_text="слияние", kind=QueryVariantKind.SYNONYM),
        ),
    )
    SQLiteQueryFamilyStore(path).persist(family)

    with sqlite3.connect(path) as connection:
        connection.execute("DROP TABLE comparable_set_member_evidence")
        connection.execute("DROP TABLE comparable_set_members")
        connection.execute("DROP TABLE comparable_set_runs")
        connection.execute("DROP TABLE comparable_set_versions")
        connection.execute("PRAGMA user_version = 7")

    SQLiteComparableSetStore(path)

    assert SQLiteQueryFamilyStore(path).get(family.family_id, family.version) == family
    with sqlite3.connect(path) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()
        assert version is not None
        assert version[0] == 8
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert {
            "comparable_set_versions",
            "comparable_set_runs",
            "comparable_set_members",
            "comparable_set_member_evidence",
        } <= tables
        evidence_columns = {
            str(row[1])
            for row in connection.execute(
                "PRAGMA table_info(comparable_set_member_evidence)"
            ).fetchall()
        }
        assert "evidence_ordinal" in evidence_columns
