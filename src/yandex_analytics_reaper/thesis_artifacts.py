from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal
from zipfile import BadZipFile, ZipFile

from pydantic import ValidationError

from yandex_analytics_reaper.analyst import (
    AnalystMarketExportReport,
    AnalystMarketFeaturesReport,
    AnalystSnapshotReport,
)
from yandex_analytics_reaper.analyst_workflow import (
    AnalystExperimentExecutionSummary,
    AnalystExperimentManifest,
    AnalystExperimentVerification,
    verify_packaged_artifact,
)
from yandex_analytics_reaper.thesis_intelligence import (
    ExperimentArtifactBinding,
    ThesisIntelligenceError,
    ThesisSuiteDeclaration,
    compile_thesis_suite,
)

_REQUIRED_MEMBERS = (
    "input/manifest.json",
    "reports/analyst-snapshot.json",
    "reports/market-export.json",
    "reports/market-features.json",
    "reports/verification.json",
    "execution-summary.json",
    "artifact-manifest.json",
)


def load_experiment_artifact_binding(
    artifact_path: Path,
    *,
    role: Literal["current", "prior"],
    expected_suite: ThesisSuiteDeclaration | None = None,
) -> ExperimentArtifactBinding:
    """Verify an immutable 0.2 experiment ZIP and reconstruct its 0.3 binding."""
    if expected_suite is not None and role != "current":
        raise ThesisIntelligenceError("expected_suite may only be used for role=current")

    try:
        packaged = verify_packaged_artifact(artifact_path)
        with ZipFile(artifact_path, mode="r") as archive:
            names = set(archive.namelist())
            missing = [name for name in _REQUIRED_MEMBERS if name not in names]
            if missing:
                raise ThesisIntelligenceError(
                    "experiment artifact is missing required intelligence binding members: "
                    + ", ".join(missing)
                )

            artifact_manifest_bytes = archive.read("artifact-manifest.json")
            manifest_bytes = archive.read("input/manifest.json")
            summary = AnalystExperimentExecutionSummary.model_validate_json(
                archive.read("execution-summary.json")
            )
            manifest = AnalystExperimentManifest.model_validate_json(manifest_bytes)
            snapshot = AnalystSnapshotReport.model_validate_json(
                archive.read("reports/analyst-snapshot.json")
            )
            market_export = AnalystMarketExportReport.model_validate_json(
                archive.read("reports/market-export.json")
            )
            market_features = AnalystMarketFeaturesReport.model_validate_json(
                archive.read("reports/market-features.json")
            )
            verification = AnalystExperimentVerification.model_validate_json(
                archive.read("reports/verification.json")
            )
    except ThesisIntelligenceError:
        raise
    except (BadZipFile, OSError, KeyError, ValidationError, ValueError) as exc:
        raise ThesisIntelligenceError(
            f"experiment artifact cannot be bound to thesis intelligence: {exc}"
        ) from exc

    manifest_sha256 = _sha256_bytes(manifest_bytes)
    artifact_manifest_sha256 = _sha256_bytes(artifact_manifest_bytes)

    if packaged.experiment_id != manifest.experiment_id:
        raise ThesisIntelligenceError(
            "artifact manifest experiment_id disagrees with input manifest"
        )
    if summary.experiment_id != manifest.experiment_id:
        raise ThesisIntelligenceError(
            "execution summary experiment_id disagrees with input manifest"
        )
    if packaged.run_id != summary.run_id:
        raise ThesisIntelligenceError(
            "artifact manifest run_id disagrees with execution summary"
        )
    if summary.manifest_sha256 != manifest_sha256:
        raise ThesisIntelligenceError(
            "execution summary manifest hash disagrees with input manifest"
        )

    expected_hashes = (
        snapshot.content_hash,
        market_export.content_hash,
        market_features.content_hash,
    )
    summary_hashes = (
        summary.snapshot_content_hash,
        summary.market_export_content_hash,
        summary.market_features_content_hash,
    )
    verification_hashes = (
        verification.snapshot_content_hash,
        verification.market_export_content_hash,
        verification.market_features_content_hash,
    )
    if summary_hashes != expected_hashes:
        raise ThesisIntelligenceError(
            "execution summary report hashes disagree with report content"
        )
    if verification_hashes != expected_hashes or verification.status != "pass":
        raise ThesisIntelligenceError(
            "experiment verification report disagrees with report content"
        )
    if snapshot.snapshot_id != market_export.snapshot_id:
        raise ThesisIntelligenceError(
            "market export snapshot_id disagrees with analyst snapshot"
        )
    if snapshot.content_hash != market_export.snapshot_content_hash:
        raise ThesisIntelligenceError(
            "market export snapshot hash disagrees with analyst snapshot"
        )
    if snapshot.snapshot_id != market_features.snapshot_id:
        raise ThesisIntelligenceError(
            "market features snapshot_id disagrees with analyst snapshot"
        )
    if snapshot.content_hash != market_features.snapshot_content_hash:
        raise ThesisIntelligenceError(
            "market features snapshot hash disagrees with analyst snapshot"
        )

    if expected_suite is not None:
        compiled = compile_thesis_suite(expected_suite)
        if manifest != compiled.experiment_manifest:
            raise ThesisIntelligenceError(
                "current experiment manifest does not equal the suite-compiled manifest"
            )

    return ExperimentArtifactBinding(
        role=role,
        artifact_sha256=_sha256_file(artifact_path),
        artifact_manifest_sha256=artifact_manifest_sha256,
        experiment_id=manifest.experiment_id,
        run_id=summary.run_id,
        manifest_sha256=manifest_sha256,
        snapshot_id=snapshot.snapshot_id,
        snapshot_content_hash=snapshot.content_hash,
        snapshot_created_at=snapshot.created_at,
        market_export_content_hash=market_export.content_hash,
        market_features_content_hash=market_features.content_hash,
        verifier_status="pass",
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise ThesisIntelligenceError(str(exc)) from exc
    return digest.hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
