from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .gold_set import (
    ANNOTATION_CONTRACT_V1_CONTENT_HASH,
    GOLD_SET_SPEC_VERSION,
    TaxonomyAnnotationConfidence,
    TaxonomyGoldSetReport,
    TaxonomyManualLabel,
    validate_taxonomy_gold_set_report,
)
from .models import PrimaryGameplayArchetype
from .sampling import (
    SPEC_VERSION as TAXONOMY_DIVERSITY_SAMPLE_SPEC_VERSION,
    TaxonomyDiversitySampleReport,
)

PRIMARY_ARCHETYPE_VALIDATION_SPEC_VERSION: Literal[
    "taxonomy-primary-archetype-validation-v1"
] = "taxonomy-primary-archetype-validation-v1"
PRIMARY_ARCHETYPE_VALIDATION_CONTRACT_VERSION: Literal[
    "primary-archetype-review-v1"
] = "primary-archetype-review-v1"
PRIMARY_ARCHETYPE_VALIDATION_CONTRACT_V1_CONTENT_HASH = (
    "83d983d0062d61a6fb434b9b18debc536aba712b7a31ee584fdb7268f8f93d57"
)
_REVIEWED_LABEL_COUNT_MIN = 100
_REVIEWED_LABEL_COUNT_MAX = 200
_MODELED_PRIMARY_ARCHETYPES = tuple(
    archetype
    for archetype in PrimaryGameplayArchetype
    if archetype not in {PrimaryGameplayArchetype.OTHER, PrimaryGameplayArchetype.UNKNOWN}
)
_SPECIAL_PRIMARY_STATES = (
    PrimaryGameplayArchetype.OTHER,
    PrimaryGameplayArchetype.UNKNOWN,
)
_VALIDATION_RULES = (
    "gold_set_revalidated_against_exact_sample_before_review",
    "declaration_binds_exact_gold_set_id_and_content_hash",
    "validation_identifiers_nonblank_trimmed",
    "reviewed_at_timezone_aware_canonicalized_to_utc",
    "every_modeled_archetype_reviewed_once_in_registry_order",
    "other_unknown_are_diagnostic_only_not_review_rows",
    "evidence_listing_ids_nonblank_trimmed_unique",
    "rationale_nonblank_trimmed",
    "evidence_listing_ids_must_match_adjudicated_archetype",
    "zero_support_forces_insufficient_evidence",
    "non_insufficient_disposition_requires_evidence",
    "insufficient_evidence_may_be_used_with_supported_labels",
    "support_counts_and_rates_are_diagnostic_not_automatic_validation",
    "revision_candidates_exclude_keep_and_insufficient_evidence",
    "agreement_confusion_analysis_is_out_of_scope",
)


class PrimaryArchetypeReviewDisposition(StrEnum):
    KEEP = "keep"
    REVISE_BOUNDARY = "revise_boundary"
    MERGE_CANDIDATE = "merge_candidate"
    SPLIT_CANDIDATE = "split_candidate"
    RENAME_CANDIDATE = "rename_candidate"
    REMOVE_CANDIDATE = "remove_candidate"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class PrimaryArchetypeValidationError(ValueError):
    """A primary-archetype validation artifact violates the frozen review protocol."""


