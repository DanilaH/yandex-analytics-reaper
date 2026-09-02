from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from tempfile import NamedTemporaryFile, TemporaryDirectory
from typing import Literal, Self
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from yandex_analytics_reaper.analyst import (
    AnalystSemanticEnricher,
    AnalystSemanticEnrichmentReport,
    AnalystSemanticError,
    AnalystSemanticThesisDeclaration,
    write_analyst_semantic_csv,
)
from yandex_analytics_reaper.analyst_workflow import (
    AnalystExperimentError,
    AnalystExperimentResult,
    find_repository_root,
    run_analyst_experiment,
)
from yandex_analytics_reaper.experiment_recovery import (
    ExperimentRecoveryError,
    prepare_temporary_artifact,
    publish_artifact_create_only,
)
from yandex_analytics_reaper.experiment_workers import DEFAULT_QUERY_WORKERS
from yandex_analytics_reaper.storage import FilesystemRawSnapshotStore
from yandex_analytics_reaper.thesis_anomaly import (
    FreshAnomalyQueueReport,
    build_fresh_anomaly_queue,
)
from yandex_analytics_reaper.thesis_comparison import (
    ThesisComparisonReport,
    ThesisIntelligenceReport,
    build_thesis_comparison,
    build_thesis_intelligence_reports,
    write_thesis_comparison_csv,
    write_thesis_comparison_json,
    write_thesis_comparison_markdown,
    write_thesis_intelligence_csv,
    write_thesis_intelligence_json,
)
from yandex_analytics_reaper.thesis_directness import (
    AnalystDirectnessReviewReport,
    validate_directness_review,
)
from yandex_analytics_reaper.thesis_intelligence import (
    CompiledThesisSuite,
    ExperimentArtifactBinding,
    ThesisIntelligenceBuildIdentity,
    ThesisIntelligenceError,
    ThesisReviewBinding,
    ThesisSuiteDeclaration,
    build_intelligence_identity,
    compile_thesis_suite,
)
from yandex_analytics_reaper.thesis_traction import (
    BoundExperimentEvidence,
    ThesisTractionFeaturesReport,
    build_traction_features,
    load_bound_experiment_evidence,
)

THESIS_INTELLIGENCE_ARTIFACT_SPEC_VERSION: Literal["thesis-intelligence-artifact-v1"] = (
    "thesis-intelligence-artifact-v1"
)


class ThesisIntelligenceArtifactFile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str
    size: int = Field(ge=0)
    sha256: str

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or value != path.as_posix():
            raise ValueError("intelligence artifact paths must be safe relative POSIX paths")
        if value == "artifact-manifest.json":
            raise ValueError("artifact manifest must not hash itself")
        return value

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        _require_sha256(value)
        return value


class ThesisIntelligenceArtifactManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: Literal["thesis-intelligence-artifact-v1"] = (
        THESIS_INTELLIGENCE_ARTIFACT_SPEC_VERSION
    )
    suite_id: str
    suite_version: int = Field(ge=1)
    run_id: str
    build_input_hash: str
    current_experiment_artifact_sha256: str
    prior_experiment_artifact_sha256s: tuple[str, ...]
    files: tuple[ThesisIntelligenceArtifactFile, ...] = Field(min_length=1)

    @field_validator(
        "build_input_hash",
        "current_experiment_artifact_sha256",
        "prior_experiment_artifact_sha256s",
    )
    @classmethod
    def validate_hashes(
        cls,
        value: str | tuple[str, ...],
    ) -> str | tuple[str, ...]:
        if isinstance(value, str):
            _require_sha256(value)
        else:
            for item in value:
                _require_sha256(item)
        return value

    @model_validator(mode="after")
    def validate_files(self) -> Self:
        paths = [item.path for item in self.files]
        if paths != sorted(paths):
            raise ValueError("intelligence artifact file paths must be sorted")
        if len(paths) != len(set(paths)):
            raise ValueError("intelligence artifact file paths must be unique")
        if len(set(self.prior_experiment_artifact_sha256s)) != len(
            self.prior_experiment_artifact_sha256s
        ):
            raise ValueError("prior experiment artifact hashes must be unique")
        if self.current_experiment_artifact_sha256 in self.prior_experiment_artifact_sha256s:
            raise ValueError("current artifact cannot also be a prior artifact")
        return self


class ThesisIntelligenceArtifactResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    suite_id: str
    run_id: str
    build_input_hash: str
    artifact_path: str
    artifact_sha256: str
    artifact_manifest_sha256: str
    verifier: Literal["PASS"] = "PASS"

    @field_validator("build_input_hash", "artifact_sha256", "artifact_manifest_sha256")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        _require_sha256(value)
        return value


class ThesisIntelligenceVerificationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["PASS"] = "PASS"
    suite_id: str
    run_id: str
    build_input_hash: str
    artifact_sha256: str
    artifact_manifest_sha256: str

    @field_validator("build_input_hash", "artifact_sha256", "artifact_manifest_sha256")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        _require_sha256(value)
        return value


@dataclass(frozen=True, slots=True)
class ThesisIntelligenceBundle:
    suite: ThesisSuiteDeclaration
    compiled: CompiledThesisSuite
    current: BoundExperimentEvidence
    priors: tuple[BoundExperimentEvidence, ...]
    semantic_reports: tuple[AnalystSemanticEnrichmentReport, ...]
    reviews: tuple[AnalystDirectnessReviewReport, ...]
    identity: ThesisIntelligenceBuildIdentity
    traction: ThesisTractionFeaturesReport
    anomaly: FreshAnomalyQueueReport
    thesis_reports: tuple[ThesisIntelligenceReport, ...]
    comparison: ThesisComparisonReport


def load_thesis_suite(path: Path) -> ThesisSuiteDeclaration:
    try:
        return ThesisSuiteDeclaration.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as exc:
        raise ThesisIntelligenceError(f"invalid thesis suite: {exc}") from exc


def load_directness_reviews(paths: Sequence[Path]) -> tuple[AnalystDirectnessReviewReport, ...]:
    reviews: list[AnalystDirectnessReviewReport] = []
    for path in paths:
        try:
            reviews.append(
                AnalystDirectnessReviewReport.model_validate_json(path.read_text(encoding="utf-8"))
            )
        except (OSError, ValidationError, ValueError) as exc:
            raise ThesisIntelligenceError(f"invalid directness review {path}: {exc}") from exc
    return tuple(reviews)


def reconstruct_thesis_intelligence(
    suite: ThesisSuiteDeclaration,
    *,
    current_artifact_path: Path,
    prior_artifact_paths: Sequence[Path] = (),
    reviews: Sequence[AnalystDirectnessReviewReport] = (),
) -> ThesisIntelligenceBundle:
    """Rebuild all 0.3 intelligence deterministically from frozen experiment ZIPs."""
    suite = ThesisSuiteDeclaration.model_validate(suite.model_dump())
    compiled = compile_thesis_suite(suite)
    current = load_bound_experiment_evidence(
        current_artifact_path,
        role="current",
        expected_suite=suite,
    )
    prior_evidence = tuple(
        load_bound_experiment_evidence(path, role="prior") for path in prior_artifact_paths
    )
    semantic_reports = _build_semantics_from_current_artifact(
        current_artifact_path,
        current,
        compiled.semantic_theses,
    )
    ordered_reviews = _canonical_reviews(suite, semantic_reports, reviews)
    review_bindings = tuple(
        ThesisReviewBinding(
            thesis_id=review.thesis_id,
            review_content_hash=review.content_hash,
            semantic_report_content_hash=review.semantic_report_content_hash,
        )
        for review in ordered_reviews
    )
    identity = build_intelligence_identity(
        suite,
        current_experiment=current.binding,
        prior_experiments=tuple(item.binding for item in prior_evidence),
        review_bindings=review_bindings,
    )
    traction = build_traction_features(
        suite,
        current=current,
        priors=prior_evidence,
    )
    anomaly = build_fresh_anomaly_queue(suite, traction)
    thesis_reports = build_thesis_intelligence_reports(
        suite,
        current=current,
        traction=traction,
        anomaly=anomaly,
        semantic_reports=semantic_reports,
        reviews=ordered_reviews,
    )
    comparison = build_thesis_comparison(
        suite,
        thesis_reports=thesis_reports,
        semantic_reports=semantic_reports,
        reviews=ordered_reviews,
    )
    return ThesisIntelligenceBundle(
        suite=suite,
        compiled=compiled,
        current=current,
        priors=prior_evidence,
        semantic_reports=semantic_reports,
        reviews=ordered_reviews,
        identity=identity,
        traction=traction,
        anomaly=anomaly,
        thesis_reports=thesis_reports,
        comparison=comparison,
    )


