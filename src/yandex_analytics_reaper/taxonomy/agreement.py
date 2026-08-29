from __future__ import annotations

import hashlib
import json
from collections import Counter
from itertools import combinations
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .gold_set import (
    ANNOTATION_CONTRACT_V1_CONTENT_HASH,
    ANNOTATION_SPEC_VERSION,
    GOLD_SET_SPEC_VERSION,
    LABEL_REGISTRY_VERSION,
    TaxonomyAnnotationBatch,
    TaxonomyAnnotationConfidence,
    TaxonomyGoldSetReport,
    ValidatedTaxonomyAnnotationBatch,
    validate_taxonomy_annotation_batch,
    validate_taxonomy_gold_set_report,
)
from .models import PrimaryGameplayArchetype
from .registries import TAXONOMY_LABEL_REGISTRY_V1_CONTENT_HASH
from .sampling import (
    SPEC_VERSION as TAXONOMY_DIVERSITY_SAMPLE_SPEC_VERSION,
    TaxonomyDiversitySampleReport,
)

PRIMARY_ARCHETYPE_AGREEMENT_SPEC_VERSION: Literal[
    "taxonomy-primary-agreement-v1"
] = "taxonomy-primary-agreement-v1"
PRIMARY_ARCHETYPE_AGREEMENT_CONTRACT_VERSION: Literal[
    "primary-archetype-agreement-v1"
] = "primary-archetype-agreement-v1"
PRIMARY_ARCHETYPE_AGREEMENT_CONTRACT_V1_CONTENT_HASH = (
    "e09af2c913058837724d51fad30a0b29e95faf7dd2d00ce91a99ccb0506e368f"
)
PRIMARY_ARCHETYPE_AGREEMENT_TARGET = 0.90
_PRIMARY_ARCHETYPE_ORDER = {
    archetype: index for index, archetype in enumerate(PrimaryGameplayArchetype)
}
_AGREEMENT_RULES = (
    "sample_and_gold_set_revalidated_before_analysis",
    "at_least_two_source_annotation_batches_with_unique_annotator_ids_required",
    "source_batch_ids_annotators_and_hashes_must_match_gold_set_source_refs_in_order",
    "pairwise_agreement_uses_independent_primary_archetype_assignments_only",
    "confusion_pairs_are_unordered_disagreement_pairs_not_truth_directions",
    "confusion_pair_counts_use_all_annotator_pair_comparisons",
    "confusion_pair_rates_use_all_annotator_pair_comparisons",
    "confusion_pair_listing_ids_are_unique_evidence_anchors",
    "disagreement_listing_ids_follow_sample_order",
    "unanimous_listing_rate_requires_all_source_annotators_to_match",
    "low_confidence_unknown_and_other_rates_use_all_independent_assignments",
    "gold_alignment_precision_recall_are_adjudication_alignment_not_classifier_performance",
    "zero_denominator_gold_alignment_metrics_are_none_not_zero",
    "unsupported_gold_classes_do_not_receive_fake_recall",
    "initial_primary_agreement_target_is_0_90",
    "target_result_does_not_freeze_or_validate_taxonomy_by_itself",
    "purposive_sample_metrics_do_not_estimate_population_prevalence",
)


class PrimaryArchetypeAgreementError(ValueError):
    """Independent annotation evidence violates the frozen agreement protocol."""


class PrimaryArchetypeAgreementSourceBatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    batch_id: str
    annotator_id: str
    annotation_batch_hash: str

    @field_validator("batch_id", "annotator_id")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        if not value or value != value.strip():
            raise ValueError("agreement source identifiers must be nonblank and trimmed")
        return value

    @field_validator("annotation_batch_hash")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        _validate_sha256(value, "annotation_batch_hash")
        return value


