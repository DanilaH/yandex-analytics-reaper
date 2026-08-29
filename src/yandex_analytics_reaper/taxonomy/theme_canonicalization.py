from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from enum import StrEnum
from itertools import combinations
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .registries import normalize_taxonomy_label
from .sampling import (
    SPEC_VERSION as TAXONOMY_DIVERSITY_SAMPLE_SPEC_VERSION,
    TaxonomyDiversitySampleReport,
)

THEME_CANDIDATE_MANIFEST_SPEC_VERSION: Literal[
    "taxonomy-theme-candidate-manifest-v1"
] = "taxonomy-theme-candidate-manifest-v1"
THEME_CANONICALIZATION_ANNOTATION_SPEC_VERSION: Literal[
    "taxonomy-theme-canonicalization-annotation-v1"
] = "taxonomy-theme-canonicalization-annotation-v1"
THEME_CANONICALIZATION_GOLD_SPEC_VERSION: Literal[
    "taxonomy-theme-canonicalization-gold-v1"
] = "taxonomy-theme-canonicalization-gold-v1"
THEME_CANONICALIZATION_SPEC_VERSION: Literal[
    "taxonomy-theme-canonicalization-v1"
] = "taxonomy-theme-canonicalization-v1"
THEME_CANONICALIZATION_CONTRACT_VERSION: Literal[
    "theme-canonicalization-v1"
] = "theme-canonicalization-v1"
THEME_CANONICALIZATION_CONTRACT_V1_CONTENT_HASH = "HASH_PLACEHOLDER"
THEME_CANONICALIZATION_TARGET = 0.95
_RULES = (
    "manifest_reviews_every_sample_listing_once_in_sample_order",
    "candidate_terms_bind_only_to_exact_sample_members",
    "candidate_terms_follow_sample_order_and_preserve_manifest_term_order",
    "candidate_term_ids_are_unique_nonblank_trimmed",
    "candidate_surface_forms_are_nonblank_trimmed_and_not_normalized",
    "annotation_batches_cover_every_manifest_term_exactly_in_manifest_order",
    "canonical_resolution_requires_normalized_theme_key",
    "not_theme_and_unknown_resolutions_forbid_theme_key_and_require_rationale",
    "at_least_two_source_batches_with_unique_annotator_ids_required_for_gold",
    "gold_source_batches_bind_exact_ids_annotators_and_content_hashes",
    "gold_decisions_cover_every_manifest_term_exactly_in_manifest_order",
    "pairwise_agreement_compares_exact_resolution_and_canonical_theme_key",
    "pairwise_comparison_count_is_choose_annotators_2_times_candidate_term_count",
    "initial_theme_canonicalization_target_is_0_95_pairwise_exact_outcome_agreement",
    "target_result_does_not_prove_candidate_extraction_completeness",
    "unknown_not_theme_and_canonical_assignment_rates_remain_separate_diagnostics",
    "gold_alignment_is_adjudication_alignment_not_independent_accuracy",
    "confusion_pairs_are_symmetric_outcome_pairs_sorted_by_count_then_token",
    "open_theme_metric_vocabulary_is_lexical_union_of_gold_and_source_canonical_keys",
    "zero_denominator_theme_metrics_are_none_not_zero",
    "theme_keys_match_game_taxonomy_draft_open_entity_normalization",
    "purposive_sample_metrics_do_not_estimate_population_prevalence",
)


class ThemeCanonicalizationResolution(StrEnum):
    CANONICAL = "canonical"
    NOT_THEME = "not_theme"
    UNKNOWN = "unknown"


class ThemeCanonicalizationError(ValueError):
    """Theme canonicalization evidence violates the frozen Phase 3 protocol."""