def build_thesis_intelligence_artifact(
    suite: ThesisSuiteDeclaration,
    *,
    current_artifact_path: Path,
    prior_artifact_paths: Sequence[Path] = (),
    reviews: Sequence[AnalystDirectnessReviewReport] = (),
    repository_root: Path,
) -> ThesisIntelligenceArtifactResult:
    """Build, source-verify and create-only publish one final intelligence ZIP."""
    bundle = reconstruct_thesis_intelligence(
        suite,
        current_artifact_path=current_artifact_path,
        prior_artifact_paths=prior_artifact_paths,
        reviews=reviews,
    )
    artifact_path = repository_root.resolve() / bundle.identity.relative_artifact_path

    with TemporaryDirectory(prefix="yandex-reaper-thesis-build-") as directory:
        workdir = Path(directory)
        _write_bundle_payload(bundle, workdir)
        manifest = _build_intelligence_artifact_manifest(bundle, workdir)
        manifest_path = workdir / "artifact-manifest.json"
        _write_model_create_only(manifest_path, manifest)

        temporary_artifact = prepare_temporary_artifact(artifact_path)
        try:
            _package_intelligence_workdir(workdir, temporary_artifact)
            verified_manifest = verify_intelligence_package(temporary_artifact)
            if verified_manifest != manifest:
                raise ThesisIntelligenceError(
                    "packaged intelligence manifest does not match the build manifest"
                )
            verify_thesis_intelligence_artifact(
                temporary_artifact,
                current_artifact_path=current_artifact_path,
                prior_artifact_paths=prior_artifact_paths,
            )
            artifact_sha256 = _sha256_file(temporary_artifact)
            artifact_manifest_sha256 = _sha256_file(manifest_path)
            publish_artifact_create_only(temporary_artifact, artifact_path)
        except Exception:
            _discard_file(temporary_artifact)
            raise

    return ThesisIntelligenceArtifactResult(
        suite_id=bundle.suite.suite_id,
        run_id=bundle.current.binding.run_id,
        build_input_hash=bundle.identity.build_input_hash,
        artifact_path=_relative_display(artifact_path, repository_root),
        artifact_sha256=artifact_sha256,
        artifact_manifest_sha256=artifact_manifest_sha256,
    )


def verify_intelligence_package(
    artifact_path: Path,
) -> ThesisIntelligenceArtifactManifest:
    """Verify path safety, member set, sizes and hashes without trusting derived semantics."""
    try:
        with ZipFile(artifact_path, mode="r") as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise ThesisIntelligenceError("intelligence artifact contains duplicate paths")
            for name in names:
                _validate_archive_path(name)
            if "artifact-manifest.json" not in names:
                raise ThesisIntelligenceError(
                    "intelligence artifact is missing artifact-manifest.json"
                )
            manifest = ThesisIntelligenceArtifactManifest.model_validate_json(
                archive.read("artifact-manifest.json")
            )
            expected = {item.path for item in manifest.files}
            if set(names) != expected | {"artifact-manifest.json"}:
                raise ThesisIntelligenceError(
                    "intelligence artifact member set does not match artifact-manifest.json"
                )
            for item in manifest.files:
                payload = archive.read(item.path)
                if len(payload) != item.size or _sha256_bytes(payload) != item.sha256:
                    raise ThesisIntelligenceError(
                        f"intelligence artifact hash/size mismatch for {item.path}"
                    )
            return manifest
    except ThesisIntelligenceError:
        raise
    except (BadZipFile, OSError, KeyError, ValidationError, ValueError) as exc:
        raise ThesisIntelligenceError(
            f"intelligence artifact verification failed: {exc}"
        ) from exc


