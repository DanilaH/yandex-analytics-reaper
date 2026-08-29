from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from yandex_analytics_reaper.storage import FilesystemRawSnapshotStore, SQLiteProbeRunStore
from yandex_analytics_reaper.taxonomy import (
    TaxonomySampleManifest,
    YandexTaxonomyDiversitySampler,
)


def test_sampler_revalidates_model_copy_updates_at_empirical_boundary(tmp_path: Path) -> None:
    manifest = TaxonomySampleManifest(
        sample_id="taxonomy-sample",
        target_size=100,
        run_ids=("probe:one",),
    )
    tampered = manifest.model_copy(update={"max_per_developer": 3})
    sampler = YandexTaxonomyDiversitySampler(
        raw_store=FilesystemRawSnapshotStore(tmp_path / "raw"),
        probe_store=SQLiteProbeRunStore(tmp_path / "market.sqlite3"),
    )

    with pytest.raises(ValidationError):
        sampler.analyze(tampered)
