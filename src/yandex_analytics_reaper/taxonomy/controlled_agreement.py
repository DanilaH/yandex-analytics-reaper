from __future__ import annotations

import hashlib
import json
from itertools import combinations
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .gold_set import (
    ANNOTATION_CONTRACT_V1_CONTENT_HASH,
    ANNOTATION_SPEC_VERSION,
    GOLD_SET_SPEC_VERSION,
    LABEL_REGISTRY_VERSION,
    TaxonomyAnnotationBatch,
    TaxonomyGoldSetReport,
    TaxonomyManualLabel,
    ValidatedTaxonomyAnnotationBatch,
    validate_taxonomy_annotation_batch,
    validate_taxonomy_gold_set_report,
)
from .registries import (
    TAXONOMY_LABEL_REGISTRY_V1_CONTENT_HASH,
    ControlledLabelDimension,
    get_taxonomy_label_registry,
)
from .sampling import (
    SPEC_VERSION as TAXONOMY_DIVERSITY_SAMPLE_SPEC_VERSION,
)
from .sampling import TaxonomyDiversitySampleReport

CONTROLLED_DIMENSION_AGREEMENT_SPEC_VERSION: Literal[
    "taxonomy-controlled-dimension-agreement-v1"
] = "taxonomy-controlled-dimension-agreement-v1"
CONTROLLED_DIMENSION_AGREEMENT_CONTRACT_VERSION: Literal[
    "controlled-dimension-agreement-v1"
] = "controlled-dimension-agreement-v1"
CONTROLLED_DIMENSION_AGREEMENT_CONTRACT_V1_CONTENT_HASH = (
    "9bebd5221d664ace6b6c046384bed76bbd37153908b4852317cfa74a4832798b"
)
CONTROLLED_DIMENSION_AGREEMENT_TARGET = 0.90
_CONTROLLED_DIMENSIONS = tuple(ControlledLabelDimension)
_AGREEMENT_RULES = (
    "sample_and_gold_set_revalidated_before_analysis",
    "at_least_two_source_annotation_batches_with_unique_annotator_ids_required",
    "source_batch_ids_annotators_and_hashes_must_match_gold_set_source_refs_in_order",
    "multi_label_order_is_semantically_irrelevant_and_canonicalized_to_registry_order",
    "pairwise_dimension_agreement_requires_exact_canonical_label_set_match",
    "pairwise_comparison_count_is_choose_annotators_2_times_sample_size",
    "unanimous_listing_requires_all_source_annotators_to_have_exact_same_label_set",
    "disagreement_listing_ids_follow_sample_order",
    "each_controlled_dimension_target_is_0_90_exact_set_pairwise_agreement",
    "all_dimensions_target_requires_every_controlled_dimension_to_meet_target",
    "gold_alignment_precision_recall_are_adjudication_alignment_not_classifier_performance",
    "zero_denominator_gold_alignment_metrics_are_none_not_zero",
    "unsupported_gold_labels_do_not_receive_fake_recall",
    "purposive_sample_metrics_do_not_estimate_population_prevalence",
    "theme_canonicalization_is_out_of_scope_for_this_contract",
)


class ControlledDimensionAgreementError(ValueError):
    """Controlled-dimension annotation evidence violates the frozen agreement protocol."""


class ControlledDimensionAgreementSourceBatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    batch_id: str
    annotator_id: str
    annotation_batch_hash: str

    @field_validator("batch_id", "annotator_id")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        if not value or value != value.strip():
            raise ValueError(
                "controlled-agreement source identifiers must be nonblank and trimmed"
            )
        return value

    @field_validator("annotation_batch_hash")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        _validate_sha256(value, "annotation_batch_hash")
        return value