def verify_thesis_intelligence_artifact(
    artifact_path: Path,
    *,
    current_artifact_path: Path,
    prior_artifact_paths: Sequence[Path] = (),
) -> ThesisIntelligenceVerificationResult:
    """Source-bound rebuild verification against explicitly supplied frozen experiments."""
    manifest = verify_intelligence_package(artifact_path)
    try:
        with ZipFile(artifact_path, mode="r") as archive:
            suite = ThesisSuiteDeclaration.model_validate_json(
                archive.read("input/thesis-suite.json")
            )
            reviews = _reviews_from_archive(archive, suite)
    except ThesisIntelligenceError:
        raise
    except (BadZipFile, KeyError, ValidationError, ValueError) as exc:
        raise ThesisIntelligenceError(
            f"intelligence artifact source inputs cannot be loaded: {exc}"
        ) from exc

    bundle = reconstruct_thesis_intelligence(
        suite,
        current_artifact_path=current_artifact_path,
        prior_artifact_paths=prior_artifact_paths,
        reviews=reviews,
    )
    _validate_manifest_identity(manifest, bundle)

    with TemporaryDirectory(prefix="yandex-reaper-thesis-verify-") as directory:
        expected_root = Path(directory)
        _write_bundle_payload(bundle, expected_root)
        expected_manifest = _build_intelligence_artifact_manifest(bundle, expected_root)
        if expected_manifest != manifest:
            raise ThesisIntelligenceError(
                "intelligence artifact manifest does not match source-bound rebuild"
            )
        try:
            with ZipFile(artifact_path, mode="r") as archive:
                for path in _payload_files(expected_root):
                    relative = path.relative_to(expected_root).as_posix()
                    if archive.read(relative) != path.read_bytes():
                        raise ThesisIntelligenceError(
                            f"intelligence member differs from source-bound rebuild: {relative}"
                        )
        except ThesisIntelligenceError:
            raise
        except (BadZipFile, KeyError, OSError) as exc:
            raise ThesisIntelligenceError(
                f"intelligence artifact source-bound comparison failed: {exc}"
            ) from exc

    return ThesisIntelligenceVerificationResult(
        suite_id=manifest.suite_id,
        run_id=manifest.run_id,
        build_input_hash=manifest.build_input_hash,
        artifact_sha256=_sha256_file(artifact_path),
        artifact_manifest_sha256=_artifact_manifest_sha256(artifact_path),
    )


def run_thesis_intelligence(
    suite_path: Path,
    *,
    prior_artifact_paths: Sequence[Path] = (),
    review_paths: Sequence[Path] = (),
    query_workers: int = DEFAULT_QUERY_WORKERS,
) -> ThesisIntelligenceArtifactResult:
    """Delegate collection to the 0.2 runner, then build intelligence from its frozen ZIP."""
    suite = load_thesis_suite(suite_path)
    reviews = load_directness_reviews(review_paths)
    repository_root = find_repository_root(suite_path)
    compiled = compile_thesis_suite(suite)

    temporary_manifest: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".json",
            prefix=".thesis-experiment-",
            dir=repository_root,
            delete=False,
        ) as handle:
            handle.write(compiled.experiment_manifest.model_dump_json(indent=2) + "\n")
            temporary_manifest = Path(handle.name)
        experiment_result = run_analyst_experiment(
            temporary_manifest,
            query_workers=query_workers,
        )
    finally:
        if temporary_manifest is not None:
            _discard_file(temporary_manifest)

    current_artifact_path = _experiment_result_artifact_path(
        experiment_result,
        repository_root,
    )
    return build_thesis_intelligence_artifact(
        suite,
        current_artifact_path=current_artifact_path,
        prior_artifact_paths=prior_artifact_paths,
        reviews=reviews,
        repository_root=repository_root,
    )


def _build_semantics_from_current_artifact(
    artifact_path: Path,
    current: BoundExperimentEvidence,
    semantic_theses: Sequence[AnalystSemanticThesisDeclaration],
) -> tuple[AnalystSemanticEnrichmentReport, ...]:
    with TemporaryDirectory(prefix="yandex-reaper-thesis-raw-") as directory:
        root = Path(directory)
        _materialize_raw_payload(artifact_path, root)
        enricher = AnalystSemanticEnricher(
            raw_store=FilesystemRawSnapshotStore(root / "raw")
        )
        try:
            return tuple(
                enricher.build(current.snapshot, thesis) for thesis in semantic_theses
            )
        except AnalystSemanticError as exc:
            raise ThesisIntelligenceError(
                f"semantic replay from current experiment artifact failed: {exc}"
            ) from exc


def _canonical_reviews(
    suite: ThesisSuiteDeclaration,
    semantic_reports: Sequence[AnalystSemanticEnrichmentReport],
    reviews: Sequence[AnalystDirectnessReviewReport],
) -> tuple[AnalystDirectnessReviewReport, ...]:
    semantic_by_id = {report.thesis.thesis_id: report for report in semantic_reports}
    by_id: dict[str, AnalystDirectnessReviewReport] = {}
    for source_review in reviews:
        thesis_id = source_review.thesis_id
        semantic = semantic_by_id.get(thesis_id)
        if semantic is None:
            raise ThesisIntelligenceError("directness review references a thesis outside the suite")
        if thesis_id in by_id:
            raise ThesisIntelligenceError("duplicate directness review for thesis")
        by_id[thesis_id] = validate_directness_review(
            source_review,
            suite=suite,
            semantic_report=semantic,
        )
    return tuple(by_id[item.thesis_id] for item in suite.theses if item.thesis_id in by_id)


