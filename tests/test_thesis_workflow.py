from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from yandex_analytics_reaper import thesis_workflow as workflow
from yandex_analytics_reaper.thesis_intelligence import (
    ExperimentArtifactBinding,
    ThesisDeclaration,
    ThesisIntelligenceError,
    ThesisSemanticDeclaration,
    ThesisSuiteContext,
    ThesisSuiteDeclaration,
)
from yandex_analytics_reaper.thesis_workflow import (
    ThesisIntelligenceArtifactFile,
    ThesisIntelligenceArtifactManifest,
    verify_intelligence_package,
    verify_thesis_intelligence_artifact,
)


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _suite() -> ThesisSuiteDeclaration:
    return ThesisSuiteDeclaration(
        suite_id="p6-verifier-test",
        suite_version=1,
        context=ThesisSuiteContext(
            pages=1,
            session_profile="clean_anonymous",
            lang="ru",
            device="desktop",
            platform="web",
        ),
        theses=(
            ThesisDeclaration(
                thesis_id="break-objects",
                thesis_version=1,
                label="Break Objects",
                queries=("разбей предметы",),
                semantic=ThesisSemanticDeclaration(
                    theme_terms=("предмет",),
                    mechanic_terms=("разб",),
                ),
            ),
        ),
    )


def _binding(
    *,
    role: str,
    marker: str,
    experiment_id: str,
    run_id: str,
    created_at: datetime,
) -> ExperimentArtifactBinding:
    return ExperimentArtifactBinding(
        role=role,
        artifact_sha256=marker * 64,
        artifact_manifest_sha256="a" * 64,
        experiment_id=experiment_id,
        run_id=run_id,
        manifest_sha256="b" * 64,
        snapshot_id=f"snapshot:{marker}",
        snapshot_content_hash="c" * 64,
        snapshot_created_at=created_at,
        market_export_content_hash="d" * 64,
        market_features_content_hash="e" * 64,
        verifier_status="pass",
    )


def _write_package(
    path: Path,
    *,
    members: dict[str, bytes],
    build_hash: str = "1" * 64,
    current_hash: str = "2" * 64,
) -> ThesisIntelligenceArtifactManifest:
    files = tuple(
        ThesisIntelligenceArtifactFile(
            path=name,
            size=len(payload),
            sha256=_sha(payload),
        )
        for name, payload in sorted(members.items())
    )
    manifest = ThesisIntelligenceArtifactManifest(
        suite_id="p6-verifier-test",
        suite_version=1,
        run_id="20260902T120000Z",
        build_input_hash=build_hash,
        current_experiment_artifact_sha256=current_hash,
        prior_experiment_artifact_sha256s=(),
        files=files,
    )
    with ZipFile(path, mode="w", compression=ZIP_DEFLATED) as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
        archive.writestr(
            "artifact-manifest.json",
            manifest.model_dump_json(indent=2) + "\n",
        )
    return manifest


def test_generic_package_verifier_checks_member_hashes_and_exact_set(tmp_path: Path) -> None:
    artifact = tmp_path / "intelligence.zip"
    expected = _write_package(
        artifact,
        members={"comparison/thesis-comparison.md": b"descriptive evidence only\n"},
    )

    assert verify_intelligence_package(artifact) == expected