class ControlledLabelGoldAlignment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    label: str
    gold_support_count: int = Field(ge=0)
    annotation_assignment_count: int = Field(ge=0)
    gold_alignment_true_positive_count: int = Field(ge=0)
    gold_alignment_false_positive_count: int = Field(ge=0)
    gold_alignment_false_negative_count: int = Field(ge=0)
    gold_alignment_precision: float | None = Field(default=None, ge=0.0, le=1.0)
    gold_alignment_recall: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator("label")
    @classmethod
    def validate_label(cls, value: str) -> str:
        if not value or value != value.strip():
            raise ValueError("controlled-agreement labels must be nonblank and trimmed")
        return value

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        if (
            self.gold_alignment_true_positive_count
            + self.gold_alignment_false_positive_count
            != self.annotation_assignment_count
        ):
            raise ValueError(
                "controlled label assignments must equal gold-alignment true + false positives"
            )
        precision_denominator = (
            self.gold_alignment_true_positive_count
            + self.gold_alignment_false_positive_count
        )
        recall_denominator = (
            self.gold_alignment_true_positive_count
            + self.gold_alignment_false_negative_count
        )
        if self.gold_alignment_precision != _optional_rate(
            self.gold_alignment_true_positive_count,
            precision_denominator,
        ):
            raise ValueError("controlled label gold-alignment precision is inconsistent")
        if self.gold_alignment_recall != _optional_rate(
            self.gold_alignment_true_positive_count,
            recall_denominator,
        ):
            raise ValueError("controlled label gold-alignment recall is inconsistent")
        return self


class ControlledDimensionAgreementEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    dimension: ControlledLabelDimension
    registry_labels: tuple[str, ...] = Field(min_length=1)
    pairwise_comparison_count: int = Field(ge=1)
    pairwise_exact_match_count: int = Field(ge=0)
    pairwise_exact_mismatch_count: int = Field(ge=0)
    pairwise_exact_match_rate: float = Field(ge=0.0, le=1.0)
    initial_agreement_target: float = Field(ge=0.0, le=1.0)
    meets_initial_agreement_target: bool
    unanimous_listing_count: int = Field(ge=0)
    unanimous_listing_rate: float = Field(ge=0.0, le=1.0)
    disagreement_listing_ids: tuple[str, ...]
    label_metrics: tuple[ControlledLabelGoldAlignment, ...] = Field(min_length=1)

    @field_validator("disagreement_listing_ids")
    @classmethod
    def validate_disagreement_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if any(not value for value in normalized):
            raise ValueError("controlled-dimension disagreement listing IDs cannot be blank")
        if len(normalized) != len(set(normalized)):
            raise ValueError("controlled-dimension disagreement listing IDs must be unique")
        return normalized

    @model_validator(mode="after")
    def validate_entry(self) -> Self:
        registry = get_taxonomy_label_registry(LABEL_REGISTRY_VERSION).registry_for(
            self.dimension
        )
        if self.registry_labels != registry.labels:
            raise ValueError(
                "controlled-dimension registry labels do not match frozen registry"
            )
        if tuple(metric.label for metric in self.label_metrics) != self.registry_labels:
            raise ValueError(
                "controlled label metrics must follow exact registry-label order"
            )
        if (
            self.pairwise_exact_match_count + self.pairwise_exact_mismatch_count
            != self.pairwise_comparison_count
        ):
            raise ValueError(
                "controlled-dimension pairwise counts must cover every comparison"
            )
        if self.pairwise_exact_match_rate != (
            self.pairwise_exact_match_count / self.pairwise_comparison_count
        ):
            raise ValueError(
                "controlled-dimension agreement rate is inconsistent with counts"
            )
        if self.initial_agreement_target != CONTROLLED_DIMENSION_AGREEMENT_TARGET:
            raise ValueError("controlled-dimension agreement target does not match v1")
        if self.meets_initial_agreement_target != (
            self.pairwise_exact_match_rate >= CONTROLLED_DIMENSION_AGREEMENT_TARGET
        ):
            raise ValueError(
                "controlled-dimension target result is inconsistent with rate"
            )
        return self


class ControlledDimensionAgreementReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: Literal["taxonomy-controlled-dimension-agreement-v1"] = (
        CONTROLLED_DIMENSION_AGREEMENT_SPEC_VERSION
    )
    agreement_contract_version: Literal["controlled-dimension-agreement-v1"] = (
        CONTROLLED_DIMENSION_AGREEMENT_CONTRACT_VERSION
    )
    agreement_contract_content_hash: str = (
        CONTROLLED_DIMENSION_AGREEMENT_CONTRACT_V1_CONTENT_HASH
    )
    annotation_contract_content_hash: str = ANNOTATION_CONTRACT_V1_CONTENT_HASH
    label_registry_content_hash: str = TAXONOMY_LABEL_REGISTRY_V1_CONTENT_HASH
    sample_id: str
    sample_content_hash: str
    gold_set_id: str
    gold_set_content_hash: str
    source_batches: tuple[ControlledDimensionAgreementSourceBatch, ...] = Field(min_length=2)
    total_labels: int = Field(ge=100, le=200)
    source_batch_count: int = Field(ge=2)
    dimensions: tuple[ControlledDimensionAgreementEntry, ...] = Field(
        min_length=4,
        max_length=4,
    )
    all_dimensions_meet_initial_agreement_target: bool
    agreement_content_hash: str

    @field_validator("sample_id", "gold_set_id")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        if not value or value != value.strip():
            raise ValueError("controlled-agreement report IDs must be nonblank and trimmed")
        return value

    @field_validator(
        "agreement_contract_content_hash",
        "annotation_contract_content_hash",
        "label_registry_content_hash",
        "sample_content_hash",
        "gold_set_content_hash",
        "agreement_content_hash",
    )
    @classmethod
    def validate_hash(cls, value: str) -> str:
        _validate_sha256(value, "controlled-agreement report hash")
        return value

    @model_validator(mode="after")
    def validate_report(self) -> Self:
        if (
            self.agreement_contract_content_hash
            != CONTROLLED_DIMENSION_AGREEMENT_CONTRACT_V1_CONTENT_HASH
        ):
            raise ValueError(
                "controlled-agreement contract content hash does not match v1"
            )
        if self.annotation_contract_content_hash != ANNOTATION_CONTRACT_V1_CONTENT_HASH:
            raise ValueError(
                "controlled-agreement annotation contract hash does not match v1"
            )
        if self.label_registry_content_hash != TAXONOMY_LABEL_REGISTRY_V1_CONTENT_HASH:
            raise ValueError(
                "controlled-agreement label-registry hash does not match v1"
            )
        if self.source_batch_count != len(self.source_batches):
            raise ValueError(
                "controlled-agreement source_batch_count must match source refs"
            )
        _validate_source_batch_uniqueness(self.source_batches)
        if tuple(entry.dimension for entry in self.dimensions) != _CONTROLLED_DIMENSIONS:
            raise ValueError("controlled-agreement dimensions must follow registry order")
        pair_count = self.source_batch_count * (self.source_batch_count - 1) // 2
        expected_comparisons = pair_count * self.total_labels
        total_assignments = self.total_labels * self.source_batch_count
        for entry in self.dimensions:
            if entry.pairwise_comparison_count != expected_comparisons:
                raise ValueError(
                    "controlled-dimension comparison count is inconsistent"
                )
            if entry.unanimous_listing_count > self.total_labels:
                raise ValueError(
                    "controlled-dimension unanimous count exceeds total labels"
                )
            if entry.unanimous_listing_rate != (
                entry.unanimous_listing_count / self.total_labels
            ):
                raise ValueError(
                    "controlled-dimension unanimous rate is inconsistent with count"
                )
            if len(entry.disagreement_listing_ids) != (
                self.total_labels - entry.unanimous_listing_count
            ):
                raise ValueError(
                    "controlled-dimension disagreement IDs must cover every non-unanimous listing"
                )
            for metric in entry.label_metrics:
                if metric.gold_support_count > self.total_labels:
                    raise ValueError("controlled label gold support exceeds total labels")
                if metric.annotation_assignment_count > total_assignments:
                    raise ValueError(
                        "controlled label assignment count exceeds total assignments"
                    )
                expected_gold_comparisons = (
                    metric.gold_support_count * self.source_batch_count
                )
                if (
                    metric.gold_alignment_true_positive_count
                    + metric.gold_alignment_false_negative_count
                    != expected_gold_comparisons
                ):
                    raise ValueError(
                        "controlled label gold-alignment recall support is inconsistent"
                    )
        expected_all = all(
            entry.meets_initial_agreement_target for entry in self.dimensions
        )
        if self.all_dimensions_meet_initial_agreement_target != expected_all:
            raise ValueError(
                "controlled-agreement aggregate target result is inconsistent"
            )
        return self