class PrimaryArchetypeConfusionPair(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    archetype_a: PrimaryGameplayArchetype
    archetype_b: PrimaryGameplayArchetype
    comparison_count: int = Field(ge=1)
    comparison_rate: float = Field(gt=0.0, le=1.0)
    listing_ids: tuple[str, ...] = Field(min_length=1)

    @field_validator("listing_ids")
    @classmethod
    def validate_listing_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if any(not value for value in normalized):
            raise ValueError("confusion listing IDs cannot be blank")
        if len(normalized) != len(set(normalized)):
            raise ValueError("confusion listing IDs must be unique")
        return normalized

    @model_validator(mode="after")
    def validate_pair(self) -> Self:
        if self.archetype_a is self.archetype_b:
            raise ValueError("confusion pairs must contain two different archetypes")
        if _PRIMARY_ARCHETYPE_ORDER[self.archetype_a] >= _PRIMARY_ARCHETYPE_ORDER[
            self.archetype_b
        ]:
            raise ValueError("confusion pairs must follow primary-archetype registry order")
        if len(self.listing_ids) > self.comparison_count:
            raise ValueError("confusion evidence listings cannot exceed pairwise comparisons")
        return self


class PrimaryArchetypeClassAgreement(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    archetype: PrimaryGameplayArchetype
    gold_support_count: int = Field(ge=0)
    annotation_assignment_count: int = Field(ge=0)
    gold_alignment_true_positive_count: int = Field(ge=0)
    gold_alignment_false_positive_count: int = Field(ge=0)
    gold_alignment_false_negative_count: int = Field(ge=0)
    gold_alignment_precision: float | None = Field(default=None, ge=0.0, le=1.0)
    gold_alignment_recall: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        if (
            self.gold_alignment_true_positive_count
            + self.gold_alignment_false_positive_count
            != self.annotation_assignment_count
        ):
            raise ValueError(
                "class annotation assignments must equal gold-alignment true + false positives"
            )
        precision_denominator = (
            self.gold_alignment_true_positive_count + self.gold_alignment_false_positive_count
        )
        recall_denominator = (
            self.gold_alignment_true_positive_count + self.gold_alignment_false_negative_count
        )
        expected_precision = _optional_rate(
            self.gold_alignment_true_positive_count,
            precision_denominator,
        )
        expected_recall = _optional_rate(
            self.gold_alignment_true_positive_count,
            recall_denominator,
        )
        if self.gold_alignment_precision != expected_precision:
            raise ValueError("class gold-alignment precision is inconsistent with counts")
        if self.gold_alignment_recall != expected_recall:
            raise ValueError("class gold-alignment recall is inconsistent with counts")
        return self


class PrimaryArchetypeAgreementReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: Literal["taxonomy-primary-agreement-v1"] = (
        PRIMARY_ARCHETYPE_AGREEMENT_SPEC_VERSION
    )
    agreement_contract_version: Literal["primary-archetype-agreement-v1"] = (
        PRIMARY_ARCHETYPE_AGREEMENT_CONTRACT_VERSION
    )
    agreement_contract_content_hash: str = (
        PRIMARY_ARCHETYPE_AGREEMENT_CONTRACT_V1_CONTENT_HASH
    )
    annotation_contract_content_hash: str = ANNOTATION_CONTRACT_V1_CONTENT_HASH
    label_registry_content_hash: str = TAXONOMY_LABEL_REGISTRY_V1_CONTENT_HASH
    sample_id: str
    sample_content_hash: str
    gold_set_id: str
    gold_set_content_hash: str
    source_batches: tuple[PrimaryArchetypeAgreementSourceBatch, ...] = Field(min_length=2)
    total_labels: int = Field(ge=100, le=200)
    source_batch_count: int = Field(ge=2)
    pairwise_comparison_count: int = Field(ge=1)
    pairwise_agreement_count: int = Field(ge=0)
    pairwise_disagreement_count: int = Field(ge=0)
    pairwise_agreement_rate: float = Field(ge=0.0, le=1.0)
    initial_primary_agreement_target: float = Field(ge=0.0, le=1.0)
    meets_initial_primary_agreement_target: bool
    unanimous_listing_count: int = Field(ge=0)
    unanimous_listing_rate: float = Field(ge=0.0, le=1.0)
    low_confidence_assignment_count: int = Field(ge=0)
    low_confidence_assignment_rate: float = Field(ge=0.0, le=1.0)
    unknown_assignment_count: int = Field(ge=0)
    unknown_assignment_rate: float = Field(ge=0.0, le=1.0)
    other_assignment_count: int = Field(ge=0)
    other_assignment_rate: float = Field(ge=0.0, le=1.0)
    disagreement_listing_ids: tuple[str, ...]
    confusion_pairs: tuple[PrimaryArchetypeConfusionPair, ...]
    class_metrics: tuple[PrimaryArchetypeClassAgreement, ...] = Field(min_length=1)
    agreement_content_hash: str

    @field_validator("sample_id", "gold_set_id")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        if not value or value != value.strip():
            raise ValueError("agreement report IDs must be nonblank and trimmed")
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
        _validate_sha256(value, "agreement report hash")
        return value

    @field_validator("disagreement_listing_ids")
    @classmethod
    def validate_disagreement_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if any(not value for value in normalized):
            raise ValueError("agreement disagreement listing IDs cannot be blank")
        if len(normalized) != len(set(normalized)):
            raise ValueError("agreement disagreement listing IDs must be unique")
        return normalized

    @model_validator(mode="after")
    def validate_report_shape(self) -> Self:
        if (
            self.agreement_contract_content_hash
            != PRIMARY_ARCHETYPE_AGREEMENT_CONTRACT_V1_CONTENT_HASH
        ):
            raise ValueError("agreement report contract content hash does not match v1")
        if self.annotation_contract_content_hash != ANNOTATION_CONTRACT_V1_CONTENT_HASH:
            raise ValueError("agreement report annotation contract hash does not match v1")
        if self.label_registry_content_hash != TAXONOMY_LABEL_REGISTRY_V1_CONTENT_HASH:
            raise ValueError("agreement report label-registry hash does not match v1")
        if self.source_batch_count != len(self.source_batches):
            raise ValueError("agreement source_batch_count must match source batch refs")
        _validate_source_batch_uniqueness(self.source_batches)
        if tuple(metric.archetype for metric in self.class_metrics) != tuple(
            PrimaryGameplayArchetype
        ):
            raise ValueError("agreement class metrics must follow primary registry order")
        pair_count = self.source_batch_count * (self.source_batch_count - 1) // 2
        expected_comparisons = pair_count * self.total_labels
        if self.pairwise_comparison_count != expected_comparisons:
            raise ValueError("agreement pairwise comparison count is inconsistent")
        if (
            self.pairwise_agreement_count + self.pairwise_disagreement_count
            != self.pairwise_comparison_count
        ):
            raise ValueError("agreement and disagreement counts must cover all comparisons")
        if self.pairwise_agreement_rate != (
            self.pairwise_agreement_count / self.pairwise_comparison_count
        ):
            raise ValueError("pairwise agreement rate is inconsistent with counts")
        if self.initial_primary_agreement_target != PRIMARY_ARCHETYPE_AGREEMENT_TARGET:
            raise ValueError("agreement report target does not match frozen initial target")
        if self.meets_initial_primary_agreement_target != (
            self.pairwise_agreement_rate >= PRIMARY_ARCHETYPE_AGREEMENT_TARGET
        ):
            raise ValueError("agreement target result is inconsistent with agreement rate")
        if self.unanimous_listing_count > self.total_labels:
            raise ValueError("unanimous listing count exceeds total labels")
        if self.unanimous_listing_rate != self.unanimous_listing_count / self.total_labels:
            raise ValueError("unanimous listing rate is inconsistent with counts")
        total_assignments = self.total_labels * self.source_batch_count
        _validate_assignment_rate(
            self.low_confidence_assignment_count,
            self.low_confidence_assignment_rate,
            total_assignments,
            "low-confidence",
        )
        _validate_assignment_rate(
            self.unknown_assignment_count,
            self.unknown_assignment_rate,
            total_assignments,
            "unknown",
        )
        _validate_assignment_rate(
            self.other_assignment_count,
            self.other_assignment_rate,
            total_assignments,
            "other",
        )
        if len(self.disagreement_listing_ids) != (
            self.total_labels - self.unanimous_listing_count
        ):
            raise ValueError("disagreement listing IDs must cover every non-unanimous listing")
        disagreement_id_set = set(self.disagreement_listing_ids)
        if sum(pair.comparison_count for pair in self.confusion_pairs) != (
            self.pairwise_disagreement_count
        ):
            raise ValueError("confusion pair counts must cover every pairwise disagreement")
        for pair in self.confusion_pairs:
            if pair.comparison_rate != pair.comparison_count / self.pairwise_comparison_count:
                raise ValueError("confusion pair rate is inconsistent with comparison count")
            if any(listing_id not in disagreement_id_set for listing_id in pair.listing_ids):
                raise ValueError("confusion evidence must reference non-unanimous listings")
        expected_confusion_order = tuple(
            sorted(
                self.confusion_pairs,
                key=lambda pair: (
                    -pair.comparison_count,
                    _PRIMARY_ARCHETYPE_ORDER[pair.archetype_a],
                    _PRIMARY_ARCHETYPE_ORDER[pair.archetype_b],
                ),
            )
        )
        if self.confusion_pairs != expected_confusion_order:
            raise ValueError("confusion pairs must follow frozen deterministic ordering")
        if sum(metric.gold_support_count for metric in self.class_metrics) != self.total_labels:
            raise ValueError("class gold support must cover every gold label")
        if sum(metric.annotation_assignment_count for metric in self.class_metrics) != (
            total_assignments
        ):
            raise ValueError("class assignment counts must cover all independent assignments")
        metrics_by_archetype = {metric.archetype: metric for metric in self.class_metrics}
        if (
            metrics_by_archetype[PrimaryGameplayArchetype.UNKNOWN].annotation_assignment_count
            != self.unknown_assignment_count
        ):
            raise ValueError("unknown assignment count must match unknown class diagnostics")
        if (
            metrics_by_archetype[PrimaryGameplayArchetype.OTHER].annotation_assignment_count
            != self.other_assignment_count
        ):
            raise ValueError("other assignment count must match other class diagnostics")
        for metric in self.class_metrics:
            expected_gold_comparisons = metric.gold_support_count * self.source_batch_count
            if (
                metric.gold_alignment_true_positive_count
                + metric.gold_alignment_false_negative_count
                != expected_gold_comparisons
            ):
                raise ValueError("class gold-alignment recall support is inconsistent")
        return self


def build_primary_archetype_agreement_report(
    sample: TaxonomyDiversitySampleReport,
    gold_set: TaxonomyGoldSetReport,
    annotation_batches: tuple[TaxonomyAnnotationBatch, ...],
) -> PrimaryArchetypeAgreementReport:
    """Analyze independent primary labels without treating adjudication as agreement."""

    sample = TaxonomyDiversitySampleReport.model_validate(sample.model_dump(mode="python"))
    gold_set = TaxonomyGoldSetReport.model_validate(gold_set.model_dump(mode="python"))
    annotation_batches = tuple(
        TaxonomyAnnotationBatch.model_validate(batch.model_dump(mode="python"))
        for batch in annotation_batches
    )
    _validate_contract()
    gold_set = validate_taxonomy_gold_set_report(sample, gold_set)
    validated = _validate_source_batches(sample, gold_set, annotation_batches)

    total_labels = len(gold_set.labels)
    source_batch_count = len(validated)
    total_assignments = total_labels * source_batch_count
    pair_count = source_batch_count * (source_batch_count - 1) // 2
    pairwise_comparison_count = pair_count * total_labels
    pairwise_agreement_count = 0
    confusion_counts: Counter[
        tuple[PrimaryGameplayArchetype, PrimaryGameplayArchetype]
    ] = Counter()
    confusion_listing_ids: dict[
        tuple[PrimaryGameplayArchetype, PrimaryGameplayArchetype], list[str]
    ] = {}
    disagreement_listing_ids: list[str] = []

    for label_index, sample_member in enumerate(sample.selected):
        assignments = tuple(
            batch.labels[label_index].primary_archetype for batch in validated
        )
        if len(set(assignments)) == 1:
            continue
        disagreement_listing_ids.append(sample_member.platform_listing_id)
        for left_index, right_index in combinations(range(source_batch_count), 2):
            left = assignments[left_index]
            right = assignments[right_index]
            if left is right:
                pairwise_agreement_count += 1
                continue
            pair = _canonical_confusion_pair(left, right)
            confusion_counts[pair] += 1
            ids = confusion_listing_ids.setdefault(pair, [])
            if sample_member.platform_listing_id not in ids:
                ids.append(sample_member.platform_listing_id)

    unanimous_listing_count = total_labels - len(disagreement_listing_ids)
    pairwise_agreement_count += unanimous_listing_count * pair_count
    pairwise_disagreement_count = pairwise_comparison_count - pairwise_agreement_count

    all_labels = tuple(label for batch in validated for label in batch.labels)
    low_confidence_assignment_count = sum(
        label.confidence is TaxonomyAnnotationConfidence.LOW for label in all_labels
    )
    unknown_assignment_count = sum(
        label.primary_archetype is PrimaryGameplayArchetype.UNKNOWN for label in all_labels
    )
    other_assignment_count = sum(
        label.primary_archetype is PrimaryGameplayArchetype.OTHER for label in all_labels
    )

    confusion_pairs = _build_confusion_pairs(
        confusion_counts,
        confusion_listing_ids,
        pairwise_comparison_count,
    )
    class_metrics = _build_class_metrics(gold_set, validated)
    source_batches = tuple(
        PrimaryArchetypeAgreementSourceBatch(
            batch_id=batch.batch_id,
            annotator_id=batch.annotator_id,
            annotation_batch_hash=batch.annotation_batch_hash,
        )
        for batch in validated
    )
    pairwise_agreement_rate = pairwise_agreement_count / pairwise_comparison_count
    payload = _report_payload(
        sample=sample,
        gold_set=gold_set,
        source_batches=source_batches,
        total_labels=total_labels,
        pairwise_comparison_count=pairwise_comparison_count,
        pairwise_agreement_count=pairwise_agreement_count,
        pairwise_disagreement_count=pairwise_disagreement_count,
        pairwise_agreement_rate=pairwise_agreement_rate,
        unanimous_listing_count=unanimous_listing_count,
        low_confidence_assignment_count=low_confidence_assignment_count,
        unknown_assignment_count=unknown_assignment_count,
        other_assignment_count=other_assignment_count,
        disagreement_listing_ids=tuple(disagreement_listing_ids),
        confusion_pairs=confusion_pairs,
        class_metrics=class_metrics,
    )
    content_hash = _content_hash(payload)
    return PrimaryArchetypeAgreementReport(
        sample_id=sample.sample_id,
        sample_content_hash=sample.sample_content_hash,
        gold_set_id=gold_set.gold_set_id,
        gold_set_content_hash=gold_set.gold_set_content_hash,
        source_batches=source_batches,
        total_labels=total_labels,
        source_batch_count=source_batch_count,
        pairwise_comparison_count=pairwise_comparison_count,
        pairwise_agreement_count=pairwise_agreement_count,
        pairwise_disagreement_count=pairwise_disagreement_count,
        pairwise_agreement_rate=pairwise_agreement_rate,
        initial_primary_agreement_target=PRIMARY_ARCHETYPE_AGREEMENT_TARGET,
        meets_initial_primary_agreement_target=(
            pairwise_agreement_rate >= PRIMARY_ARCHETYPE_AGREEMENT_TARGET
        ),
        unanimous_listing_count=unanimous_listing_count,
        unanimous_listing_rate=unanimous_listing_count / total_labels,
        low_confidence_assignment_count=low_confidence_assignment_count,
        low_confidence_assignment_rate=low_confidence_assignment_count / total_assignments,
        unknown_assignment_count=unknown_assignment_count,
        unknown_assignment_rate=unknown_assignment_count / total_assignments,
        other_assignment_count=other_assignment_count,
        other_assignment_rate=other_assignment_count / total_assignments,
        disagreement_listing_ids=tuple(disagreement_listing_ids),
        confusion_pairs=confusion_pairs,
        class_metrics=class_metrics,
        agreement_content_hash=content_hash,
    )


def validate_primary_archetype_agreement_report(
    sample: TaxonomyDiversitySampleReport,
    gold_set: TaxonomyGoldSetReport,
    annotation_batches: tuple[TaxonomyAnnotationBatch, ...],
    report: PrimaryArchetypeAgreementReport,
) -> PrimaryArchetypeAgreementReport:
    """Rebuild and compare a persisted independent-annotation agreement artifact."""

    report = PrimaryArchetypeAgreementReport.model_validate(report.model_dump(mode="python"))
    expected = build_primary_archetype_agreement_report(sample, gold_set, annotation_batches)
    if report != expected:
        raise PrimaryArchetypeAgreementError(
            "persisted primary-archetype agreement report does not match rebuilt content"
        )
    return report


def primary_archetype_agreement_contract_content_hash() -> str:
    payload = {
        "spec_version": PRIMARY_ARCHETYPE_AGREEMENT_SPEC_VERSION,
        "agreement_contract_version": PRIMARY_ARCHETYPE_AGREEMENT_CONTRACT_VERSION,
        "sample_spec_version": TAXONOMY_DIVERSITY_SAMPLE_SPEC_VERSION,
        "gold_set_spec_version": GOLD_SET_SPEC_VERSION,
        "annotation_spec_version": ANNOTATION_SPEC_VERSION,
        "annotation_contract_content_hash": ANNOTATION_CONTRACT_V1_CONTENT_HASH,
        "label_registry_version": LABEL_REGISTRY_VERSION,
        "label_registry_content_hash": TAXONOMY_LABEL_REGISTRY_V1_CONTENT_HASH,
        "primary_archetypes": [item.value for item in PrimaryGameplayArchetype],
        "initial_primary_agreement_target": PRIMARY_ARCHETYPE_AGREEMENT_TARGET,
        "source_batch_fields": list(PrimaryArchetypeAgreementSourceBatch.model_fields),
        "confusion_pair_fields": list(PrimaryArchetypeConfusionPair.model_fields),
        "class_metric_fields": list(PrimaryArchetypeClassAgreement.model_fields),
        "report_fields": list(PrimaryArchetypeAgreementReport.model_fields),
        "rules": list(_AGREEMENT_RULES),
        "pairwise_agreement_formula": (
            "matching_independent_primary_assignments/all_annotator_pair_comparisons"
        ),
        "confusion_pair_order": (
            "descending_comparison_count_then_primary_registry_pair_order"
        ),
        "class_metric_order": "primary_registry_order_including_other_and_unknown",
        "content_hash_canonicalization": (
            "json-sort-keys-compact-utf8-ensure-ascii-false"
        ),
    }
    return _content_hash(payload)


def _validate_contract() -> None:
    if (
        primary_archetype_agreement_contract_content_hash()
        != PRIMARY_ARCHETYPE_AGREEMENT_CONTRACT_V1_CONTENT_HASH
    ):
        raise PrimaryArchetypeAgreementError(
            "primary-archetype agreement contract changed without a new version"
        )


def _validate_source_batches(
    sample: TaxonomyDiversitySampleReport,
    gold_set: TaxonomyGoldSetReport,
    annotation_batches: tuple[TaxonomyAnnotationBatch, ...],
) -> tuple[ValidatedTaxonomyAnnotationBatch, ...]:
    if len(annotation_batches) < 2:
        raise PrimaryArchetypeAgreementError(
            "primary-archetype agreement requires at least two independent annotation batches"
        )
    validated = tuple(
        validate_taxonomy_annotation_batch(sample, batch) for batch in annotation_batches
    )
    batch_ids = tuple(batch.batch_id for batch in validated)
    annotator_ids = tuple(batch.annotator_id for batch in validated)
    if len(batch_ids) != len(set(batch_ids)):
        raise PrimaryArchetypeAgreementError("agreement source batch IDs must be unique")
    if len(annotator_ids) != len(set(annotator_ids)):
        raise PrimaryArchetypeAgreementError(
            "agreement source batches require unique annotator identities"
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
        raise PrimaryArchetypeAgreementError(
            "agreement source batches must exactly match gold-set source batches in order"
        )
    return validated


def _canonical_confusion_pair(
    left: PrimaryGameplayArchetype,
    right: PrimaryGameplayArchetype,
) -> tuple[PrimaryGameplayArchetype, PrimaryGameplayArchetype]:
    if _PRIMARY_ARCHETYPE_ORDER[left] < _PRIMARY_ARCHETYPE_ORDER[right]:
        return left, right
    return right, left


def _build_confusion_pairs(
    counts: Counter[tuple[PrimaryGameplayArchetype, PrimaryGameplayArchetype]],
    listing_ids: dict[
        tuple[PrimaryGameplayArchetype, PrimaryGameplayArchetype], list[str]
    ],
    total_comparisons: int,
) -> tuple[PrimaryArchetypeConfusionPair, ...]:
    ordered_pairs = sorted(
        counts,
        key=lambda pair: (
            -counts[pair],
            _PRIMARY_ARCHETYPE_ORDER[pair[0]],
            _PRIMARY_ARCHETYPE_ORDER[pair[1]],
        ),
    )
    return tuple(
        PrimaryArchetypeConfusionPair(
            archetype_a=pair[0],
            archetype_b=pair[1],
            comparison_count=counts[pair],
            comparison_rate=counts[pair] / total_comparisons,
            listing_ids=tuple(listing_ids[pair]),
        )
        for pair in ordered_pairs
    )


def _build_class_metrics(
    gold_set: TaxonomyGoldSetReport,
    validated: tuple[ValidatedTaxonomyAnnotationBatch, ...],
) -> tuple[PrimaryArchetypeClassAgreement, ...]:
    metrics: list[PrimaryArchetypeClassAgreement] = []
    for archetype in PrimaryGameplayArchetype:
        gold_support_count = sum(
            label.primary_archetype is archetype for label in gold_set.labels
        )
        true_positive_count = 0
        false_positive_count = 0
        false_negative_count = 0
        for batch in validated:
            for gold_label, annotation_label in zip(gold_set.labels, batch.labels, strict=True):
                gold_matches = gold_label.primary_archetype is archetype
                annotation_matches = annotation_label.primary_archetype is archetype
                if gold_matches and annotation_matches:
                    true_positive_count += 1
                elif annotation_matches:
                    false_positive_count += 1
                elif gold_matches:
                    false_negative_count += 1
        assignment_count = true_positive_count + false_positive_count
        metrics.append(
            PrimaryArchetypeClassAgreement(
                archetype=archetype,
                gold_support_count=gold_support_count,
                annotation_assignment_count=assignment_count,
                gold_alignment_true_positive_count=true_positive_count,
                gold_alignment_false_positive_count=false_positive_count,
                gold_alignment_false_negative_count=false_negative_count,
                gold_alignment_precision=_optional_rate(
                    true_positive_count,
                    assignment_count,
                ),
                gold_alignment_recall=_optional_rate(
                    true_positive_count,
                    true_positive_count + false_negative_count,
                ),
            )
        )
    return tuple(metrics)


def _report_payload(
    *,
    sample: TaxonomyDiversitySampleReport,
    gold_set: TaxonomyGoldSetReport,
    source_batches: tuple[PrimaryArchetypeAgreementSourceBatch, ...],
    total_labels: int,
    pairwise_comparison_count: int,
    pairwise_agreement_count: int,
    pairwise_disagreement_count: int,
    pairwise_agreement_rate: float,
    unanimous_listing_count: int,
    low_confidence_assignment_count: int,
    unknown_assignment_count: int,
    other_assignment_count: int,
    disagreement_listing_ids: tuple[str, ...],
    confusion_pairs: tuple[PrimaryArchetypeConfusionPair, ...],
    class_metrics: tuple[PrimaryArchetypeClassAgreement, ...],
) -> dict[str, object]:
    source_batch_count = len(source_batches)
    total_assignments = total_labels * source_batch_count
    return {
        "spec_version": PRIMARY_ARCHETYPE_AGREEMENT_SPEC_VERSION,
        "agreement_contract_version": PRIMARY_ARCHETYPE_AGREEMENT_CONTRACT_VERSION,
        "agreement_contract_content_hash": (
            PRIMARY_ARCHETYPE_AGREEMENT_CONTRACT_V1_CONTENT_HASH
        ),
        "annotation_contract_content_hash": ANNOTATION_CONTRACT_V1_CONTENT_HASH,
        "label_registry_content_hash": TAXONOMY_LABEL_REGISTRY_V1_CONTENT_HASH,
        "sample_id": sample.sample_id,
        "sample_content_hash": sample.sample_content_hash,
        "gold_set_id": gold_set.gold_set_id,
        "gold_set_content_hash": gold_set.gold_set_content_hash,
        "source_batches": [batch.model_dump(mode="json") for batch in source_batches],
        "total_labels": total_labels,
        "source_batch_count": source_batch_count,
        "pairwise_comparison_count": pairwise_comparison_count,
        "pairwise_agreement_count": pairwise_agreement_count,
        "pairwise_disagreement_count": pairwise_disagreement_count,
        "pairwise_agreement_rate": pairwise_agreement_rate,
        "initial_primary_agreement_target": PRIMARY_ARCHETYPE_AGREEMENT_TARGET,
        "meets_initial_primary_agreement_target": (
            pairwise_agreement_rate >= PRIMARY_ARCHETYPE_AGREEMENT_TARGET
        ),
        "unanimous_listing_count": unanimous_listing_count,
        "unanimous_listing_rate": unanimous_listing_count / total_labels,
        "low_confidence_assignment_count": low_confidence_assignment_count,
        "low_confidence_assignment_rate": (
            low_confidence_assignment_count / total_assignments
        ),
        "unknown_assignment_count": unknown_assignment_count,
        "unknown_assignment_rate": unknown_assignment_count / total_assignments,
        "other_assignment_count": other_assignment_count,
        "other_assignment_rate": other_assignment_count / total_assignments,
        "disagreement_listing_ids": list(disagreement_listing_ids),
        "confusion_pairs": [pair.model_dump(mode="json") for pair in confusion_pairs],
        "class_metrics": [metric.model_dump(mode="json") for metric in class_metrics],
    }


def _validate_source_batch_uniqueness(
    batches: tuple[PrimaryArchetypeAgreementSourceBatch, ...],
) -> None:
    batch_ids = tuple(batch.batch_id for batch in batches)
    annotator_ids = tuple(batch.annotator_id for batch in batches)
    hashes = tuple(batch.annotation_batch_hash for batch in batches)
    if len(batch_ids) != len(set(batch_ids)):
        raise ValueError("agreement source batch IDs must be unique")
    if len(annotator_ids) != len(set(annotator_ids)):
        raise ValueError("agreement source annotators must be unique")
    if len(hashes) != len(set(hashes)):
        raise ValueError("agreement source batch hashes must be unique")


def _validate_assignment_rate(
    count: int,
    rate: float,
    total_assignments: int,
    label: str,
) -> None:
    if count > total_assignments:
        raise ValueError(f"{label} assignment count exceeds total assignments")
    if rate != count / total_assignments:
        raise ValueError(f"{label} assignment rate is inconsistent with count")


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