class PrimaryArchetypeLabelReview(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    archetype: PrimaryGameplayArchetype
    disposition: PrimaryArchetypeReviewDisposition
    evidence_listing_ids: tuple[str, ...] = ()
    rationale: str

    @field_validator("evidence_listing_ids")
    @classmethod
    def validate_evidence_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if any(not value for value in normalized):
            raise ValueError("primary-archetype review evidence IDs cannot be blank")
        if len(normalized) != len(set(normalized)):
            raise ValueError("primary-archetype review evidence IDs must be unique")
        return normalized

    @field_validator("rationale")
    @classmethod
    def validate_rationale(cls, value: str) -> str:
        if not value or value != value.strip():
            raise ValueError("primary-archetype review rationale must be nonblank and trimmed")
        return value

    @model_validator(mode="after")
    def validate_archetype(self) -> Self:
        if self.archetype in _SPECIAL_PRIMARY_STATES:
            raise ValueError("other/unknown are diagnostics, not modeled archetype review rows")
        return self


class PrimaryArchetypeValidationDeclaration(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: Literal["taxonomy-primary-archetype-validation-v1"] = (
        PRIMARY_ARCHETYPE_VALIDATION_SPEC_VERSION
    )
    validation_contract_version: Literal["primary-archetype-review-v1"] = (
        PRIMARY_ARCHETYPE_VALIDATION_CONTRACT_VERSION
    )
    review_id: str
    reviewer_id: str
    gold_set_id: str
    gold_set_content_hash: str
    reviewed_at: datetime
    reviews: tuple[PrimaryArchetypeLabelReview, ...] = Field(min_length=1)

    @field_validator("review_id", "reviewer_id", "gold_set_id")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        if not value or value != value.strip():
            raise ValueError(
                "primary-archetype validation identifiers must be nonblank and trimmed"
            )
        return value

    @field_validator("gold_set_content_hash")
    @classmethod
    def validate_gold_hash(cls, value: str) -> str:
        _validate_sha256(value, "gold_set_content_hash")
        return value

    @field_validator("reviewed_at")
    @classmethod
    def validate_reviewed_at(cls, value: datetime) -> datetime:
        return _utc_datetime(value, "primary-archetype validation reviewed_at")

    @model_validator(mode="after")
    def validate_review_shape(self) -> Self:
        archetypes = tuple(review.archetype for review in self.reviews)
        if archetypes != _MODELED_PRIMARY_ARCHETYPES:
            raise ValueError(
                "primary-archetype validation must review every modeled archetype exactly once "
                "in registry order"
            )
        return self


class PrimaryArchetypeValidationEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    archetype: PrimaryGameplayArchetype
    support_count: int = Field(ge=0)
    support_rate: float = Field(ge=0.0, le=1.0)
    high_confidence_count: int = Field(ge=0)
    medium_confidence_count: int = Field(ge=0)
    low_confidence_count: int = Field(ge=0)
    adjudicated_listing_ids: tuple[str, ...]
    disposition: PrimaryArchetypeReviewDisposition
    evidence_listing_ids: tuple[str, ...]
    rationale: str

    @model_validator(mode="after")
    def validate_entry(self) -> Self:
        if self.archetype in _SPECIAL_PRIMARY_STATES:
            raise ValueError("validation entries cannot use other/unknown special states")
        if self.support_count != len(self.adjudicated_listing_ids):
            raise ValueError("validation entry support_count must match adjudicated listing IDs")
        if (
            self.high_confidence_count
            + self.medium_confidence_count
            + self.low_confidence_count
            != self.support_count
        ):
            raise ValueError("validation entry confidence counts must sum to support_count")
        return self


class PrimaryArchetypeValidationReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: Literal["taxonomy-primary-archetype-validation-v1"] = (
        PRIMARY_ARCHETYPE_VALIDATION_SPEC_VERSION
    )
    validation_contract_version: Literal["primary-archetype-review-v1"] = (
        PRIMARY_ARCHETYPE_VALIDATION_CONTRACT_VERSION
    )
    validation_contract_content_hash: str = (
        PRIMARY_ARCHETYPE_VALIDATION_CONTRACT_V1_CONTENT_HASH
    )
    annotation_contract_content_hash: str = ANNOTATION_CONTRACT_V1_CONTENT_HASH
    review_id: str
    reviewer_id: str
    reviewed_at: datetime
    sample_id: str
    sample_content_hash: str
    gold_set_id: str
    gold_set_content_hash: str
    total_labels: int = Field(ge=_REVIEWED_LABEL_COUNT_MIN, le=_REVIEWED_LABEL_COUNT_MAX)
    modeled_label_count: int = Field(ge=0)
    unknown_count: int = Field(ge=0)
    unknown_rate: float = Field(ge=0.0, le=1.0)
    other_count: int = Field(ge=0)
    other_rate: float = Field(ge=0.0, le=1.0)
    high_confidence_count: int = Field(ge=0)
    medium_confidence_count: int = Field(ge=0)
    low_confidence_count: int = Field(ge=0)
    labels_with_support: int = Field(ge=0)
    labels_without_support: int = Field(ge=0)
    revision_candidate_count: int = Field(ge=0)
    entries: tuple[PrimaryArchetypeValidationEntry, ...] = Field(min_length=1)
    validation_content_hash: str

    @field_validator("review_id", "reviewer_id", "sample_id", "gold_set_id")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        if not value or value != value.strip():
            raise ValueError("primary-archetype validation report IDs must be nonblank and trimmed")
        return value

    @field_validator("reviewed_at")
    @classmethod
    def validate_reviewed_at(cls, value: datetime) -> datetime:
        return _utc_datetime(value, "primary-archetype validation report reviewed_at")

    @field_validator(
        "validation_contract_content_hash",
        "annotation_contract_content_hash",
        "sample_content_hash",
        "gold_set_content_hash",
        "validation_content_hash",
    )
    @classmethod
    def validate_hash(cls, value: str) -> str:
        _validate_sha256(value, "primary-archetype validation report hash")
        return value

    @model_validator(mode="after")
    def validate_report_shape(self) -> Self:
        if (
            self.validation_contract_content_hash
            != PRIMARY_ARCHETYPE_VALIDATION_CONTRACT_V1_CONTENT_HASH
        ):
            raise ValueError("validation report contract content hash does not match v1")
        if self.annotation_contract_content_hash != ANNOTATION_CONTRACT_V1_CONTENT_HASH:
            raise ValueError("validation report annotation contract hash does not match v1")
        if tuple(entry.archetype for entry in self.entries) != _MODELED_PRIMARY_ARCHETYPES:
            raise ValueError(
                "validation report entries must follow modeled archetype registry order"
            )
        if self.modeled_label_count + self.unknown_count + self.other_count != self.total_labels:
            raise ValueError("validation report label counts must sum to total_labels")
        if (
            self.high_confidence_count
            + self.medium_confidence_count
            + self.low_confidence_count
            != self.total_labels
        ):
            raise ValueError("validation report confidence counts must sum to total_labels")
        if self.labels_with_support + self.labels_without_support != len(self.entries):
            raise ValueError("validation report support diagnostics must cover every entry")
        if self.revision_candidate_count > len(self.entries):
            raise ValueError("validation report revision candidate count exceeds entry count")
        return self


def build_primary_archetype_validation_report(
    sample: TaxonomyDiversitySampleReport,
    gold_set: TaxonomyGoldSetReport,
    declaration: PrimaryArchetypeValidationDeclaration,
) -> PrimaryArchetypeValidationReport:
    """Build a manual primary-label review report without doing agreement/confusion analysis."""

    sample = TaxonomyDiversitySampleReport.model_validate(sample.model_dump(mode="python"))
    gold_set = TaxonomyGoldSetReport.model_validate(gold_set.model_dump(mode="python"))
    declaration = PrimaryArchetypeValidationDeclaration.model_validate(
        declaration.model_dump(mode="python")
    )
    _validate_contract()
    gold_set = validate_taxonomy_gold_set_report(sample, gold_set)
    if declaration.gold_set_id != gold_set.gold_set_id:
        raise PrimaryArchetypeValidationError(
            "primary-archetype validation declaration references a different gold set"
        )
    if declaration.gold_set_content_hash != gold_set.gold_set_content_hash:
        raise PrimaryArchetypeValidationError(
            "primary-archetype validation declaration gold-set hash does not match"
        )

    by_archetype: dict[PrimaryGameplayArchetype, list[TaxonomyManualLabel]] = {
        archetype: [] for archetype in PrimaryGameplayArchetype
    }
    for label in gold_set.labels:
        by_archetype[label.primary_archetype].append(label)

    entries = tuple(
        _build_entry(
            review,
            by_archetype[review.archetype],
            total=len(gold_set.labels),
        )
        for review in declaration.reviews
    )
    counts = Counter(label.confidence for label in gold_set.labels)
    unknown_count = len(by_archetype[PrimaryGameplayArchetype.UNKNOWN])
    other_count = len(by_archetype[PrimaryGameplayArchetype.OTHER])
    total = len(gold_set.labels)
    modeled_count = total - unknown_count - other_count
    labels_with_support = sum(entry.support_count > 0 for entry in entries)
    labels_without_support = len(entries) - labels_with_support
    revision_candidate_count = sum(
        entry.disposition
        not in {
            PrimaryArchetypeReviewDisposition.KEEP,
            PrimaryArchetypeReviewDisposition.INSUFFICIENT_EVIDENCE,
        }
        for entry in entries
    )

    payload = _report_payload(
        declaration=declaration,
        sample=sample,
        gold_set=gold_set,
        total=total,
        modeled_count=modeled_count,
        unknown_count=unknown_count,
        other_count=other_count,
        confidence_counts=counts,
        labels_with_support=labels_with_support,
        labels_without_support=labels_without_support,
        revision_candidate_count=revision_candidate_count,
        entries=entries,
    )
    content_hash = _content_hash(payload)
    return PrimaryArchetypeValidationReport(
        review_id=declaration.review_id,
        reviewer_id=declaration.reviewer_id,
        reviewed_at=declaration.reviewed_at,
        sample_id=sample.sample_id,
        sample_content_hash=sample.sample_content_hash,
        gold_set_id=gold_set.gold_set_id,
        gold_set_content_hash=gold_set.gold_set_content_hash,
        total_labels=total,
        modeled_label_count=modeled_count,
        unknown_count=unknown_count,
        unknown_rate=unknown_count / total,
        other_count=other_count,
        other_rate=other_count / total,
        high_confidence_count=counts[TaxonomyAnnotationConfidence.HIGH],
        medium_confidence_count=counts[TaxonomyAnnotationConfidence.MEDIUM],
        low_confidence_count=counts[TaxonomyAnnotationConfidence.LOW],
        labels_with_support=labels_with_support,
        labels_without_support=labels_without_support,
        revision_candidate_count=revision_candidate_count,
        entries=entries,
        validation_content_hash=content_hash,
    )


def validate_primary_archetype_validation_report(
    sample: TaxonomyDiversitySampleReport,
    gold_set: TaxonomyGoldSetReport,
    declaration: PrimaryArchetypeValidationDeclaration,
    report: PrimaryArchetypeValidationReport,
) -> PrimaryArchetypeValidationReport:
    """Rebuild and compare a persisted primary-label validation report."""

    report = PrimaryArchetypeValidationReport.model_validate(report.model_dump(mode="python"))
    expected = build_primary_archetype_validation_report(sample, gold_set, declaration)
    if report != expected:
        raise PrimaryArchetypeValidationError(
            "persisted primary-archetype validation report does not match rebuilt content"
        )
    return report


def primary_archetype_validation_contract_content_hash() -> str:
    payload = {
        "spec_version": PRIMARY_ARCHETYPE_VALIDATION_SPEC_VERSION,
        "validation_contract_version": PRIMARY_ARCHETYPE_VALIDATION_CONTRACT_VERSION,
        "sample_spec_version": TAXONOMY_DIVERSITY_SAMPLE_SPEC_VERSION,
        "gold_set_spec_version": GOLD_SET_SPEC_VERSION,
        "annotation_contract_content_hash": ANNOTATION_CONTRACT_V1_CONTENT_HASH,
        "modeled_primary_archetypes": [item.value for item in _MODELED_PRIMARY_ARCHETYPES],
        "special_primary_states": [item.value for item in _SPECIAL_PRIMARY_STATES],
        "dispositions": [item.value for item in PrimaryArchetypeReviewDisposition],
        "reviewed_label_count_bounds": {
            "min": _REVIEWED_LABEL_COUNT_MIN,
            "max": _REVIEWED_LABEL_COUNT_MAX,
        },
        "declaration_fields": list(PrimaryArchetypeValidationDeclaration.model_fields),
        "review_fields": list(PrimaryArchetypeLabelReview.model_fields),
        "entry_fields": list(PrimaryArchetypeValidationEntry.model_fields),
        "report_fields": list(PrimaryArchetypeValidationReport.model_fields),
        "rules": list(_VALIDATION_RULES),
        "datetime_canonicalization": "timezone-aware-to-utc-isoformat",
        "content_hash_canonicalization": "json-sort-keys-compact-utf8-ensure-ascii-false",
    }
    return _content_hash(payload)


def _validate_contract() -> None:
    if (
        primary_archetype_validation_contract_content_hash()
        != PRIMARY_ARCHETYPE_VALIDATION_CONTRACT_V1_CONTENT_HASH
    ):
        raise PrimaryArchetypeValidationError(
            "primary-archetype validation contract changed without a new version"
        )


def _build_entry(
    review: PrimaryArchetypeLabelReview,
    labels: list[TaxonomyManualLabel],
    *,
    total: int,
) -> PrimaryArchetypeValidationEntry:
    listing_ids = tuple(label.platform_listing_id for label in labels)
    listing_id_set = set(listing_ids)
    if any(value not in listing_id_set for value in review.evidence_listing_ids):
        raise PrimaryArchetypeValidationError(
            f"review evidence for {review.archetype.value} must use listings adjudicated "
            "to that archetype"
        )
    if (
        not labels
        and review.disposition is not PrimaryArchetypeReviewDisposition.INSUFFICIENT_EVIDENCE
    ):
        raise PrimaryArchetypeValidationError(
            f"archetype {review.archetype.value} has zero gold-set support and must be "
            "insufficient_evidence"
        )
    if (
        review.disposition is not PrimaryArchetypeReviewDisposition.INSUFFICIENT_EVIDENCE
        and not review.evidence_listing_ids
    ):
        raise PrimaryArchetypeValidationError(
            f"archetype {review.archetype.value} review disposition requires evidence listing IDs"
        )
    confidence_counts = Counter(label.confidence for label in labels)
    return PrimaryArchetypeValidationEntry(
        archetype=review.archetype,
        support_count=len(labels),
        support_rate=len(labels) / total,
        high_confidence_count=confidence_counts[TaxonomyAnnotationConfidence.HIGH],
        medium_confidence_count=confidence_counts[TaxonomyAnnotationConfidence.MEDIUM],
        low_confidence_count=confidence_counts[TaxonomyAnnotationConfidence.LOW],
        adjudicated_listing_ids=listing_ids,
        disposition=review.disposition,
        evidence_listing_ids=review.evidence_listing_ids,
        rationale=review.rationale,
    )


def _report_payload(
    *,
    declaration: PrimaryArchetypeValidationDeclaration,
    sample: TaxonomyDiversitySampleReport,
    gold_set: TaxonomyGoldSetReport,
    total: int,
    modeled_count: int,
    unknown_count: int,
    other_count: int,
    confidence_counts: Counter[TaxonomyAnnotationConfidence],
    labels_with_support: int,
    labels_without_support: int,
    revision_candidate_count: int,
    entries: tuple[PrimaryArchetypeValidationEntry, ...],
) -> dict[str, object]:
    return {
        "spec_version": PRIMARY_ARCHETYPE_VALIDATION_SPEC_VERSION,
        "validation_contract_version": PRIMARY_ARCHETYPE_VALIDATION_CONTRACT_VERSION,
        "validation_contract_content_hash": (
            PRIMARY_ARCHETYPE_VALIDATION_CONTRACT_V1_CONTENT_HASH
        ),
        "annotation_contract_content_hash": ANNOTATION_CONTRACT_V1_CONTENT_HASH,
        "review_id": declaration.review_id,
        "reviewer_id": declaration.reviewer_id,
        "reviewed_at": declaration.reviewed_at.isoformat(),
        "sample_id": sample.sample_id,
        "sample_content_hash": sample.sample_content_hash,
        "gold_set_id": gold_set.gold_set_id,
        "gold_set_content_hash": gold_set.gold_set_content_hash,
        "total_labels": total,
        "modeled_label_count": modeled_count,
        "unknown_count": unknown_count,
        "unknown_rate": unknown_count / total,
        "other_count": other_count,
        "other_rate": other_count / total,
        "high_confidence_count": confidence_counts[TaxonomyAnnotationConfidence.HIGH],
        "medium_confidence_count": confidence_counts[TaxonomyAnnotationConfidence.MEDIUM],
        "low_confidence_count": confidence_counts[TaxonomyAnnotationConfidence.LOW],
        "labels_with_support": labels_with_support,
        "labels_without_support": labels_without_support,
        "revision_candidate_count": revision_candidate_count,
        "entries": [entry.model_dump(mode="json") for entry in entries],
    }


def _utc_datetime(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


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