def build_controlled_dimension_agreement_report(
    sample: TaxonomyDiversitySampleReport,
    gold_set: TaxonomyGoldSetReport,
    annotation_batches: tuple[TaxonomyAnnotationBatch, ...],
) -> ControlledDimensionAgreementReport:
    """Analyze exact-set agreement for the four frozen controlled multi-label dimensions."""

    sample = TaxonomyDiversitySampleReport.model_validate(sample.model_dump(mode="python"))
    gold_set = TaxonomyGoldSetReport.model_validate(gold_set.model_dump(mode="python"))
    annotation_batches = tuple(
        TaxonomyAnnotationBatch.model_validate(batch.model_dump(mode="python"))
        for batch in annotation_batches
    )
    _validate_contract()
    gold_set = validate_taxonomy_gold_set_report(sample, gold_set)
    validated = _validate_source_batches(sample, gold_set, annotation_batches)

    dimensions = tuple(
        _build_dimension_entry(dimension, sample, gold_set, validated)
        for dimension in _CONTROLLED_DIMENSIONS
    )
    source_batches = tuple(
        ControlledDimensionAgreementSourceBatch(
            batch_id=batch.batch_id,
            annotator_id=batch.annotator_id,
            annotation_batch_hash=batch.annotation_batch_hash,
        )
        for batch in validated
    )
    payload = _report_payload(
        sample=sample,
        gold_set=gold_set,
        source_batches=source_batches,
        dimensions=dimensions,
    )
    content_hash = _content_hash(payload)
    return ControlledDimensionAgreementReport(
        sample_id=sample.sample_id,
        sample_content_hash=sample.sample_content_hash,
        gold_set_id=gold_set.gold_set_id,
        gold_set_content_hash=gold_set.gold_set_content_hash,
        source_batches=source_batches,
        total_labels=len(gold_set.labels),
        source_batch_count=len(validated),
        dimensions=dimensions,
        all_dimensions_meet_initial_agreement_target=all(
            entry.meets_initial_agreement_target for entry in dimensions
        ),
        agreement_content_hash=content_hash,
    )


def validate_controlled_dimension_agreement_report(
    sample: TaxonomyDiversitySampleReport,
    gold_set: TaxonomyGoldSetReport,
    annotation_batches: tuple[TaxonomyAnnotationBatch, ...],
    report: ControlledDimensionAgreementReport,
) -> ControlledDimensionAgreementReport:
    """Rebuild and compare one persisted controlled-dimension agreement artifact."""

    report = ControlledDimensionAgreementReport.model_validate(
        report.model_dump(mode="python")
    )
    expected = build_controlled_dimension_agreement_report(
        sample,
        gold_set,
        annotation_batches,
    )
    if report != expected:
        raise ControlledDimensionAgreementError(
            "persisted controlled-dimension agreement report does not match rebuilt content"
        )
    return report


def controlled_dimension_agreement_contract_content_hash() -> str:
    payload = {
        "spec_version": CONTROLLED_DIMENSION_AGREEMENT_SPEC_VERSION,
        "agreement_contract_version": CONTROLLED_DIMENSION_AGREEMENT_CONTRACT_VERSION,
        "sample_spec_version": TAXONOMY_DIVERSITY_SAMPLE_SPEC_VERSION,
        "gold_set_spec_version": GOLD_SET_SPEC_VERSION,
        "annotation_spec_version": ANNOTATION_SPEC_VERSION,
        "annotation_contract_content_hash": ANNOTATION_CONTRACT_V1_CONTENT_HASH,
        "label_registry_version": LABEL_REGISTRY_VERSION,
        "label_registry_content_hash": TAXONOMY_LABEL_REGISTRY_V1_CONTENT_HASH,
        "controlled_dimensions": [item.value for item in _CONTROLLED_DIMENSIONS],
        "initial_controlled_dimension_agreement_target": (
            CONTROLLED_DIMENSION_AGREEMENT_TARGET
        ),
        "source_batch_fields": list(ControlledDimensionAgreementSourceBatch.model_fields),
        "label_metric_fields": list(ControlledLabelGoldAlignment.model_fields),
        "dimension_entry_fields": list(ControlledDimensionAgreementEntry.model_fields),
        "report_fields": list(ControlledDimensionAgreementReport.model_fields),
        "rules": list(_AGREEMENT_RULES),
        "pairwise_agreement_formula": (
            "exact_canonical_label_set_matches/all_annotator_pair_comparisons"
        ),
        "dimension_order": "controlled-label-dimension-enum-order",
        "label_order": "frozen-registry-order",
        "content_hash_canonicalization": (
            "json-sort-keys-compact-utf8-ensure-ascii-false"
        ),
    }
    return _content_hash(payload)


def _validate_contract() -> None:
    if (
        controlled_dimension_agreement_contract_content_hash()
        != CONTROLLED_DIMENSION_AGREEMENT_CONTRACT_V1_CONTENT_HASH
    ):
        raise ControlledDimensionAgreementError(
            "controlled-dimension agreement contract changed without a new version"
        )


