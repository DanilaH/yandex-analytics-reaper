from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

import pytest

from yandex_analytics_reaper.thesis_artifacts import load_experiment_artifact_binding
from yandex_analytics_reaper.thesis_intelligence import ThesisIntelligenceError


def test_artifact_binding_rejects_non_experiment_zip(tmp_path: Path) -> None:
    artifact = tmp_path / "invalid.zip"
    with ZipFile(artifact, mode="w") as archive:
        archive.writestr("random.txt", "not an experiment")

    with pytest.raises(ThesisIntelligenceError, match="cannot be bound"):
        load_experiment_artifact_binding(artifact, role="current")


def test_artifact_binding_rejects_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "missing.zip"

    with pytest.raises(ThesisIntelligenceError, match="cannot be bound"):
        load_experiment_artifact_binding(missing, role="prior")
