from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from yandex_analytics_reaper.analyst import AnalystSemanticRule, AnalystSemanticThesisDeclaration
from yandex_analytics_reaper.analyst_workflow import (
    AnalystExperimentContext,
    AnalystExperimentFamily,
    AnalystExperimentManifest,
)

THESIS_SUITE_SPEC_VERSION: Literal["thesis-suite-v1"] = "thesis-suite-v1"
THESIS_ANOMALY_POLICY_SPEC_VERSION: Literal["thesis-anomaly-policy-v1"] = (
    "thesis-anomaly-policy-v1"
)
THESIS_EXPERIMENT_BINDING_SPEC_VERSION: Literal["thesis-experiment-binding-v1"] = (
    "thesis-experiment-binding-v1"
)
THESIS_BUILD_INPUTS_SPEC_VERSION: Literal["thesis-intelligence-build-inputs-v1"] = (
    "thesis-intelligence-build-inputs-v1"
)
THESIS_INTELLIGENCE_METHOD_VERSION: Literal["thesis-intelligence-method-v1"] = (
    "thesis-intelligence-method-v1"
)

_ID_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"


class ThesisIntelligenceError(ValueError):
    """Frozen thesis-intelligence evidence cannot be accepted safely."""


class ThesisSuiteContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    pages: int = Field(ge=1)
    session_profile: Literal["clean_anonymous"]
    lang: str
    device: Literal["desktop", "mobile"]
    platform: str

    @field_validator("lang", "platform")
    @classmethod
    def validate_text(cls, value: str) -> str:
        if not value or value != value.strip():
            raise ValueError("suite context fields must be non-blank and already trimmed")
        return value


