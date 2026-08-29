from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from yandex_analytics_reaper.domain import (
    QueryFamilyMember,
    QueryFamilyVersion,
    QueryVariantKind,
)
from yandex_analytics_reaper.experiments import (
    CadenceCheckpointInput,
    CollectionCadenceEvidenceError,
    CollectionCadenceExperiment,
    CollectionCadenceManifest,
)
from yandex_analytics_reaper.experiments.collection_cadence_protocol import _canonical_numeric
from yandex_analytics_reaper.storage import FilesystemRawSnapshotStore, SQLiteQueryFamilyStore


def _listing_ids() -> tuple[str, ...]:
    return tuple(f"yandex_games:{index}" for index in range(1, 21))


def _checkpoints(
    *,
    start: datetime = datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
) -> tuple[CadenceCheckpointInput, ...]:
    return tuple(
        CadenceCheckpointInput(
            checkpoint_at=start + timedelta(days=index),
            feed_run_id=f"probe:feed:{index}",
            search_run_ids=(f"probe:search:{index}",),
        )
        for index in range(28)
    )


def _manifest(**updates: object) -> CollectionCadenceManifest:
    values: dict[str, object] = {
        "frozen_at": datetime(2026, 9, 1, 9, 0, tzinfo=UTC),
        "listing_ids": _listing_ids(),
        "query_family_id": "merge-intent",
        "query_family_version": 1,
        "checkpoints": _checkpoints(),
    }
    values.update(updates)
    return CollectionCadenceManifest.model_validate(values)


def test_cadence_manifest_requires_predeclared_freeze_before_reference_window() -> None:
    manifest = _manifest()

    assert manifest.frozen_at == datetime(2026, 9, 1, 9, 0, tzinfo=UTC)
    assert len(manifest.listing_ids) == 20
    assert len(manifest.checkpoints) == 28

    with pytest.raises(ValidationError, match="frozen_at"):
        _manifest(frozen_at=datetime(2026, 9, 1, 10, 30, tzinfo=UTC))


def test_cadence_manifest_rejects_fake_daily_spacing_across_midnight() -> None:
    start_date = datetime(2026, 9, 1, 23, 30, tzinfo=UTC)
    checkpoints = tuple(
        CadenceCheckpointInput(
            checkpoint_at=(
                start_date + timedelta(days=index)
                if index % 2 == 0
                else datetime(2026, 9, 1 + index, 0, 30, tzinfo=UTC)
            ),
            feed_run_id=f"probe:feed:{index}",
            search_run_ids=(f"probe:search:{index}",),
        )
        for index in range(28)
    )

    with pytest.raises(ValidationError, match="22 to 26 hours"):
        _manifest(
            frozen_at=datetime(2026, 9, 1, 20, 0, tzinfo=UTC),
            checkpoints=checkpoints,
        )


def test_query_family_must_exist_before_manifest_freeze(tmp_path: Path) -> None:
    database_path = tmp_path / "market.sqlite3"
    SQLiteQueryFamilyStore(database_path).persist(
        QueryFamilyVersion(
            family_id="merge-intent",
            version=1,
            label="Merge intent",
            source_id="yandex_public",
            language="ru",
            created_at=datetime(2026, 9, 1, 9, 30, tzinfo=UTC),
            members=(
                QueryFamilyMember(
                    query_text="merge",
                    kind=QueryVariantKind.SEED,
                ),
            ),
        )
    )
    manifest = _manifest()

    with pytest.raises(
        CollectionCadenceEvidenceError,
        match="query-family version must exist no later than manifest frozen_at",
    ):
        CollectionCadenceExperiment(
            raw_store=FilesystemRawSnapshotStore(tmp_path / "raw"),
            database_path=database_path,
        ).analyze(manifest)


def test_cadence_numeric_state_preserves_large_integer_identity() -> None:
    value = 9_007_199_254_740_993

    assert _canonical_numeric(value) == str(value)
