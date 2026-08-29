from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from yandex_analytics_reaper.domain import (
    Platform,
    PlatformListing,
    QueryFamilyMember,
    QueryFamilyVersion,
    QueryVariantKind,
)
from yandex_analytics_reaper.experiments import (
    CadenceCheckpointInput,
    CollectionCadenceEvidenceError,
    CollectionCadenceManifest,
    CollectionCadencePlanDeclaration,
    CollectionCadencePlanFreezer,
)
from yandex_analytics_reaper.experiments.collection_cadence_protocol import _canonical_numeric
from yandex_analytics_reaper.storage import (
    SQLiteCollectionCadencePlanStore,
    SQLiteIdentityStore,
    SQLiteQueryFamilyStore,
)


def _listing_ids() -> tuple[str, ...]:
    return tuple(f"yandex_games:{index}" for index in range(1, 21))


def _checkpoint_times(first: datetime) -> tuple[datetime, ...]:
    return tuple(first + timedelta(days=index) for index in range(28))


def _prepare_cohort(database_path: Path, observed_at: datetime) -> None:
    identity_store = SQLiteIdentityStore(database_path)
    for app_id in range(1, 21):
        identity_store.persist_listing_identity(
            PlatformListing(
                id=f"yandex_games:{app_id}",
                platform=Platform.YANDEX_GAMES,
                external_app_id=str(app_id),
            ),
            None,
            observed_at,
        )
    SQLiteQueryFamilyStore(database_path).persist(
        QueryFamilyVersion(
            family_id="merge-intent",
            version=1,
            label="Merge intent",
            source_id="yandex_public",
            language="ru",
            created_at=observed_at,
            members=(
                QueryFamilyMember(query_text="merge", kind=QueryVariantKind.SEED),
            ),
        )
    )


def _declaration(first: datetime) -> CollectionCadencePlanDeclaration:
    return CollectionCadencePlanDeclaration(
        plan_id="cadence:merge:v1",
        listing_ids=_listing_ids(),
        query_family_id="merge-intent",
        query_family_version=1,
        checkpoint_at=_checkpoint_times(first),
    )


def test_cadence_plan_freezes_with_database_time_and_is_immutable(tmp_path: Path) -> None:
    database_path = tmp_path / "market.sqlite3"
    now = datetime.now(UTC)
    _prepare_cohort(database_path, now - timedelta(days=1))
    first = now + timedelta(days=1)
    freezer = CollectionCadencePlanFreezer(database_path)

    first_write = freezer.freeze(_declaration(first))
    second_write = freezer.freeze(_declaration(first))

    assert first_write == second_write
    assert first_write.plan_id == "cadence:merge:v1"
    assert first_write.frozen_at <= first - timedelta(hours=2)
    assert len(first_write.content_hash) == 64
    assert first_write.listing_ids == _listing_ids()
    assert first_write.checkpoint_at == _checkpoint_times(first)

    conflicting = _declaration(first).model_copy(
        update={"listing_ids": tuple(reversed(_listing_ids()))}
    )
    with pytest.raises(CollectionCadenceEvidenceError, match="conflicting content"):
        freezer.freeze(conflicting)


def test_cadence_plan_cannot_be_backdated_after_collection_window_starts(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "market.sqlite3"
    now = datetime.now(UTC)
    _prepare_cohort(database_path, now - timedelta(days=1))

    with pytest.raises(CollectionCadenceEvidenceError, match="at least two hours"):
        CollectionCadencePlanFreezer(database_path).freeze(
            _declaration(now + timedelta(hours=1))
        )


def test_cadence_plan_rejects_fake_daily_spacing_across_midnight() -> None:
    start = datetime(2026, 9, 1, 23, 30, tzinfo=UTC)
    checkpoint_at = tuple(
        start + timedelta(days=index)
        if index % 2 == 0
        else datetime(2026, 9, 1 + index, 0, 30, tzinfo=UTC)
        for index in range(28)
    )

    with pytest.raises(ValidationError, match="22 to 26 hours"):
        CollectionCadencePlanDeclaration(
            plan_id="cadence:broken",
            listing_ids=_listing_ids(),
            query_family_id="merge-intent",
            query_family_version=1,
            checkpoint_at=checkpoint_at,
        )


def test_evidence_manifest_must_match_frozen_checkpoint_schedule(tmp_path: Path) -> None:
    database_path = tmp_path / "market.sqlite3"
    now = datetime.now(UTC)
    _prepare_cohort(database_path, now - timedelta(days=1))
    first = now + timedelta(days=1)
    stored = CollectionCadencePlanFreezer(database_path).freeze(_declaration(first))
    checkpoints = tuple(
        CadenceCheckpointInput(
            checkpoint_at=value,
            feed_run_id=f"probe:feed:{index}",
            search_run_ids=(f"probe:search:{index}",),
        )
        for index, value in enumerate(stored.checkpoint_at)
    )
    shifted = list(checkpoints)
    shifted[5] = shifted[5].model_copy(
        update={"checkpoint_at": shifted[5].checkpoint_at + timedelta(minutes=1)}
    )
    manifest = CollectionCadenceManifest(
        plan_id=stored.plan_id,
        checkpoints=tuple(shifted),
    )

    with pytest.raises(CollectionCadenceEvidenceError, match="differs from the frozen plan"):
        manifest.evidence_manifest(stored)


def test_late_manifest_cannot_supply_fake_freeze_or_cohort_fields() -> None:
    with pytest.raises(ValidationError, match="extra"):
        CollectionCadenceManifest.model_validate(
            {
                "plan_id": "cadence:merge:v1",
                "frozen_at": "2026-09-01T00:00:00Z",
                "listing_ids": list(_listing_ids()),
                "checkpoints": [
                    {
                        "checkpoint_at": "2026-09-02T12:00:00Z",
                        "feed_run_id": "probe:feed:0",
                        "search_run_ids": ["probe:search:0"],
                    }
                ]
                * 28,
            }
        )


def test_plan_store_roundtrip_validates_content_hash(tmp_path: Path) -> None:
    database_path = tmp_path / "market.sqlite3"
    now = datetime.now(UTC)
    _prepare_cohort(database_path, now - timedelta(days=1))
    stored = CollectionCadencePlanFreezer(database_path).freeze(
        _declaration(now + timedelta(days=1))
    )

    assert SQLiteCollectionCadencePlanStore(database_path).get(stored.plan_id) == stored


def test_cadence_numeric_state_preserves_large_integer_identity() -> None:
    value = 9_007_199_254_740_993

    assert _canonical_numeric(value) == str(value)