class ThesisSemanticDeclaration(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    theme_terms: tuple[str, ...] = Field(min_length=1)
    mechanic_terms: tuple[str, ...] = Field(min_length=1)
    reward_grammar_terms: tuple[str, ...] | None = None

    @field_validator("theme_terms", "mechanic_terms", "reward_grammar_terms")
    @classmethod
    def validate_terms(cls, values: tuple[str, ...] | None) -> tuple[str, ...] | None:
        if values is None:
            return None
        if not values:
            raise ValueError("configured semantic term groups must be non-empty")
        AnalystSemanticRule(terms=values)
        return values


class ThesisAnomalyPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: Literal["thesis-anomaly-policy-v1"] = THESIS_ANOMALY_POLICY_SPEC_VERSION
    max_age_days: float | None = Field(default=None, gt=0.0)
    min_rating_count: int | None = Field(default=None, ge=0)
    min_lifetime_ratings_per_day: float | None = Field(default=None, ge=0.0)
    min_age_bucket_percentile: float | None = Field(default=None, ge=0.0, le=1.0)
    min_observed_rating_delta_per_day: float | None = Field(default=None, ge=0.0)

    @model_validator(mode="after")
    def validate_gates(self) -> Self:
        gates = (
            self.max_age_days,
            self.min_rating_count,
            self.min_lifetime_ratings_per_day,
            self.min_age_bucket_percentile,
            self.min_observed_rating_delta_per_day,
        )
        if all(value is None for value in gates):
            raise ValueError("anomaly policy must configure at least one gate")
        return self


class ThesisDeclaration(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    thesis_id: str = Field(pattern=_ID_PATTERN, max_length=80)
    thesis_version: int = Field(ge=1)
    label: str
    queries: tuple[str, ...] = Field(min_length=1)
    semantic: ThesisSemanticDeclaration

    @field_validator("label")
    @classmethod
    def validate_label(cls, value: str) -> str:
        if not value or value != value.strip():
            raise ValueError("thesis label must be non-blank and already trimmed")
        return value

    @field_validator("queries")
    @classmethod
    def validate_queries(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not value or value != value.strip() for value in values):
            raise ValueError("thesis queries must be non-blank and already trimmed")
        if len(set(values)) != len(values):
            raise ValueError("thesis queries must be unique")
        return values


class ThesisSuiteDeclaration(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: Literal["thesis-suite-v1"] = THESIS_SUITE_SPEC_VERSION
    suite_id: str = Field(pattern=_ID_PATTERN, max_length=80)
    suite_version: int = Field(ge=1)
    context: ThesisSuiteContext
    anomaly_policy: ThesisAnomalyPolicy | None = None
    theses: tuple[ThesisDeclaration, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_suite(self) -> Self:
        thesis_ids = [item.thesis_id for item in self.theses]
        if len(set(thesis_ids)) != len(thesis_ids):
            raise ValueError("suite thesis IDs must be unique")
        queries = [query for item in self.theses for query in item.queries]
        if len(set(queries)) != len(queries):
            raise ValueError("an exact query may belong to only one suite thesis")
        return self


class CompiledThesisSuite(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    suite_content_hash: str
    experiment_manifest: AnalystExperimentManifest
    semantic_theses: tuple[AnalystSemanticThesisDeclaration, ...] = Field(min_length=1)

    @field_validator("suite_content_hash")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        _require_sha256(value)
        return value


class ExperimentArtifactBinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: Literal["thesis-experiment-binding-v1"] = (
        THESIS_EXPERIMENT_BINDING_SPEC_VERSION
    )
    role: Literal["current", "prior"]
    artifact_sha256: str
    artifact_manifest_sha256: str
    experiment_id: str
    run_id: str
    manifest_sha256: str
    snapshot_id: str
    snapshot_content_hash: str
    snapshot_created_at: AwareDatetime
    market_export_content_hash: str
    market_features_content_hash: str
    verifier_status: Literal["pass"] = "pass"

    @field_validator(
        "artifact_sha256",
        "artifact_manifest_sha256",
        "manifest_sha256",
        "snapshot_content_hash",
        "market_export_content_hash",
        "market_features_content_hash",
    )
    @classmethod
    def validate_hash(cls, value: str) -> str:
        _require_sha256(value)
        return value

    @field_validator("experiment_id", "run_id", "snapshot_id")
    @classmethod
    def validate_identity(cls, value: str) -> str:
        if not value or value != value.strip():
            raise ValueError("artifact binding identities must be non-blank and already trimmed")
        return value


class ThesisReviewBinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    thesis_id: str = Field(pattern=_ID_PATTERN, max_length=80)
    review_content_hash: str
    semantic_report_content_hash: str

    @field_validator("review_content_hash", "semantic_report_content_hash")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        _require_sha256(value)
        return value


class ThesisIntelligenceBuildInputs(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: Literal["thesis-intelligence-build-inputs-v1"] = (
        THESIS_BUILD_INPUTS_SPEC_VERSION
    )
    method_version: Literal["thesis-intelligence-method-v1"] = THESIS_INTELLIGENCE_METHOD_VERSION
    suite_content_hash: str
    current_experiment: ExperimentArtifactBinding
    prior_experiments: tuple[ExperimentArtifactBinding, ...] = ()
    review_bindings: tuple[ThesisReviewBinding, ...] = ()

    @field_validator("suite_content_hash")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        _require_sha256(value)
        return value

    @model_validator(mode="after")
    def validate_bindings(self) -> Self:
        if self.current_experiment.role != "current":
            raise ValueError("current_experiment binding must have role=current")
        if any(item.role != "prior" for item in self.prior_experiments):
            raise ValueError("prior_experiments bindings must have role=prior")
        if self.prior_experiments != _sorted_prior_bindings(self.prior_experiments):
            raise ValueError("prior_experiments must use canonical history ordering")
        hashes = [item.artifact_sha256 for item in self.prior_experiments]
        if len(set(hashes)) != len(hashes):
            raise ValueError("prior experiment artifact hashes must be unique")
        if self.current_experiment.artifact_sha256 in hashes:
            raise ValueError("current experiment artifact cannot also be a prior artifact")
        review_ids = [item.thesis_id for item in self.review_bindings]
        if len(set(review_ids)) != len(review_ids):
            raise ValueError("review bindings must have unique thesis IDs")
        return self


class ThesisIntelligenceBuildIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    suite_id: str = Field(pattern=_ID_PATTERN, max_length=80)
    suite_version: int = Field(ge=1)
    inputs: ThesisIntelligenceBuildInputs
    build_input_hash: str
    relative_artifact_path: str

    @field_validator("build_input_hash")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        _require_sha256(value)
        return value

    @field_validator("relative_artifact_path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or value != path.as_posix():
            raise ValueError("intelligence artifact path must be a normalized relative POSIX path")
        return value

    @model_validator(mode="after")
    def validate_build_identity(self) -> Self:
        expected_hash = canonical_model_hash(self.inputs)
        if self.build_input_hash != expected_hash:
            raise ValueError("build_input_hash does not match canonical build inputs")
        expected_path = intelligence_artifact_relative_path(
            suite_id=self.suite_id,
            run_id=self.inputs.current_experiment.run_id,
            build_input_hash=self.build_input_hash,
        ).as_posix()
        if expected_path != self.relative_artifact_path:
            raise ValueError("relative artifact path does not match build identity")
        return self


def compile_thesis_suite(suite: ThesisSuiteDeclaration) -> CompiledThesisSuite:
    """Compile a suite onto existing experiment and M1.7 semantic contracts."""
    suite = ThesisSuiteDeclaration.model_validate(suite.model_dump())
    experiment = AnalystExperimentManifest(
        schema_version=1,
        experiment_id=suite.suite_id,
        context=AnalystExperimentContext.model_validate(suite.context.model_dump()),
        families=tuple(
            AnalystExperimentFamily(id=item.thesis_id, queries=item.queries)
            for item in suite.theses
        ),
    )
    semantic_theses = tuple(_compile_semantic_thesis(suite, item) for item in suite.theses)
    return CompiledThesisSuite(
        suite_content_hash=canonical_model_hash(suite),
        experiment_manifest=experiment,
        semantic_theses=semantic_theses,
    )


def build_intelligence_inputs(
    suite: ThesisSuiteDeclaration,
    *,
    current_experiment: ExperimentArtifactBinding,
    prior_experiments: Sequence[ExperimentArtifactBinding] = (),
    review_bindings: Sequence[ThesisReviewBinding] = (),
) -> ThesisIntelligenceBuildInputs:
    """Canonicalize current/history/review bindings for deterministic identity."""
    suite = ThesisSuiteDeclaration.model_validate(suite.model_dump())
    current = ExperimentArtifactBinding.model_validate(current_experiment.model_dump())
    if current.role != "current":
        raise ThesisIntelligenceError("current experiment binding must have role=current")
    if current.experiment_id != suite.suite_id:
        raise ThesisIntelligenceError(
            "current experiment binding experiment_id must match suite_id"
        )

    priors = tuple(
        ExperimentArtifactBinding.model_validate(item.model_dump()) for item in prior_experiments
    )
    if any(item.role != "prior" for item in priors):
        raise ThesisIntelligenceError("all history bindings must have role=prior")
    prior_hashes = [item.artifact_sha256 for item in priors]
    if len(set(prior_hashes)) != len(prior_hashes):
        raise ThesisIntelligenceError("history artifact hashes must be unique")
    if current.artifact_sha256 in prior_hashes:
        raise ThesisIntelligenceError("current artifact cannot also be supplied as history")
    priors = _sorted_prior_bindings(priors)

    thesis_order = {item.thesis_id: index for index, item in enumerate(suite.theses)}
    reviews = tuple(
        ThesisReviewBinding.model_validate(item.model_dump()) for item in review_bindings
    )
    if any(item.thesis_id not in thesis_order for item in reviews):
        raise ThesisIntelligenceError("review binding references a thesis outside the suite")
    review_ids = [item.thesis_id for item in reviews]
    if len(set(review_ids)) != len(review_ids):
        raise ThesisIntelligenceError("review bindings must have unique thesis IDs")
    reviews = tuple(sorted(reviews, key=lambda item: thesis_order[item.thesis_id]))

    return ThesisIntelligenceBuildInputs(
        suite_content_hash=canonical_model_hash(suite),
        current_experiment=current,
        prior_experiments=priors,
        review_bindings=reviews,
    )


def build_intelligence_identity(
    suite: ThesisSuiteDeclaration,
    *,
    current_experiment: ExperimentArtifactBinding,
    prior_experiments: Sequence[ExperimentArtifactBinding] = (),
    review_bindings: Sequence[ThesisReviewBinding] = (),
) -> ThesisIntelligenceBuildIdentity:
    inputs = build_intelligence_inputs(
        suite,
        current_experiment=current_experiment,
        prior_experiments=prior_experiments,
        review_bindings=review_bindings,
    )
    digest = canonical_model_hash(inputs)
    relative = intelligence_artifact_relative_path(
        suite_id=suite.suite_id,
        run_id=inputs.current_experiment.run_id,
        build_input_hash=digest,
    )
    return ThesisIntelligenceBuildIdentity(
        suite_id=suite.suite_id,
        suite_version=suite.suite_version,
        inputs=inputs,
        build_input_hash=digest,
        relative_artifact_path=relative.as_posix(),
    )


def intelligence_artifact_relative_path(
    *, suite_id: str, run_id: str, build_input_hash: str
) -> PurePosixPath:
    if not suite_id or not run_id:
        raise ThesisIntelligenceError("suite_id and run_id must be non-blank")
    _require_sha256(build_input_hash)
    return PurePosixPath(
        "artifacts",
        "intelligence",
        suite_id,
        run_id,
        f"{build_input_hash}.zip",
    )


def validate_artifact_file_sha256(binding: ExperimentArtifactBinding, path: Path) -> None:
    actual = _sha256_file(path)
    if actual != binding.artifact_sha256:
        expected = binding.artifact_sha256
        raise ThesisIntelligenceError(
            f"experiment artifact SHA-256 mismatch: expected {expected}, got {actual}"
        )


def canonical_model_hash(model: BaseModel) -> str:
    return hashlib.sha256(_canonical_json_bytes(model)).hexdigest()


def _compile_semantic_thesis(
    suite: ThesisSuiteDeclaration,
    thesis: ThesisDeclaration,
) -> AnalystSemanticThesisDeclaration:
    reward_terms = thesis.semantic.reward_grammar_terms
    return AnalystSemanticThesisDeclaration(
        spec_version="analyst-semantic-thesis-v1",
        thesis_id=thesis.thesis_id,
        version=thesis.thesis_version,
        label=thesis.label,
        target_set_ids=(f"{suite.suite_id}--{thesis.thesis_id}",),
        theme=AnalystSemanticRule(terms=thesis.semantic.theme_terms),
        mechanic=AnalystSemanticRule(terms=thesis.semantic.mechanic_terms),
        reward_grammar=(None if reward_terms is None else AnalystSemanticRule(terms=reward_terms)),
    )


def _canonical_json_bytes(model: BaseModel) -> bytes:
    value = _canonicalize(model.model_dump(mode="python"))
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _canonicalize(value: object) -> object:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ThesisIntelligenceError("canonical timestamps must be timezone-aware")
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, BaseModel):
        return _canonicalize(value.model_dump(mode="python"))
    if isinstance(value, Mapping):
        return {str(key): _canonicalize(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_canonicalize(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise ThesisIntelligenceError(
        f"unsupported canonical thesis-intelligence value: {type(value).__name__}"
    )


def _sorted_prior_bindings(
    values: Iterable[ExperimentArtifactBinding],
) -> tuple[ExperimentArtifactBinding, ...]:
    return tuple(
        sorted(
            values,
            key=lambda item: (
                item.snapshot_created_at.astimezone(UTC),
                item.experiment_id,
                item.run_id,
                item.artifact_sha256,
            ),
        )
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


def _require_sha256(value: str) -> None:
    invalid = len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    )
    if invalid:
        raise ValueError("value must be a lowercase SHA-256 hex digest")
