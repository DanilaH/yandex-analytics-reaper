from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from yandex_analytics_reaper.domain import (
    QueryFamilyMember,
    QueryFamilyVersion,
    QueryVariantKind,
)
from yandex_analytics_reaper.storage import SQLiteQueryFamilyStore


def _family(
    *,
    version: int = 1,
    label: str = "merge games",
    members: tuple[QueryFamilyMember, ...] | None = None,
) -> QueryFamilyVersion:
    return QueryFamilyVersion(
        family_id="merge-games",
        version=version,
        label=label,
        source_id="yandex_public",
        language="ru",
        created_at=datetime(2026, 8, 29, 12, 0, tzinfo=UTC),
        members=members
        or (
            QueryFamilyMember(query_text="merge", kind=QueryVariantKind.SEED),
            QueryFamilyMember(query_text="слияние", kind=QueryVariantKind.SYNONYM),
            QueryFamilyMember(
                query_text="мердж",
                kind=QueryVariantKind.TRANSLITERATION,
            ),
        ),
    )


def test_query_family_requires_exactly_one_seed_at_member_zero() -> None:
    with pytest.raises(ValidationError, match="exactly one seed"):
        _family(
            members=(
                QueryFamilyMember(query_text="merge", kind=QueryVariantKind.SYNONYM),
                QueryFamilyMember(query_text="слияние", kind=QueryVariantKind.SEED),
            )
        )

    with pytest.raises(ValidationError, match="exactly one seed"):
        _family(
            members=(
                QueryFamilyMember(query_text="merge", kind=QueryVariantKind.SEED),
                QueryFamilyMember(query_text="слияние", kind=QueryVariantKind.SEED),
            )
        )


def test_query_family_rejects_duplicate_or_silently_normalized_query_text() -> None:
    with pytest.raises(ValidationError, match="must already be trimmed"):
        QueryFamilyMember(query_text=" merge ", kind=QueryVariantKind.SEED)

    with pytest.raises(ValidationError, match="must be unique"):
        _family(
            members=(
                QueryFamilyMember(query_text="merge", kind=QueryVariantKind.SEED),
                QueryFamilyMember(query_text="merge", kind=QueryVariantKind.SYNONYM),
            )
        )


def test_query_family_store_round_trips_exact_member_order(tmp_path: Path) -> None:
    store = SQLiteQueryFamilyStore(tmp_path / "market.sqlite3")
    family = _family()

    persisted = store.persist(family)

    assert persisted == family
    assert store.get("merge-games", 1) == family
    assert [member.query_text for member in persisted.members] == [
        "merge",
        "слияние",
        "мердж",
    ]


def test_identical_write_is_idempotent_but_conflicting_rewrite_fails(tmp_path: Path) -> None:
    store = SQLiteQueryFamilyStore(tmp_path / "market.sqlite3")
    family = _family()

    assert store.persist(family) == family
    assert store.persist(family) == family

    with pytest.raises(ValueError, match="conflicting query-family content"):
        store.persist(_family(label="changed label"))


def test_multiple_versions_coexist_and_latest_uses_highest_version(tmp_path: Path) -> None:
    store = SQLiteQueryFamilyStore(tmp_path / "market.sqlite3")
    first = _family(version=1)
    second = _family(
        version=2,
        members=(
            QueryFamilyMember(query_text="merge", kind=QueryVariantKind.SEED),
            QueryFamilyMember(query_text="слияние", kind=QueryVariantKind.SYNONYM),
            QueryFamilyMember(query_text="объединение", kind=QueryVariantKind.SYNONYM),
        ),
    )

    store.persist(second)
    store.persist(first)

    assert store.get("merge-games", 1) == first
    assert store.get("merge-games", 2) == second
    assert store.latest("merge-games") == second
    assert store.latest("unknown-family") is None


def test_store_fails_closed_on_noncontiguous_member_ordinals(tmp_path: Path) -> None:
    store = SQLiteQueryFamilyStore(tmp_path / "market.sqlite3")
    family = _family()
    store.persist(family)

    with store.database.connect() as connection:
        connection.execute(
            """
            UPDATE query_family_members
            SET ordinal = 7
            WHERE family_id = ? AND version = ? AND ordinal = 2
            """,
            (family.family_id, family.version),
        )

    with pytest.raises(RuntimeError, match="ordinals are not contiguous"):
        store.get(family.family_id, family.version)