class ThemeCandidateTerm(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    term_id: str
    platform_listing_id: str
    surface_form: str
    language: str | None = None

    @field_validator("term_id", "platform_listing_id", "surface_form")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        if not value or value != value.strip():
            raise ValueError("theme candidate text fields must be nonblank and trimmed")
        return value

    @field_validator("language")
    @classmethod
    def validate_language(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value or value != value.strip() or value != value.lower():
            raise ValueError("theme candidate language must be lowercase, nonblank, and trimmed")
        if any(character.isspace() for character in value):
            raise ValueError("theme candidate language cannot contain whitespace")
        return value


class ThemeCandidateManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: Literal["taxonomy-theme-candidate-manifest-v1"] = (
        THEME_CANDIDATE_MANIFEST_SPEC_VERSION
    )
    contract_version: Literal["theme-canonicalization-v1"] = (
        THEME_CANONICALIZATION_CONTRACT_VERSION
    )
    manifest_id: str
    sample_id: str
    sample_content_hash: str
    created_at: datetime
    reviewed_listing_ids: tuple[str, ...] = Field(min_length=100, max_length=200)
    terms: tuple[ThemeCandidateTerm, ...] = Field(min_length=1)

    @field_validator("manifest_id", "sample_id")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        return _trimmed_identifier(value, "theme candidate manifest identifier")

    @field_validator("sample_content_hash")
    @classmethod
    def validate_sample_hash(cls, value: str) -> str:
        _validate_sha256(value, "theme candidate manifest sample hash")
        return value

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return _utc_datetime(value, "theme candidate manifest created_at")

    @model_validator(mode="after")
    def validate_unique_terms(self) -> Self:
        term_ids = tuple(term.term_id for term in self.terms)
        if len(term_ids) != len(set(term_ids)):
            raise ValueError("theme candidate manifest term IDs must be unique")
        listing_ids = self.reviewed_listing_ids
        if len(listing_ids) != len(set(listing_ids)):
            raise ValueError("theme candidate reviewed listing IDs must be unique")
        return self


class ValidatedThemeCandidateManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: Literal["taxonomy-theme-candidate-manifest-v1"] = (
        THEME_CANDIDATE_MANIFEST_SPEC_VERSION
    )
    contract_version: Literal["theme-canonicalization-v1"] = (
        THEME_CANONICALIZATION_CONTRACT_VERSION
    )
    contract_content_hash: str = THEME_CANONICALIZATION_CONTRACT_V1_CONTENT_HASH
    manifest_id: str
    sample_id: str
    sample_content_hash: str
    created_at: datetime
    reviewed_listing_ids: tuple[str, ...]
    terms: tuple[ThemeCandidateTerm, ...]
    manifest_content_hash: str

    @field_validator("contract_content_hash", "sample_content_hash", "manifest_content_hash")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        _validate_sha256(value, "validated theme manifest hash")
        return value


class ThemeCanonicalizationDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    term_id: str
    resolution: ThemeCanonicalizationResolution
    canonical_theme_key: str | None = None
    rationale: str | None = None

    @field_validator("term_id")
    @classmethod
    def validate_term_id(cls, value: str) -> str:
        return _trimmed_identifier(value, "theme canonicalization term ID")

    @field_validator("canonical_theme_key")
    @classmethod
    def validate_theme_key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_taxonomy_label(value)

    @field_validator("rationale")
    @classmethod
    def validate_rationale(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _trimmed_identifier(value, "theme canonicalization rationale")

    @model_validator(mode="after")
    def validate_resolution(self) -> Self:
        if self.resolution is ThemeCanonicalizationResolution.CANONICAL:
            if self.canonical_theme_key is None:
                raise ValueError("canonical theme resolution requires canonical_theme_key")
            return self
        if self.canonical_theme_key is not None:
            raise ValueError("not_theme/unknown theme resolutions cannot carry a theme key")
        if self.rationale is None:
            raise ValueError("not_theme/unknown theme resolutions require rationale")
        return self


class ThemeCanonicalizationBatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: Literal["taxonomy-theme-canonicalization-annotation-v1"] = (
        THEME_CANONICALIZATION_ANNOTATION_SPEC_VERSION
    )
    contract_version: Literal["theme-canonicalization-v1"] = (
        THEME_CANONICALIZATION_CONTRACT_VERSION
    )
    batch_id: str
    annotator_id: str
    manifest_id: str
    manifest_content_hash: str
    sample_id: str
    sample_content_hash: str
    created_at: datetime
    decisions: tuple[ThemeCanonicalizationDecision, ...] = Field(min_length=1)

    @field_validator("batch_id", "annotator_id", "manifest_id", "sample_id")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        return _trimmed_identifier(value, "theme canonicalization batch identifier")

    @field_validator("manifest_content_hash", "sample_content_hash")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        _validate_sha256(value, "theme canonicalization batch hash")
        return value

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return _utc_datetime(value, "theme canonicalization batch created_at")

    @model_validator(mode="after")
    def validate_unique_decisions(self) -> Self:
        term_ids = tuple(decision.term_id for decision in self.decisions)
        if len(term_ids) != len(set(term_ids)):
            raise ValueError("theme canonicalization batch term IDs must be unique")
        return self


class ValidatedThemeCanonicalizationBatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: Literal["taxonomy-theme-canonicalization-annotation-v1"] = (
        THEME_CANONICALIZATION_ANNOTATION_SPEC_VERSION
    )
    contract_version: Literal["theme-canonicalization-v1"] = (
        THEME_CANONICALIZATION_CONTRACT_VERSION
    )
    contract_content_hash: str = THEME_CANONICALIZATION_CONTRACT_V1_CONTENT_HASH
    batch_id: str
    annotator_id: str
    manifest_id: str
    manifest_content_hash: str
    sample_id: str
    sample_content_hash: str
    created_at: datetime
    decisions: tuple[ThemeCanonicalizationDecision, ...]
    annotation_batch_hash: str

    @field_validator(
        "contract_content_hash",
        "manifest_content_hash",
        "sample_content_hash",
        "annotation_batch_hash",
    )
    @classmethod
    def validate_hash(cls, value: str) -> str:
        _validate_sha256(value, "validated theme annotation hash")
        return value


class ThemeCanonicalizationSourceBatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    batch_id: str
    annotator_id: str
    annotation_batch_hash: str

    @field_validator("batch_id", "annotator_id")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        return _trimmed_identifier(value, "theme canonicalization source identifier")

    @field_validator("annotation_batch_hash")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        _validate_sha256(value, "theme canonicalization source hash")
        return value


class ThemeCanonicalizationGoldDeclaration(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: Literal["taxonomy-theme-canonicalization-gold-v1"] = (
        THEME_CANONICALIZATION_GOLD_SPEC_VERSION
    )
    contract_version: Literal["theme-canonicalization-v1"] = (
        THEME_CANONICALIZATION_CONTRACT_VERSION
    )
    gold_set_id: str
    manifest_id: str
    manifest_content_hash: str
    sample_id: str
    sample_content_hash: str
    adjudicator_id: str
    adjudicated_at: datetime
    source_annotation_batch_hashes: tuple[str, ...] = Field(min_length=2)
    decisions: tuple[ThemeCanonicalizationDecision, ...] = Field(min_length=1)

    @field_validator("gold_set_id", "manifest_id", "sample_id", "adjudicator_id")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        return _trimmed_identifier(value, "theme canonicalization gold identifier")

    @field_validator("manifest_content_hash", "sample_content_hash")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        _validate_sha256(value, "theme canonicalization gold hash")
        return value

    @field_validator("adjudicated_at")
    @classmethod
    def validate_adjudicated_at(cls, value: datetime) -> datetime:
        return _utc_datetime(value, "theme canonicalization adjudicated_at")

    @field_validator("source_annotation_batch_hashes")
    @classmethod
    def validate_source_hashes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("theme gold source annotation hashes must be unique")
        for value in values:
            _validate_sha256(value, "theme gold source annotation hash")
        return values

    @model_validator(mode="after")
    def validate_unique_decisions(self) -> Self:
        term_ids = tuple(decision.term_id for decision in self.decisions)
        if len(term_ids) != len(set(term_ids)):
            raise ValueError("theme gold decision term IDs must be unique")
        return self


class ThemeCanonicalizationGoldReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: Literal["taxonomy-theme-canonicalization-gold-v1"] = (
        THEME_CANONICALIZATION_GOLD_SPEC_VERSION
    )
    contract_version: Literal["theme-canonicalization-v1"] = (
        THEME_CANONICALIZATION_CONTRACT_VERSION
    )
    contract_content_hash: str = THEME_CANONICALIZATION_CONTRACT_V1_CONTENT_HASH
    gold_set_id: str
    manifest_id: str
    manifest_content_hash: str
    sample_id: str
    sample_content_hash: str
    adjudicator_id: str
    adjudicated_at: datetime
    source_batches: tuple[ThemeCanonicalizationSourceBatch, ...] = Field(min_length=2)
    decisions: tuple[ThemeCanonicalizationDecision, ...] = Field(min_length=1)
    gold_set_content_hash: str

    @field_validator(
        "contract_content_hash",
        "manifest_content_hash",
        "sample_content_hash",
        "gold_set_content_hash",
    )
    @classmethod
    def validate_hash(cls, value: str) -> str:
        _validate_sha256(value, "theme gold report hash")
        return value


class ThemeCanonicalizationConfusionPair(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    outcome_a: str
    outcome_b: str
    comparison_count: int = Field(ge=1)
    comparison_rate: float = Field(gt=0.0, le=1.0)
    term_ids: tuple[str, ...] = Field(min_length=1)

    @field_validator("outcome_a", "outcome_b")
    @classmethod
    def validate_outcome(cls, value: str) -> str:
        return _trimmed_identifier(value, "theme confusion outcome")

    @field_validator("term_ids")
    @classmethod
    def validate_term_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if any(not value for value in normalized):
            raise ValueError("theme confusion term IDs cannot be blank")
        if len(normalized) != len(set(normalized)):
            raise ValueError("theme confusion term IDs must be unique")
        return normalized

    @model_validator(mode="after")
    def validate_pair(self) -> Self:
        if self.outcome_a >= self.outcome_b:
            raise ValueError("theme confusion outcomes must be different and lexically ordered")
        if len(self.term_ids) > self.comparison_count:
            raise ValueError("theme confusion evidence cannot exceed comparison count")
        return self


class ThemeCanonicalKeyMetric(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    canonical_theme_key: str
    gold_support_count: int = Field(ge=0)
    annotation_assignment_count: int = Field(ge=0)
    gold_alignment_true_positive_count: int = Field(ge=0)
    gold_alignment_false_positive_count: int = Field(ge=0)
    gold_alignment_false_negative_count: int = Field(ge=0)
    gold_alignment_precision: float | None = Field(default=None, ge=0.0, le=1.0)
    gold_alignment_recall: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator("canonical_theme_key")
    @classmethod
    def validate_theme_key(cls, value: str) -> str:
        return normalize_taxonomy_label(value)

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        if (
            self.gold_alignment_true_positive_count
            + self.gold_alignment_false_positive_count
            != self.annotation_assignment_count
        ):
            raise ValueError("theme key assignments must equal true + false positives")
        precision_denominator = (
            self.gold_alignment_true_positive_count + self.gold_alignment_false_positive_count
        )
        recall_denominator = (
            self.gold_alignment_true_positive_count + self.gold_alignment_false_negative_count
        )
        if self.gold_alignment_precision != _optional_rate(
            self.gold_alignment_true_positive_count,
            precision_denominator,
        ):
            raise ValueError("theme key precision is inconsistent with counts")
        if self.gold_alignment_recall != _optional_rate(
            self.gold_alignment_true_positive_count,
            recall_denominator,
        ):
            raise ValueError("theme key recall is inconsistent with counts")
        return self


class ThemeCanonicalizationReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: Literal["taxonomy-theme-canonicalization-v1"] = (
        THEME_CANONICALIZATION_SPEC_VERSION
    )
    contract_version: Literal["theme-canonicalization-v1"] = (
        THEME_CANONICALIZATION_CONTRACT_VERSION
    )
    contract_content_hash: str = THEME_CANONICALIZATION_CONTRACT_V1_CONTENT_HASH
    manifest_id: str
    manifest_content_hash: str
    sample_id: str
    sample_content_hash: str
    gold_set_id: str
    gold_set_content_hash: str
    source_batches: tuple[ThemeCanonicalizationSourceBatch, ...] = Field(min_length=2)
    total_candidate_terms: int = Field(ge=1)
    source_batch_count: int = Field(ge=2)
    pairwise_comparison_count: int = Field(ge=1)
    pairwise_agreement_count: int = Field(ge=0)
    pairwise_disagreement_count: int = Field(ge=0)
    pairwise_agreement_rate: float = Field(ge=0.0, le=1.0)
    initial_theme_canonicalization_target: float = Field(ge=0.0, le=1.0)
    meets_initial_theme_canonicalization_target: bool
    unanimous_term_count: int = Field(ge=0)
    unanimous_term_rate: float = Field(ge=0.0, le=1.0)
    canonical_assignment_count: int = Field(ge=0)
    canonical_assignment_rate: float = Field(ge=0.0, le=1.0)
    unknown_assignment_count: int = Field(ge=0)
    unknown_assignment_rate: float = Field(ge=0.0, le=1.0)
    not_theme_assignment_count: int = Field(ge=0)
    not_theme_assignment_rate: float = Field(ge=0.0, le=1.0)
    gold_alignment_count: int = Field(ge=0)
    gold_alignment_rate: float = Field(ge=0.0, le=1.0)
    disagreement_term_ids: tuple[str, ...]
    confusion_pairs: tuple[ThemeCanonicalizationConfusionPair, ...]
    theme_metrics: tuple[ThemeCanonicalKeyMetric, ...]
    canonical_gold_theme_keys: tuple[str, ...]
    report_content_hash: str

    @field_validator("manifest_id", "sample_id", "gold_set_id")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        return _trimmed_identifier(value, "theme canonicalization report identifier")

    @field_validator(
        "contract_content_hash",
        "manifest_content_hash",
        "sample_content_hash",
        "gold_set_content_hash",
        "report_content_hash",
    )
    @classmethod
    def validate_hash(cls, value: str) -> str:
        _validate_sha256(value, "theme canonicalization report hash")
        return value

    @field_validator("disagreement_term_ids", "canonical_gold_theme_keys")
    @classmethod
    def validate_unique_text(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not value or value != value.strip() for value in values):
            raise ValueError("theme report identifiers cannot be blank or untrimmed")
        if len(values) != len(set(values)):
            raise ValueError("theme report identifiers must be unique")
        return values

    @model_validator(mode="after")
    def validate_report(self) -> Self:
        if self.contract_content_hash != THEME_CANONICALIZATION_CONTRACT_V1_CONTENT_HASH:
            raise ValueError("theme canonicalization contract hash does not match v1")
        if self.source_batch_count != len(self.source_batches):
            raise ValueError("theme source_batch_count must match source batch refs")
        _validate_source_batch_uniqueness(self.source_batches)
        pair_count = self.source_batch_count * (self.source_batch_count - 1) // 2
        expected_comparisons = pair_count * self.total_candidate_terms
        if self.pairwise_comparison_count != expected_comparisons:
            raise ValueError("theme pairwise comparison count is inconsistent")
        if (
            self.pairwise_agreement_count + self.pairwise_disagreement_count
            != self.pairwise_comparison_count
        ):
            raise ValueError("theme pairwise counts must cover every comparison")
        if self.pairwise_agreement_rate != (
            self.pairwise_agreement_count / self.pairwise_comparison_count
        ):
            raise ValueError("theme pairwise agreement rate is inconsistent")
        if self.initial_theme_canonicalization_target != THEME_CANONICALIZATION_TARGET:
            raise ValueError("theme canonicalization target does not match v1")
        if self.meets_initial_theme_canonicalization_target != (
            self.pairwise_agreement_rate >= THEME_CANONICALIZATION_TARGET
        ):
            raise ValueError("theme canonicalization target result is inconsistent")
        if self.unanimous_term_count > self.total_candidate_terms:
            raise ValueError("theme unanimous term count exceeds candidate count")
        if self.unanimous_term_rate != self.unanimous_term_count / self.total_candidate_terms:
            raise ValueError("theme unanimous term rate is inconsistent")
        total_assignments = self.total_candidate_terms * self.source_batch_count
        if (
            self.canonical_assignment_count
            + self.unknown_assignment_count
            + self.not_theme_assignment_count
            != total_assignments
        ):
            raise ValueError("theme assignment-state counts must cover every assignment")
        _validate_rate(
            self.canonical_assignment_count,
            self.canonical_assignment_rate,
            total_assignments,
            "canonical",
        )
        _validate_rate(
            self.unknown_assignment_count,
            self.unknown_assignment_rate,
            total_assignments,
            "unknown",
        )
        _validate_rate(
            self.not_theme_assignment_count,
            self.not_theme_assignment_rate,
            total_assignments,
            "not-theme",
        )
        if self.gold_alignment_count > total_assignments:
            raise ValueError("theme gold alignment count exceeds total assignments")
        if self.gold_alignment_rate != self.gold_alignment_count / total_assignments:
            raise ValueError("theme gold alignment rate is inconsistent")
        if len(self.disagreement_term_ids) != (
            self.total_candidate_terms - self.unanimous_term_count
        ):
            raise ValueError("theme disagreement IDs must cover every non-unanimous term")
        disagreement_set = set(self.disagreement_term_ids)
        if sum(pair.comparison_count for pair in self.confusion_pairs) != (
            self.pairwise_disagreement_count
        ):
            raise ValueError("theme confusion pairs must cover every disagreement")
        for pair in self.confusion_pairs:
            if pair.comparison_rate != pair.comparison_count / self.pairwise_comparison_count:
                raise ValueError("theme confusion pair rate is inconsistent")
            if any(term_id not in disagreement_set for term_id in pair.term_ids):
                raise ValueError("theme confusion evidence must reference disagreement terms")
        expected_pair_order = tuple(
            sorted(
                self.confusion_pairs,
                key=lambda pair: (-pair.comparison_count, pair.outcome_a, pair.outcome_b),
            )
        )
        if self.confusion_pairs != expected_pair_order:
            raise ValueError("theme confusion pairs must follow deterministic ordering")
        metric_keys = tuple(metric.canonical_theme_key for metric in self.theme_metrics)
        if metric_keys != tuple(sorted(metric_keys)):
            raise ValueError("theme metrics must follow lexical canonical-key order")
        if self.canonical_gold_theme_keys != tuple(sorted(self.canonical_gold_theme_keys)):
            raise ValueError("canonical gold theme keys must follow lexical order")
        return self


def validate_theme_candidate_manifest(
    sample: TaxonomyDiversitySampleReport,
    manifest: ThemeCandidateManifest,
) -> ValidatedThemeCandidateManifest:
    sample = TaxonomyDiversitySampleReport.model_validate(sample.model_dump(mode="python"))
    manifest = ThemeCandidateManifest.model_validate(manifest.model_dump(mode="python"))
    _validate_contract()
    _validate_manifest_binding(sample, manifest)
    content_hash = _content_hash(_manifest_payload(manifest))
    return ValidatedThemeCandidateManifest(
        manifest_id=manifest.manifest_id,
        sample_id=manifest.sample_id,
        sample_content_hash=manifest.sample_content_hash,
        created_at=manifest.created_at,
        reviewed_listing_ids=manifest.reviewed_listing_ids,
        terms=manifest.terms,
        manifest_content_hash=content_hash,
    )


def validate_theme_canonicalization_batch(
    sample: TaxonomyDiversitySampleReport,
    manifest: ThemeCandidateManifest,
    batch: ThemeCanonicalizationBatch,
) -> ValidatedThemeCanonicalizationBatch:
    validated_manifest = validate_theme_candidate_manifest(sample, manifest)
    batch = ThemeCanonicalizationBatch.model_validate(batch.model_dump(mode="python"))
    _validate_batch_binding(validated_manifest, batch)
    batch_hash = _content_hash(_annotation_payload(batch))
    return ValidatedThemeCanonicalizationBatch(
        batch_id=batch.batch_id,
        annotator_id=batch.annotator_id,
        manifest_id=batch.manifest_id,
        manifest_content_hash=batch.manifest_content_hash,
        sample_id=batch.sample_id,
        sample_content_hash=batch.sample_content_hash,
        created_at=batch.created_at,
        decisions=batch.decisions,
        annotation_batch_hash=batch_hash,
    )


def build_theme_canonicalization_gold_set(
    sample: TaxonomyDiversitySampleReport,
    manifest: ThemeCandidateManifest,
    declaration: ThemeCanonicalizationGoldDeclaration,
    annotation_batches: tuple[ThemeCanonicalizationBatch, ...],
) -> ThemeCanonicalizationGoldReport:
    validated_manifest = validate_theme_candidate_manifest(sample, manifest)
    declaration = ThemeCanonicalizationGoldDeclaration.model_validate(
        declaration.model_dump(mode="python")
    )
    _validate_gold_binding(validated_manifest, declaration)
    validated = tuple(
        validate_theme_canonicalization_batch(sample, manifest, batch)
        for batch in annotation_batches
    )
    if len(validated) < 2:
        raise ThemeCanonicalizationError(
            "theme gold set requires at least two independent annotation batches"
        )
    _validate_validated_batch_uniqueness(validated)
    validated_hashes = tuple(batch.annotation_batch_hash for batch in validated)
    if set(validated_hashes) != set(declaration.source_annotation_batch_hashes):
        raise ThemeCanonicalizationError(
            "theme gold source hashes must exactly match supplied validated batches"
        )
    by_hash = {batch.annotation_batch_hash: batch for batch in validated}
    ordered = tuple(by_hash[value] for value in declaration.source_annotation_batch_hashes)
    source_batches = tuple(
        ThemeCanonicalizationSourceBatch(
            batch_id=batch.batch_id,
            annotator_id=batch.annotator_id,
            annotation_batch_hash=batch.annotation_batch_hash,
        )
        for batch in ordered
    )
    payload = _gold_payload(declaration, source_batches)
    gold_hash = _content_hash(payload)
    return ThemeCanonicalizationGoldReport(
        gold_set_id=declaration.gold_set_id,
        manifest_id=declaration.manifest_id,
        manifest_content_hash=declaration.manifest_content_hash,
        sample_id=declaration.sample_id,
        sample_content_hash=declaration.sample_content_hash,
        adjudicator_id=declaration.adjudicator_id,
        adjudicated_at=declaration.adjudicated_at,
        source_batches=source_batches,
        decisions=declaration.decisions,
        gold_set_content_hash=gold_hash,
    )


def validate_theme_canonicalization_gold_report(
    sample: TaxonomyDiversitySampleReport,
    manifest: ThemeCandidateManifest,
    report: ThemeCanonicalizationGoldReport,
) -> ThemeCanonicalizationGoldReport:
    validated_manifest = validate_theme_candidate_manifest(sample, manifest)
    report = ThemeCanonicalizationGoldReport.model_validate(report.model_dump(mode="python"))
    if report.contract_content_hash != THEME_CANONICALIZATION_CONTRACT_V1_CONTENT_HASH:
        raise ThemeCanonicalizationError("theme gold contract hash does not match v1")
    _validate_report_binding(validated_manifest, report)
    _validate_source_batch_uniqueness(report.source_batches)
    expected_hash = _content_hash(_gold_report_payload(report))
    if report.gold_set_content_hash != expected_hash:
        raise ThemeCanonicalizationError("theme gold content hash does not match report")
    return report


def build_theme_canonicalization_report(
    sample: TaxonomyDiversitySampleReport,
    manifest: ThemeCandidateManifest,
    gold_set: ThemeCanonicalizationGoldReport,
    annotation_batches: tuple[ThemeCanonicalizationBatch, ...],
) -> ThemeCanonicalizationReport:
    validated_manifest = validate_theme_candidate_manifest(sample, manifest)
    gold_set = validate_theme_canonicalization_gold_report(sample, manifest, gold_set)
    validated_batches = _validate_analysis_batches(
        sample,
        manifest,
        gold_set,
        annotation_batches,
    )
    term_count = len(validated_manifest.terms)
    source_batch_count = len(validated_batches)
    pair_count = source_batch_count * (source_batch_count - 1) // 2
    pairwise_comparison_count = pair_count * term_count
    pairwise_agreement_count = 0
    disagreement_term_ids: list[str] = []
    confusion_counts: Counter[tuple[str, str]] = Counter()
    confusion_terms: dict[tuple[str, str], list[str]] = {}

    for index, term in enumerate(validated_manifest.terms):
        outcomes = tuple(_outcome_token(batch.decisions[index]) for batch in validated_batches)
        if len(set(outcomes)) == 1:
            pairwise_agreement_count += pair_count
            continue
        disagreement_term_ids.append(term.term_id)
        for left_index, right_index in combinations(range(source_batch_count), 2):
            left = outcomes[left_index]
            right = outcomes[right_index]
            if left == right:
                pairwise_agreement_count += 1
                continue
            pair = tuple(sorted((left, right)))
            confusion_counts[pair] += 1
            evidence = confusion_terms.setdefault(pair, [])
            if term.term_id not in evidence:
                evidence.append(term.term_id)

    pairwise_disagreement_count = pairwise_comparison_count - pairwise_agreement_count
    all_decisions = tuple(
        decision for batch in validated_batches for decision in batch.decisions
    )
    canonical_count = sum(
        decision.resolution is ThemeCanonicalizationResolution.CANONICAL
        for decision in all_decisions
    )
    unknown_count = sum(
        decision.resolution is ThemeCanonicalizationResolution.UNKNOWN
        for decision in all_decisions
    )
    not_theme_count = sum(
        decision.resolution is ThemeCanonicalizationResolution.NOT_THEME
        for decision in all_decisions
    )
    gold_alignment_count = sum(
        _decision_outcome(annotation_decision) == _decision_outcome(gold_decision)
        for batch in validated_batches
        for annotation_decision, gold_decision in zip(
            batch.decisions,
            gold_set.decisions,
            strict=True,
        )
    )
    confusion_pairs = _build_confusion_pairs(
        confusion_counts,
        confusion_terms,
        pairwise_comparison_count,
    )
    theme_metrics = _build_theme_metrics(gold_set, validated_batches)
    canonical_gold_keys = tuple(
        sorted(
            {
                decision.canonical_theme_key
                for decision in gold_set.decisions
                if decision.resolution is ThemeCanonicalizationResolution.CANONICAL
                and decision.canonical_theme_key is not None
            }
        )
    )
    source_batches = tuple(
        ThemeCanonicalizationSourceBatch(
            batch_id=batch.batch_id,
            annotator_id=batch.annotator_id,
            annotation_batch_hash=batch.annotation_batch_hash,
        )
        for batch in validated_batches
    )
    total_assignments = term_count * source_batch_count
    agreement_rate = pairwise_agreement_count / pairwise_comparison_count
    unanimous_count = term_count - len(disagreement_term_ids)
    payload = _report_payload(
        manifest=validated_manifest,
        gold_set=gold_set,
        source_batches=source_batches,
        pairwise_comparison_count=pairwise_comparison_count,
        pairwise_agreement_count=pairwise_agreement_count,
        pairwise_disagreement_count=pairwise_disagreement_count,
        canonical_count=canonical_count,
        unknown_count=unknown_count,
        not_theme_count=not_theme_count,
        gold_alignment_count=gold_alignment_count,
        disagreement_term_ids=tuple(disagreement_term_ids),
        confusion_pairs=confusion_pairs,
        theme_metrics=theme_metrics,
        canonical_gold_keys=canonical_gold_keys,
    )
    report_hash = _content_hash(payload)
    return ThemeCanonicalizationReport(
        manifest_id=validated_manifest.manifest_id,
        manifest_content_hash=validated_manifest.manifest_content_hash,
        sample_id=validated_manifest.sample_id,
        sample_content_hash=validated_manifest.sample_content_hash,
        gold_set_id=gold_set.gold_set_id,
        gold_set_content_hash=gold_set.gold_set_content_hash,
        source_batches=source_batches,
        total_candidate_terms=term_count,
        source_batch_count=source_batch_count,
        pairwise_comparison_count=pairwise_comparison_count,
        pairwise_agreement_count=pairwise_agreement_count,
        pairwise_disagreement_count=pairwise_disagreement_count,
        pairwise_agreement_rate=agreement_rate,
        initial_theme_canonicalization_target=THEME_CANONICALIZATION_TARGET,
        meets_initial_theme_canonicalization_target=(
            agreement_rate >= THEME_CANONICALIZATION_TARGET
        ),
        unanimous_term_count=unanimous_count,
        unanimous_term_rate=unanimous_count / term_count,
        canonical_assignment_count=canonical_count,
        canonical_assignment_rate=canonical_count / total_assignments,
        unknown_assignment_count=unknown_count,
        unknown_assignment_rate=unknown_count / total_assignments,
        not_theme_assignment_count=not_theme_count,
        not_theme_assignment_rate=not_theme_count / total_assignments,
        gold_alignment_count=gold_alignment_count,
        gold_alignment_rate=gold_alignment_count / total_assignments,
        disagreement_term_ids=tuple(disagreement_term_ids),
        confusion_pairs=confusion_pairs,
        theme_metrics=theme_metrics,
        canonical_gold_theme_keys=canonical_gold_keys,
        report_content_hash=report_hash,
    )


def validate_theme_canonicalization_report(
    sample: TaxonomyDiversitySampleReport,
    manifest: ThemeCandidateManifest,
    gold_set: ThemeCanonicalizationGoldReport,
    annotation_batches: tuple[ThemeCanonicalizationBatch, ...],
    report: ThemeCanonicalizationReport,
) -> ThemeCanonicalizationReport:
    report = ThemeCanonicalizationReport.model_validate(report.model_dump(mode="python"))
    expected = build_theme_canonicalization_report(
        sample,
        manifest,
        gold_set,
        annotation_batches,
    )
    if report != expected:
        raise ThemeCanonicalizationError(
            "persisted theme canonicalization report does not match rebuilt content"
        )
    return report


def theme_canonicalization_contract_content_hash() -> str:
    payload = {
        "contract_version": THEME_CANONICALIZATION_CONTRACT_VERSION,
        "candidate_manifest_spec_version": THEME_CANDIDATE_MANIFEST_SPEC_VERSION,
        "annotation_spec_version": THEME_CANONICALIZATION_ANNOTATION_SPEC_VERSION,
        "gold_spec_version": THEME_CANONICALIZATION_GOLD_SPEC_VERSION,
        "report_spec_version": THEME_CANONICALIZATION_SPEC_VERSION,
        "sample_spec_version": TAXONOMY_DIVERSITY_SAMPLE_SPEC_VERSION,
        "target": THEME_CANONICALIZATION_TARGET,
        "resolutions": [item.value for item in ThemeCanonicalizationResolution],
        "candidate_term_fields": list(ThemeCandidateTerm.model_fields),
        "manifest_fields": list(ThemeCandidateManifest.model_fields),
        "decision_fields": list(ThemeCanonicalizationDecision.model_fields),
        "annotation_batch_fields": list(ThemeCanonicalizationBatch.model_fields),
        "gold_declaration_fields": list(ThemeCanonicalizationGoldDeclaration.model_fields),
        "gold_report_fields": list(ThemeCanonicalizationGoldReport.model_fields),
        "confusion_pair_fields": list(ThemeCanonicalizationConfusionPair.model_fields),
        "theme_metric_fields": list(ThemeCanonicalKeyMetric.model_fields),
        "report_fields": list(ThemeCanonicalizationReport.model_fields),
        "rules": list(_RULES),
        "outcome_token": "theme:<canonical_key>|not_theme|unknown",
        "manifest_term_order": "sample-order-then-manifest-order-within-listing",
        "confusion_order": "descending-count-then-lexical-outcome-pair",
        "theme_metric_order": "lexical-open-canonical-key-union",
        "datetime_canonicalization": "timezone-aware-to-utc-isoformat",
        "content_hash_canonicalization": "json-sort-keys-compact-utf8-ensure-ascii-false",
    }
    return _content_hash(payload)


def _validate_contract() -> None:
    if theme_canonicalization_contract_content_hash() != (
        THEME_CANONICALIZATION_CONTRACT_V1_CONTENT_HASH
    ):
        raise ThemeCanonicalizationError(
            "theme canonicalization contract changed without a new version"
        )


def _validate_manifest_binding(
    sample: TaxonomyDiversitySampleReport,
    manifest: ThemeCandidateManifest,
) -> None:
    if manifest.sample_id != sample.sample_id or (
        manifest.sample_content_hash != sample.sample_content_hash
    ):
        raise ThemeCanonicalizationError("theme manifest must bind exact taxonomy sample")
    sample_ids = tuple(member.platform_listing_id for member in sample.selected)
    if manifest.reviewed_listing_ids != sample_ids:
        raise ThemeCanonicalizationError(
            "theme manifest must record every sample listing exactly in sample order"
        )
    order = {listing_id: index for index, listing_id in enumerate(sample_ids)}
    try:
        term_order = tuple(order[term.platform_listing_id] for term in manifest.terms)
    except KeyError as exc:
        raise ThemeCanonicalizationError(
            "theme candidate term references listing outside exact taxonomy sample"
        ) from exc
    if term_order != tuple(sorted(term_order)):
        raise ThemeCanonicalizationError(
            "theme candidate terms must follow sample listing order"
        )


def _validate_batch_binding(
    manifest: ValidatedThemeCandidateManifest,
    batch: ThemeCanonicalizationBatch,
) -> None:
    if (
        batch.manifest_id != manifest.manifest_id
        or batch.manifest_content_hash != manifest.manifest_content_hash
        or batch.sample_id != manifest.sample_id
        or batch.sample_content_hash != manifest.sample_content_hash
    ):
        raise ThemeCanonicalizationError(
            "theme annotation batch must bind exact validated manifest and sample"
        )
    expected_term_ids = tuple(term.term_id for term in manifest.terms)
    actual_term_ids = tuple(decision.term_id for decision in batch.decisions)
    if actual_term_ids != expected_term_ids:
        raise ThemeCanonicalizationError(
            "theme annotation decisions must cover every manifest term exactly in order"
        )


def _validate_gold_binding(
    manifest: ValidatedThemeCandidateManifest,
    declaration: ThemeCanonicalizationGoldDeclaration,
) -> None:
    if (
        declaration.manifest_id != manifest.manifest_id
        or declaration.manifest_content_hash != manifest.manifest_content_hash
        or declaration.sample_id != manifest.sample_id
        or declaration.sample_content_hash != manifest.sample_content_hash
    ):
        raise ThemeCanonicalizationError(
            "theme gold declaration must bind exact validated manifest and sample"
        )
    expected_term_ids = tuple(term.term_id for term in manifest.terms)
    actual_term_ids = tuple(decision.term_id for decision in declaration.decisions)
    if actual_term_ids != expected_term_ids:
        raise ThemeCanonicalizationError(
            "theme gold decisions must cover every manifest term exactly in order"
        )


def _validate_report_binding(
    manifest: ValidatedThemeCandidateManifest,
    report: ThemeCanonicalizationGoldReport,
) -> None:
    if (
        report.manifest_id != manifest.manifest_id
        or report.manifest_content_hash != manifest.manifest_content_hash
        or report.sample_id != manifest.sample_id
        or report.sample_content_hash != manifest.sample_content_hash
    ):
        raise ThemeCanonicalizationError(
            "theme gold report must bind exact validated manifest and sample"
        )
    expected_term_ids = tuple(term.term_id for term in manifest.terms)
    actual_term_ids = tuple(decision.term_id for decision in report.decisions)
    if actual_term_ids != expected_term_ids:
        raise ThemeCanonicalizationError(
            "theme gold report decisions must cover every manifest term exactly in order"
        )


def _validate_analysis_batches(
    sample: TaxonomyDiversitySampleReport,
    manifest: ThemeCandidateManifest,
    gold_set: ThemeCanonicalizationGoldReport,
    annotation_batches: tuple[ThemeCanonicalizationBatch, ...],
) -> tuple[ValidatedThemeCanonicalizationBatch, ...]:
    validated = tuple(
        validate_theme_canonicalization_batch(sample, manifest, batch)
        for batch in annotation_batches
    )
    if len(validated) < 2:
        raise ThemeCanonicalizationError(
            "theme canonicalization analysis requires at least two source batches"
        )
    _validate_validated_batch_uniqueness(validated)
    actual_refs = tuple(
        (batch.batch_id, batch.annotator_id, batch.annotation_batch_hash)
        for batch in validated
    )
    expected_refs = tuple(
        (batch.batch_id, batch.annotator_id, batch.annotation_batch_hash)
        for batch in gold_set.source_batches
    )
    if actual_refs != expected_refs:
        raise ThemeCanonicalizationError(
            "theme analysis source batches must exactly match gold-set source refs in order"
        )
    return validated


def _validate_validated_batch_uniqueness(
    batches: tuple[ValidatedThemeCanonicalizationBatch, ...],
) -> None:
    batch_ids = tuple(batch.batch_id for batch in batches)
    annotator_ids = tuple(batch.annotator_id for batch in batches)
    hashes = tuple(batch.annotation_batch_hash for batch in batches)
    if len(batch_ids) != len(set(batch_ids)):
        raise ThemeCanonicalizationError("theme annotation batch IDs must be unique")
    if len(annotator_ids) != len(set(annotator_ids)):
        raise ThemeCanonicalizationError("theme annotations require unique annotator identities")
    if len(hashes) != len(set(hashes)):
        raise ThemeCanonicalizationError("theme annotation batch hashes must be unique")


def _validate_source_batch_uniqueness(
    batches: tuple[ThemeCanonicalizationSourceBatch, ...],
) -> None:
    batch_ids = tuple(batch.batch_id for batch in batches)
    annotator_ids = tuple(batch.annotator_id for batch in batches)
    hashes = tuple(batch.annotation_batch_hash for batch in batches)
    if len(batch_ids) != len(set(batch_ids)):
        raise ValueError("theme source batch IDs must be unique")
    if len(annotator_ids) != len(set(annotator_ids)):
        raise ValueError("theme source annotators must be unique")
    if len(hashes) != len(set(hashes)):
        raise ValueError("theme source hashes must be unique")


def _decision_outcome(
    decision: ThemeCanonicalizationDecision,
) -> tuple[ThemeCanonicalizationResolution, str | None]:
    return decision.resolution, decision.canonical_theme_key


def _outcome_token(decision: ThemeCanonicalizationDecision) -> str:
    if decision.resolution is ThemeCanonicalizationResolution.CANONICAL:
        if decision.canonical_theme_key is None:
            raise AssertionError("validated canonical decision is missing theme key")
        return f"theme:{decision.canonical_theme_key}"
    return decision.resolution.value


def _build_confusion_pairs(
    counts: Counter[tuple[str, str]],
    term_ids: dict[tuple[str, str], list[str]],
    total_comparisons: int,
) -> tuple[ThemeCanonicalizationConfusionPair, ...]:
    ordered = sorted(counts, key=lambda pair: (-counts[pair], pair[0], pair[1]))
    return tuple(
        ThemeCanonicalizationConfusionPair(
            outcome_a=pair[0],
            outcome_b=pair[1],
            comparison_count=counts[pair],
            comparison_rate=counts[pair] / total_comparisons,
            term_ids=tuple(term_ids[pair]),
        )
        for pair in ordered
    )


def _build_theme_metrics(
    gold_set: ThemeCanonicalizationGoldReport,
    batches: tuple[ValidatedThemeCanonicalizationBatch, ...],
) -> tuple[ThemeCanonicalKeyMetric, ...]:
    keys = sorted(
        {
            decision.canonical_theme_key
            for decision in (*gold_set.decisions, *(d for batch in batches for d in batch.decisions))
            if decision.resolution is ThemeCanonicalizationResolution.CANONICAL
            and decision.canonical_theme_key is not None
        }
    )
    metrics: list[ThemeCanonicalKeyMetric] = []
    for key in keys:
        gold_support = sum(
            decision.resolution is ThemeCanonicalizationResolution.CANONICAL
            and decision.canonical_theme_key == key
            for decision in gold_set.decisions
        )
        true_positive = 0
        false_positive = 0
        false_negative = 0
        for batch in batches:
            for gold_decision, annotation_decision in zip(
                gold_set.decisions,
                batch.decisions,
                strict=True,
            ):
                gold_matches = (
                    gold_decision.resolution is ThemeCanonicalizationResolution.CANONICAL
                    and gold_decision.canonical_theme_key == key
                )
                annotation_matches = (
                    annotation_decision.resolution is ThemeCanonicalizationResolution.CANONICAL
                    and annotation_decision.canonical_theme_key == key
                )
                if gold_matches and annotation_matches:
                    true_positive += 1
                elif annotation_matches:
                    false_positive += 1
                elif gold_matches:
                    false_negative += 1
        assignments = true_positive + false_positive
        metrics.append(
            ThemeCanonicalKeyMetric(
                canonical_theme_key=key,
                gold_support_count=gold_support,
                annotation_assignment_count=assignments,
                gold_alignment_true_positive_count=true_positive,
                gold_alignment_false_positive_count=false_positive,
                gold_alignment_false_negative_count=false_negative,
                gold_alignment_precision=_optional_rate(true_positive, assignments),
                gold_alignment_recall=_optional_rate(
                    true_positive,
                    true_positive + false_negative,
                ),
            )
        )
    return tuple(metrics)


def _manifest_payload(manifest: ThemeCandidateManifest) -> dict[str, object]:
    return {
        "spec_version": manifest.spec_version,
        "contract_version": manifest.contract_version,
        "contract_content_hash": THEME_CANONICALIZATION_CONTRACT_V1_CONTENT_HASH,
        "manifest_id": manifest.manifest_id,
        "sample_id": manifest.sample_id,
        "sample_content_hash": manifest.sample_content_hash,
        "created_at": manifest.created_at.isoformat(),
        "reviewed_listing_ids": list(manifest.reviewed_listing_ids),
        "terms": [term.model_dump(mode="json") for term in manifest.terms],
    }


def _annotation_payload(batch: ThemeCanonicalizationBatch) -> dict[str, object]:
    return {
        "spec_version": batch.spec_version,
        "contract_version": batch.contract_version,
        "contract_content_hash": THEME_CANONICALIZATION_CONTRACT_V1_CONTENT_HASH,
        "batch_id": batch.batch_id,
        "annotator_id": batch.annotator_id,
        "manifest_id": batch.manifest_id,
        "manifest_content_hash": batch.manifest_content_hash,
        "sample_id": batch.sample_id,
        "sample_content_hash": batch.sample_content_hash,
        "created_at": batch.created_at.isoformat(),
        "decisions": [decision.model_dump(mode="json") for decision in batch.decisions],
    }


def _gold_payload(
    declaration: ThemeCanonicalizationGoldDeclaration,
    source_batches: tuple[ThemeCanonicalizationSourceBatch, ...],
) -> dict[str, object]:
    return {
        "spec_version": declaration.spec_version,
        "contract_version": declaration.contract_version,
        "contract_content_hash": THEME_CANONICALIZATION_CONTRACT_V1_CONTENT_HASH,
        "gold_set_id": declaration.gold_set_id,
        "manifest_id": declaration.manifest_id,
        "manifest_content_hash": declaration.manifest_content_hash,
        "sample_id": declaration.sample_id,
        "sample_content_hash": declaration.sample_content_hash,
        "adjudicator_id": declaration.adjudicator_id,
        "adjudicated_at": declaration.adjudicated_at.isoformat(),
        "source_batches": [batch.model_dump(mode="json") for batch in source_batches],
        "decisions": [decision.model_dump(mode="json") for decision in declaration.decisions],
    }


def _gold_report_payload(report: ThemeCanonicalizationGoldReport) -> dict[str, object]:
    return {
        "spec_version": report.spec_version,
        "contract_version": report.contract_version,
        "contract_content_hash": report.contract_content_hash,
        "gold_set_id": report.gold_set_id,
        "manifest_id": report.manifest_id,
        "manifest_content_hash": report.manifest_content_hash,
        "sample_id": report.sample_id,
        "sample_content_hash": report.sample_content_hash,
        "adjudicator_id": report.adjudicator_id,
        "adjudicated_at": report.adjudicated_at.isoformat(),
        "source_batches": [batch.model_dump(mode="json") for batch in report.source_batches],
        "decisions": [decision.model_dump(mode="json") for decision in report.decisions],
    }


def _report_payload(
    *,
    manifest: ValidatedThemeCandidateManifest,
    gold_set: ThemeCanonicalizationGoldReport,
    source_batches: tuple[ThemeCanonicalizationSourceBatch, ...],
    pairwise_comparison_count: int,
    pairwise_agreement_count: int,
    pairwise_disagreement_count: int,
    canonical_count: int,
    unknown_count: int,
    not_theme_count: int,
    gold_alignment_count: int,
    disagreement_term_ids: tuple[str, ...],
    confusion_pairs: tuple[ThemeCanonicalizationConfusionPair, ...],
    theme_metrics: tuple[ThemeCanonicalKeyMetric, ...],
    canonical_gold_keys: tuple[str, ...],
) -> dict[str, object]:
    source_batch_count = len(source_batches)
    term_count = len(manifest.terms)
    total_assignments = source_batch_count * term_count
    agreement_rate = pairwise_agreement_count / pairwise_comparison_count
    unanimous_count = term_count - len(disagreement_term_ids)
    return {
        "spec_version": THEME_CANONICALIZATION_SPEC_VERSION,
        "contract_version": THEME_CANONICALIZATION_CONTRACT_VERSION,
        "contract_content_hash": THEME_CANONICALIZATION_CONTRACT_V1_CONTENT_HASH,
        "manifest_id": manifest.manifest_id,
        "manifest_content_hash": manifest.manifest_content_hash,
        "sample_id": manifest.sample_id,
        "sample_content_hash": manifest.sample_content_hash,
        "gold_set_id": gold_set.gold_set_id,
        "gold_set_content_hash": gold_set.gold_set_content_hash,
        "source_batches": [batch.model_dump(mode="json") for batch in source_batches],
        "total_candidate_terms": term_count,
        "source_batch_count": source_batch_count,
        "pairwise_comparison_count": pairwise_comparison_count,
        "pairwise_agreement_count": pairwise_agreement_count,
        "pairwise_disagreement_count": pairwise_disagreement_count,
        "pairwise_agreement_rate": agreement_rate,
        "initial_theme_canonicalization_target": THEME_CANONICALIZATION_TARGET,
        "meets_initial_theme_canonicalization_target": (
            agreement_rate >= THEME_CANONICALIZATION_TARGET
        ),
        "unanimous_term_count": unanimous_count,
        "unanimous_term_rate": unanimous_count / term_count,
        "canonical_assignment_count": canonical_count,
        "canonical_assignment_rate": canonical_count / total_assignments,
        "unknown_assignment_count": unknown_count,
        "unknown_assignment_rate": unknown_count / total_assignments,
        "not_theme_assignment_count": not_theme_count,
        "not_theme_assignment_rate": not_theme_count / total_assignments,
        "gold_alignment_count": gold_alignment_count,
        "gold_alignment_rate": gold_alignment_count / total_assignments,
        "disagreement_term_ids": list(disagreement_term_ids),
        "confusion_pairs": [pair.model_dump(mode="json") for pair in confusion_pairs],
        "theme_metrics": [metric.model_dump(mode="json") for metric in theme_metrics],
        "canonical_gold_theme_keys": list(canonical_gold_keys),
    }


def _trimmed_identifier(value: str, field_name: str) -> str:
    if not value or value != value.strip():
        raise ValueError(f"{field_name} must be nonblank and trimmed")
    return value


def _utc_datetime(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _validate_rate(count: int, rate: float, total: int, label: str) -> None:
    if count > total:
        raise ValueError(f"theme {label} assignment count exceeds total")
    if rate != count / total:
        raise ValueError(f"theme {label} assignment rate is inconsistent")


def _optional_rate(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def _validate_sha256(value: str, field_name: str) -> None:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{field_name} must be 64 lowercase hexadecimal characters")


def _content_hash(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


_validate_contract()