def _validate_source_batches(
    sample: TaxonomyDiversitySampleReport,
    gold_set: TaxonomyGoldSetReport,
    annotation_batches: tuple[TaxonomyAnnotationBatch, ...],
) -> tuple[ValidatedTaxonomyAnnotationBatch, ...]:
    if len(annotation_batches) < 2:
        raise ControlledDimensionAgreementError(
            "controlled-dimension agreement requires at least two independent annotation batches"
        )
    validated = tuple(
        validate_taxonomy_annotation_batch(sample, batch) for batch in annotation_batches
    )
    batch_ids = tuple(batch.batch_id for batch in validated)
    annotator_ids = tuple(batch.annotator_id for batch in validated)
    if len(batch_ids) != len(set(batch_ids)):
        raise ControlledDimensionAgreementError(
            "controlled-agreement source batch IDs must be unique"
        )
    if len(annotator_ids) != len(set(annotator_ids)):
        raise ControlledDimensionAgreementError(
            "controlled-agreement source batches require unique annotator identities"
        )
    actual_refs = tuple(
        (batch.batch_id, batch.annotator_id, batch.annotation_batch_hash)
        for batch in validated
    )
    expected_refs = tuple(
        (batch.batch_id, batch.annotator_id, batch.annotation_batch_hash)
        for batch in gold_set.source_batches
    )
    if actual_refs != expected_refs:
        raise ControlledDimensionAgreementError(
            "source batches must exactly match gold-set source refs in order"
        )
    return validated


def _build_dimension_entry(
    dimension: ControlledLabelDimension,
    sample: TaxonomyDiversitySampleReport,
    gold_set: TaxonomyGoldSetReport,
    validated: tuple[ValidatedTaxonomyAnnotationBatch, ...],
) -> ControlledDimensionAgreementEntry:
    registry_labels = get_taxonomy_label_registry(LABEL_REGISTRY_VERSION).registry_for(
        dimension
    ).labels
    source_batch_count = len(validated)
    pair_count = source_batch_count * (source_batch_count - 1) // 2
    pairwise_comparison_count = pair_count * len(sample.selected)
    pairwise_exact_match_count = 0
    disagreement_listing_ids: list[str] = []

    for label_index, sample_member in enumerate(sample.selected):
        assignments = tuple(
            _canonical_dimension_values(
                batch.labels[label_index],
                dimension,
                registry_labels,
            )
            for batch in validated
        )
        if len(set(assignments)) == 1:
            pairwise_exact_match_count += pair_count
            continue
        disagreement_listing_ids.append(sample_member.platform_listing_id)
        pairwise_exact_match_count += sum(
            assignments[left_index] == assignments[right_index]
            for left_index, right_index in combinations(range(source_batch_count), 2)
        )

    pairwise_exact_mismatch_count = (
        pairwise_comparison_count - pairwise_exact_match_count
    )
    unanimous_listing_count = len(sample.selected) - len(disagreement_listing_ids)
    label_metrics = tuple(
        _build_label_metric(label, dimension, gold_set, validated)
        for label in registry_labels
    )
    rate = pairwise_exact_match_count / pairwise_comparison_count
    return ControlledDimensionAgreementEntry(
        dimension=dimension,
        registry_labels=registry_labels,
        pairwise_comparison_count=pairwise_comparison_count,
        pairwise_exact_match_count=pairwise_exact_match_count,
        pairwise_exact_mismatch_count=pairwise_exact_mismatch_count,
        pairwise_exact_match_rate=rate,
        initial_agreement_target=CONTROLLED_DIMENSION_AGREEMENT_TARGET,
        meets_initial_agreement_target=rate >= CONTROLLED_DIMENSION_AGREEMENT_TARGET,
        unanimous_listing_count=unanimous_listing_count,
        unanimous_listing_rate=unanimous_listing_count / len(sample.selected),
        disagreement_listing_ids=tuple(disagreement_listing_ids),
        label_metrics=label_metrics,
    )