def _write_bundle_payload(bundle: ThesisIntelligenceBundle, root: Path) -> None:
    _write_model_create_only(root / "input/thesis-suite.json", bundle.suite)
    _write_model_create_only(
        root / "input/compiled-experiment-manifest.json",
        bundle.compiled.experiment_manifest,
    )
    for thesis in bundle.compiled.semantic_theses:
        _write_model_create_only(
            root / f"input/semantic-theses/{thesis.thesis_id}.json",
            thesis,
        )

    _write_model_create_only(
        root / "bindings/current-experiment-artifact.json",
        bundle.current.binding,
    )
    _write_json_create_only(
        root / "bindings/history-experiment-artifacts.json",
        [item.binding.model_dump(mode="json") for item in bundle.priors],
    )

    semantic_by_id = {
        report.thesis.thesis_id: report for report in bundle.semantic_reports
    }
    review_by_id = {review.thesis_id: review for review in bundle.reviews}
    thesis_report_by_id = {report.thesis_id: report for report in bundle.thesis_reports}
    for thesis in bundle.suite.theses:
        semantic = semantic_by_id[thesis.thesis_id]
        _write_model_create_only(
            root / f"semantic/{thesis.thesis_id}.json",
            semantic,
        )
        write_analyst_semantic_csv(
            semantic,
            root / f"semantic/{thesis.thesis_id}.csv",
        )
        review = review_by_id.get(thesis.thesis_id)
        if review is not None:
            _write_model_create_only(
                root / f"reviews/{thesis.thesis_id}.json",
                review,
            )
        report = thesis_report_by_id[thesis.thesis_id]
        write_thesis_intelligence_json(
            report,
            root / f"theses/{thesis.thesis_id}-report.json",
        )
        write_thesis_intelligence_csv(
            report,
            root / f"theses/{thesis.thesis_id}-report.csv",
        )

    write_thesis_comparison_json(
        bundle.comparison,
        root / "comparison/thesis-comparison.json",
    )
    write_thesis_comparison_csv(
        bundle.comparison,
        root / "comparison/thesis-comparison.csv",
    )
    write_thesis_comparison_markdown(
        bundle.comparison,
        root / "comparison/thesis-comparison.md",
    )


def _build_intelligence_artifact_manifest(
    bundle: ThesisIntelligenceBundle,
    root: Path,
) -> ThesisIntelligenceArtifactManifest:
    files = tuple(
        ThesisIntelligenceArtifactFile(
            path=path.relative_to(root).as_posix(),
            size=path.stat().st_size,
            sha256=_sha256_file(path),
        )
        for path in _payload_files(root)
    )
    return ThesisIntelligenceArtifactManifest(
        suite_id=bundle.suite.suite_id,
        suite_version=bundle.suite.suite_version,
        run_id=bundle.current.binding.run_id,
        build_input_hash=bundle.identity.build_input_hash,
        current_experiment_artifact_sha256=bundle.current.binding.artifact_sha256,
        prior_experiment_artifact_sha256s=tuple(
            item.artifact_sha256 for item in bundle.identity.inputs.prior_experiments
        ),
        files=files,
    )


def _package_intelligence_workdir(root: Path, artifact_path: Path) -> None:
    try:
        with ZipFile(artifact_path, mode="x", compression=ZIP_DEFLATED) as archive:
            for path in _payload_files(root):
                archive.write(path, path.relative_to(root).as_posix())
            archive.write(root / "artifact-manifest.json", "artifact-manifest.json")
    except Exception:
        _discard_file(artifact_path)
        raise


def _materialize_raw_payload(artifact_path: Path, target_root: Path) -> None:
    try:
        with ZipFile(artifact_path, mode="r") as archive:
            found = False
            for info in archive.infolist():
                name = info.filename
                _validate_archive_path(name)
                if info.is_dir() or not name.startswith("raw/"):
                    continue
                found = True
                target = target_root.joinpath(*PurePosixPath(name).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(info))
            if not found:
                raise ThesisIntelligenceError(
                    "current experiment artifact contains no raw payload for semantic replay"
                )
    except ThesisIntelligenceError:
        raise
    except (BadZipFile, OSError, KeyError) as exc:
        raise ThesisIntelligenceError(
            f"current experiment raw payload cannot be materialized: {exc}"
        ) from exc