def test_generic_package_verifier_rejects_tampered_member(tmp_path: Path) -> None:
    artifact = tmp_path / "intelligence.zip"
    expected = _write_package(artifact, members={"payload.txt": b"original"})

    with ZipFile(artifact, mode="w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("payload.txt", b"tampered")
        archive.writestr(
            "artifact-manifest.json",
            expected.model_dump_json(indent=2) + "\n",
        )

    with pytest.raises(ThesisIntelligenceError, match="hash/size mismatch"):
        verify_intelligence_package(artifact)


def test_generic_package_verifier_rejects_undeclared_member(tmp_path: Path) -> None:
    artifact = tmp_path / "intelligence.zip"
    expected = _write_package(artifact, members={"payload.txt": b"original"})

    with ZipFile(artifact, mode="w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("payload.txt", b"original")
        archive.writestr("extra.txt", b"not declared")
        archive.writestr(
            "artifact-manifest.json",
            expected.model_dump_json(indent=2) + "\n",
        )

    with pytest.raises(ThesisIntelligenceError, match="member set"):
        verify_intelligence_package(artifact)


def test_source_bound_verify_requires_real_current_experiment_artifact(tmp_path: Path) -> None:
    artifact = tmp_path / "intelligence.zip"
    suite_bytes = (_suite().model_dump_json(indent=2) + "\n").encode()
    _write_package(
        artifact,
        members={"input/thesis-suite.json": suite_bytes},
    )
    missing_current = tmp_path / "missing-current.zip"

    with pytest.raises(ThesisIntelligenceError, match="cannot be bound"):
        verify_thesis_intelligence_artifact(
            artifact,
            current_artifact_path=missing_current,
        )


def test_source_artifact_bytes_remain_unchanged_on_verification_failure(tmp_path: Path) -> None:
    artifact = tmp_path / "intelligence.zip"
    suite_bytes = (_suite().model_dump_json(indent=2) + "\n").encode()
    _write_package(
        artifact,
        members={"input/thesis-suite.json": suite_bytes},
    )
    current = tmp_path / "current.zip"
    original = b"not-a-valid-experiment-zip"
    current.write_bytes(original)

    with pytest.raises(ThesisIntelligenceError, match="cannot be bound"):
        verify_thesis_intelligence_artifact(
            artifact,
            current_artifact_path=current,
        )

    assert current.read_bytes() == original


def test_manifest_rejects_noncanonical_file_order() -> None:
    with pytest.raises(ValueError, match="file paths must be sorted"):
        ThesisIntelligenceArtifactManifest(
            suite_id="p6-verifier-test",
            suite_version=1,
            run_id="20260902T120000Z",
            build_input_hash="1" * 64,
            current_experiment_artifact_sha256="2" * 64,
            prior_experiment_artifact_sha256s=(),
            files=(
                ThesisIntelligenceArtifactFile(
                    path="z.txt",
                    size=1,
                    sha256=_sha(b"z"),
                ),
                ThesisIntelligenceArtifactFile(
                    path="a.txt",
                    size=1,
                    sha256=_sha(b"a"),
                ),
            ),
        )


def test_reconstruct_canonicalizes_prior_order_before_derived_reports(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    suite = _suite()
    current = _binding(
        role="current",
        marker="1",
        experiment_id=suite.suite_id,
        run_id="20260902T120000Z",
        created_at=datetime(2026, 9, 2, 12, 0, tzinfo=UTC),
    )
    earlier = _binding(
        role="prior",
        marker="2",
        experiment_id="prior-a",
        run_id="20260831T120000Z",
        created_at=datetime(2026, 8, 31, 12, 0, tzinfo=UTC),
    )
    later = _binding(
        role="prior",
        marker="3",
        experiment_id="prior-b",
        run_id="20260901T120000Z",
        created_at=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
    )
    current_path = tmp_path / "current.zip"
    earlier_path = tmp_path / "earlier.zip"
    later_path = tmp_path / "later.zip"
    bindings = {
        current_path: current,
        earlier_path: earlier,
        later_path: later,
    }

    def fake_load(path: Path, **_: object) -> SimpleNamespace:
        return SimpleNamespace(binding=bindings[path])

    observed_prior_orders: list[tuple[str, ...]] = []

    def fake_traction(*_: object, priors: tuple[SimpleNamespace, ...], **__: object) -> str:
        observed_prior_orders.append(
            tuple(item.binding.artifact_sha256 for item in priors)
        )
        return "traction"

    monkeypatch.setattr(workflow, "load_bound_experiment_evidence", fake_load)
    monkeypatch.setattr(
        workflow,
        "_build_semantics_from_current_artifact",
        lambda *_: (),
    )
    monkeypatch.setattr(workflow, "_canonical_reviews", lambda *_: ())
    monkeypatch.setattr(workflow, "build_traction_features", fake_traction)
    monkeypatch.setattr(workflow, "build_fresh_anomaly_queue", lambda *_: "anomaly")
    monkeypatch.setattr(workflow, "build_thesis_intelligence_reports", lambda *_, **__: ())
    monkeypatch.setattr(workflow, "build_thesis_comparison", lambda *_, **__: "comparison")

    left = workflow.reconstruct_thesis_intelligence(
        suite,
        current_artifact_path=current_path,
        prior_artifact_paths=(later_path, earlier_path),
    )
    right = workflow.reconstruct_thesis_intelligence(
        suite,
        current_artifact_path=current_path,
        prior_artifact_paths=(earlier_path, later_path),
    )

    expected = (earlier.artifact_sha256, later.artifact_sha256)
    assert observed_prior_orders == [expected, expected]
    assert tuple(item.binding.artifact_sha256 for item in left.priors) == expected
    assert tuple(item.binding.artifact_sha256 for item in right.priors) == expected
    assert left.identity == right.identity
