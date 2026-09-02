from __future__ import annotations

import hashlib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from yandex_analytics_reaper.thesis_intelligence import (
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
        archive.writestr("artifact-manifest.json", manifest.model_dump_json(indent=2) + "\n")
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
        archive.writestr("artifact-manifest.json", expected.model_dump_json(indent=2) + "\n")

    with pytest.raises(ThesisIntelligenceError, match="hash/size mismatch"):
        verify_intelligence_package(artifact)


def test_generic_package_verifier_rejects_undeclared_member(tmp_path: Path) -> None:
    artifact = tmp_path / "intelligence.zip"
    expected = _write_package(artifact, members={"payload.txt": b"original"})

    with ZipFile(artifact, mode="w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("payload.txt", b"original")
        archive.writestr("extra.txt", b"not declared")
        archive.writestr("artifact-manifest.json", expected.model_dump_json(indent=2) + "\n")

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