def _build_label_metric(
    label: str,
    dimension: ControlledLabelDimension,
    gold_set: TaxonomyGoldSetReport,
    validated: tuple[ValidatedTaxonomyAnnotationBatch, ...],
) -> ControlledLabelGoldAlignment:
    gold_support_count = sum(
        label in _dimension_values(gold_label, dimension)
        for gold_label in gold_set.labels
    )
    true_positive_count = 0
    false_positive_count = 0
    false_negative_count = 0
    for batch in validated:
        for gold_label, annotation_label in zip(
            gold_set.labels,
            batch.labels,
            strict=True,
        ):
            gold_matches = label in _dimension_values(gold_label, dimension)
            annotation_matches = label in _dimension_values(
                annotation_label,
                dimension,
            )
            if gold_matches and annotation_matches:
                true_positive_count += 1
            elif annotation_matches:
                false_positive_count += 1
            elif gold_matches:
                false_negative_count += 1
    assignment_count = true_positive_count + false_positive_count
    return ControlledLabelGoldAlignment(
        label=label,
        gold_support_count=gold_support_count,
        annotation_assignment_count=assignment_count,
        gold_alignment_true_positive_count=true_positive_count,
        gold_alignment_false_positive_count=false_positive_count,
        gold_alignment_false_negative_count=false_negative_count,
        gold_alignment_precision=_optional_rate(true_positive_count, assignment_count),
        gold_alignment_recall=_optional_rate(
            true_positive_count,
            true_positive_count + false_negative_count,
        ),
    )


def _canonical_dimension_values(
    label: TaxonomyManualLabel,
    dimension: ControlledLabelDimension,
    registry_labels: tuple[str, ...],
) -> tuple[str, ...]:
    values = set(_dimension_values(label, dimension))
    return tuple(
        registry_label for registry_label in registry_labels if registry_label in values
    )


def _dimension_values(
    label: TaxonomyManualLabel,
    dimension: ControlledLabelDimension,
) -> tuple[str, ...]:
    if dimension is ControlledLabelDimension.MECHANICS:
        return label.mechanics
    if dimension is ControlledLabelDimension.OBJECTIVES:
        return label.objectives
    if dimension is ControlledLabelDimension.META_SYSTEMS:
        return label.meta_systems
    if dimension is ControlledLabelDimension.TONES:
        return label.tones
    raise AssertionError(f"unsupported controlled dimension: {dimension.value}")


def _report_payload(
    *,
    sample: TaxonomyDiversitySampleReport,
    gold_set: TaxonomyGoldSetReport,
    source_batches: tuple[ControlledDimensionAgreementSourceBatch, ...],
    dimensions: tuple[ControlledDimensionAgreementEntry, ...],
) -> dict[str, object]:
    return {
        "spec_version": CONTROLLED_DIMENSION_AGREEMENT_SPEC_VERSION,
        "agreement_contract_version": CONTROLLED_DIMENSION_AGREEMENT_CONTRACT_VERSION,
        "agreement_contract_content_hash": (
            CONTROLLED_DIMENSION_AGREEMENT_CONTRACT_V1_CONTENT_HASH
        ),
        "annotation_contract_content_hash": ANNOTATION_CONTRACT_V1_CONTENT_HASH,
        "label_registry_content_hash": TAXONOMY_LABEL_REGISTRY_V1_CONTENT_HASH,
        "sample_id": sample.sample_id,
        "sample_content_hash": sample.sample_content_hash,
        "gold_set_id": gold_set.gold_set_id,
        "gold_set_content_hash": gold_set.gold_set_content_hash,
        "source_batches": [batch.model_dump(mode="json") for batch in source_batches],
        "total_labels": len(gold_set.labels),
        "source_batch_count": len(source_batches),
        "dimensions": [entry.model_dump(mode="json") for entry in dimensions],
        "all_dimensions_meet_initial_agreement_target": all(
            entry.meets_initial_agreement_target for entry in dimensions
        ),
    }


def _validate_source_batch_uniqueness(
    batches: tuple[ControlledDimensionAgreementSourceBatch, ...],
) -> None:
    batch_ids = tuple(batch.batch_id for batch in batches)
    annotator_ids = tuple(batch.annotator_id for batch in batches)
    hashes = tuple(batch.annotation_batch_hash for batch in batches)
    if len(batch_ids) != len(set(batch_ids)):
        raise ValueError("controlled-agreement source batch IDs must be unique")
    if len(annotator_ids) != len(set(annotator_ids)):
        raise ValueError("controlled-agreement source annotators must be unique")
    if len(hashes) != len(set(hashes)):
        raise ValueError("controlled-agreement source batch hashes must be unique")


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
