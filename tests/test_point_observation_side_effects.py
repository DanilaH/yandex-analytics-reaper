from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from yandex_analytics_reaper.ingestion import RichMetadataCollectionResult
from yandex_analytics_reaper.point_observation import (
    ListingObservationArtifactCollector,
    ListingObservationError,
    ListingObservationSetDeclaration,
)
from yandex_analytics_reaper.storage import FilesystemRawSnapshotStore


class _MustNotCollect:
    def collect(self, app_ids: Sequence[int]) -> RichMetadataCollectionResult:
        raise AssertionError(f"collector must not be called for an existing artifact: {app_ids}")


def test_existing_artifact_fails_before_collection_side_effects(tmp_path: Path) -> None:
    artifact = tmp_path / "already-exists.zip"
    artifact.write_bytes(b"existing")
    declaration = ListingObservationSetDeclaration(
        observation_set_id="keycap-known-direct",
        observation_set_version=1,
        app_ids=(540402, 559445, 553722),
    )
    collector = ListingObservationArtifactCollector(
        rich_collector=_MustNotCollect(),
        raw_store=FilesystemRawSnapshotStore(tmp_path / "raw"),
    )

    with pytest.raises(ListingObservationError, match="refusing to overwrite"):
        collector.collect(declaration, artifact)