def _reviews_from_archive(
    archive: ZipFile,
    suite: ThesisSuiteDeclaration,
) -> tuple[AnalystDirectnessReviewReport, ...]:
    reviews: list[AnalystDirectnessReviewReport] = []
    names = set(archive.namelist())
    for thesis in suite.theses:
        name = f"reviews/{thesis.thesis_id}.json"
        if name not in names:
            continue
        reviews.append(AnalystDirectnessReviewReport.model_validate_json(archive.read(name)))
    unexpected = {
        name
        for name in names
        if name.startswith("reviews/")
        and name.endswith(".json")
        and name not in {f"reviews/{item.thesis_id}.json" for item in suite.theses}
    }
    if unexpected:
        raise ThesisIntelligenceError(
            "intelligence artifact contains review files outside the declared suite"
        )
    return tuple(reviews)


def _validate_manifest_identity(
    manifest: ThesisIntelligenceArtifactManifest,
    bundle: ThesisIntelligenceBundle,
) -> None:
    expected = (
        bundle.suite.suite_id,
        bundle.suite.suite_version,
        bundle.current.binding.run_id,
        bundle.identity.build_input_hash,
        bundle.current.binding.artifact_sha256,
        tuple(item.artifact_sha256 for item in bundle.identity.inputs.prior_experiments),
    )
    actual = (
        manifest.suite_id,
        manifest.suite_version,
        manifest.run_id,
        manifest.build_input_hash,
        manifest.current_experiment_artifact_sha256,
        manifest.prior_experiment_artifact_sha256s,
    )
    if actual != expected:
        raise ThesisIntelligenceError(
            "intelligence artifact identity does not match source-bound rebuild"
        )


def _payload_files(root: Path) -> tuple[Path, ...]:
    selected = [
        path
        for path in root.rglob("*")
        if path.is_file() and path.name != "artifact-manifest.json"
    ]
    return tuple(sorted(selected, key=lambda path: path.relative_to(root).as_posix()))


def _write_model_create_only(path: Path, model: BaseModel) -> None:
    _write_text_create_only(path, model.model_dump_json(indent=2) + "\n")


def _write_json_create_only(path: Path, value: object) -> None:
    _write_text_create_only(
        path,
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
    )


def _write_text_create_only(path: Path, value: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8", newline="") as handle:
            handle.write(value)
    except FileExistsError as exc:
        raise ThesisIntelligenceError(f"output already exists: {path}") from exc
    except OSError as exc:
        raise ThesisIntelligenceError(str(exc)) from exc


def _artifact_manifest_sha256(artifact_path: Path) -> str:
    try:
        with ZipFile(artifact_path, mode="r") as archive:
            return _sha256_bytes(archive.read("artifact-manifest.json"))
    except (BadZipFile, KeyError, OSError) as exc:
        raise ThesisIntelligenceError(
            f"cannot hash intelligence artifact manifest: {exc}"
        ) from exc


def _experiment_result_artifact_path(
    result: AnalystExperimentResult,
    repository_root: Path,
) -> Path:
    path = Path(result.artifact_path)
    return path if path.is_absolute() else repository_root / path


def _validate_archive_path(name: str) -> None:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or name != path.as_posix():
        raise ThesisIntelligenceError(f"artifact contains unsafe path: {name}")


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


def _require_sha256(value: str) -> None:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError("value must be a lowercase SHA-256 hex digest")


def _discard_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _relative_display(path: Path, repository_root: Path) -> str:
    try:
        return path.resolve().relative_to(repository_root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


__all__ = [
    "THESIS_INTELLIGENCE_ARTIFACT_SPEC_VERSION",
    "ThesisIntelligenceArtifactFile",
    "ThesisIntelligenceArtifactManifest",
    "ThesisIntelligenceArtifactResult",
    "ThesisIntelligenceBundle",
    "ThesisIntelligenceVerificationResult",
    "build_thesis_intelligence_artifact",
    "load_directness_reviews",
    "load_thesis_suite",
    "reconstruct_thesis_intelligence",
    "run_thesis_intelligence",
    "verify_intelligence_package",
    "verify_thesis_intelligence_artifact",
]
