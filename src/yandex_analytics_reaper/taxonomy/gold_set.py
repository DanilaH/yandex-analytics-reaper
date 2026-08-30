from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .models import PrimaryGameplayArchetype
from .registries import (
    TAXONOMY_LABEL_REGISTRY_V1_CONTENT_HASH,
    ControlledLabelDimension,
    get_taxonomy_label_registry,
    normalize_taxonomy_label,
)
from .sampling import TaxonomyDiversitySampleReport

ANNOTATION_SPEC_VERSION: Literal["taxonomy-manual-annotation-v1"] = (
    "taxonomy-manual-annotation-v1"
)
GOLD_SET_SPEC_VERSION: Literal["taxonomy-gold-set-v1"] = "taxonomy-gold-set-v1"
ANNOTATION_CONTRACT_VERSION: Literal["phase3-draft-v1"] = "phase3-draft-v1"
ANNOTATION_CONTRACT_V1_CONTENT_HASH = (
    "9815b185ef709cb9275985474970165f16eef8f78ea74e73c1397b38fa646c17"
)
LABEL_REGISTRY_VERSION: Literal[1] = 1
_SAMPLE_PARSER_NAME = "YandexFeedParser"
_SAMPLE_PARSER_VERSION = "2"
_SAMPLE_MAX_PER_DEVELOPER = 2
_CONTROLLED_DIMENSIONS = (
    ControlledLabelDimension.MECHANICS,
    ControlledLabelDimension.OBJECTIVES,
    ControlledLabelDimension.META_SYSTEMS,
    ControlledLabelDimension.TONES,
)
_MANUAL_LABEL_FIELDS = (
    "platform_listing_id",
    "primary_archetype",
    "mechanics",
    "objectives",
    "meta_systems",
    "tones",
    "confidence",
    "rationale",
)
_RATIONALE_REQUIRED_PRIMARY_STATES = (
    PrimaryGameplayArchetype.OTHER,
    PrimaryGameplayArchetype.UNKNOWN,
)
_EXCLUSIVE_META_LABELS = ("none",)


class TaxonomyAnnotationConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TaxonomyGoldSetError(ValueError):
    """Manual taxonomy annotations cannot form the requested gold-set artifact."""


class TaxonomyManualLabel(BaseModel):
    """Manual label surface intentionally limited to the Phase 3 validation target."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    platform_listing_id: str
    primary_archetype: PrimaryGameplayArchetype
    mechanics: tuple[str, ...] = ()
    objectives: tuple[str, ...] = ()
    meta_systems: tuple[str, ...] = ()
    tones: tuple[str, ...] = ()
    confidence: TaxonomyAnnotationConfidence
    rationale: str | None = None

    @field_validator("platform_listing_id")
    @classmethod
    def validate_listing_id(cls, value: str) -> str:
        return _trimmed_identifier(value, "taxonomy annotation listing ID")

    @field_validator("mechanics", "objectives", "meta_systems", "tones")
    @classmethod
    def validate_controlled_labels(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(normalize_taxonomy_label(value) for value in values)
        if len(normalized) != len(set(normalized)):
            raise ValueError("manual taxonomy labels must be unique within each dimension")
        return normalized

    @field_validator("rationale")
    @classmethod
    def validate_rationale(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _trimmed_identifier(value, "taxonomy annotation rationale")

    @model_validator(mode="after")
    def validate_semantics(self) -> Self:
        registry = get_taxonomy_label_registry(LABEL_REGISTRY_VERSION)
        registry.validate_membership(ControlledLabelDimension.MECHANICS, self.mechanics)
        registry.validate_membership(ControlledLabelDimension.OBJECTIVES, self.objectives)
        registry.validate_membership(ControlledLabelDimension.META_SYSTEMS, self.meta_systems)
        registry.validate_membership(ControlledLabelDimension.TONES, self.tones)
        if "none" in self.meta_systems and len(self.meta_systems) != 1:
            raise ValueError("meta_systems label 'none' cannot be combined with other labels")
        if self.primary_archetype in _RATIONALE_REQUIRED_PRIMARY_STATES and self.rationale is None:
            raise ValueError("unknown/other primary archetype requires an explicit rationale")
        return self


class TaxonomyAnnotationBatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: Literal["taxonomy-manual-annotation-v1"] = ANNOTATION_SPEC_VERSION
    annotation_contract_version: Literal["phase3-draft-v1"] = ANNOTATION_CONTRACT_VERSION
    label_registry_version: Literal[1] = LABEL_REGISTRY_VERSION
    batch_id: str
    annotator_id: str
    sample_id: str
    sample_content_hash: str
    created_at: datetime
    labels: tuple[TaxonomyManualLabel, ...] = Field(min_length=100, max_length=200)

    @field_validator("batch_id", "annotator_id", "sample_id")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        return _trimmed_identifier(value, "taxonomy annotation identifier")

    @field_validator("sample_content_hash")
    @classmethod
    def validate_sample_hash(cls, value: str) -> str:
        _validate_sha256(value, "sample_content_hash")
        return value

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return _utc_datetime(value, "created_at")

    @model_validator(mode="after")
    def validate_unique_members(self) -> Self:
        _validate_unique_label_members(self.labels, "taxonomy annotation batch")
        return self


class ValidatedTaxonomyAnnotationBatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: Literal["taxonomy-manual-annotation-v1"] = ANNOTATION_SPEC_VERSION
    annotation_contract_version: Literal["phase3-draft-v1"] = ANNOTATION_CONTRACT_VERSION
    annotation_contract_content_hash: str = ANNOTATION_CONTRACT_V1_CONTENT_HASH
    label_registry_version: Literal[1] = LABEL_REGISTRY_VERSION
    label_registry_content_hash: str = TAXONOMY_LABEL_REGISTRY_V1_CONTENT_HASH
    batch_id: str
    annotator_id: str
    sample_id: str
    sample_content_hash: str
    created_at: datetime
    labels: tuple[TaxonomyManualLabel, ...] = Field(min_length=100, max_length=200)
    annotation_batch_hash: str

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return _utc_datetime(value, "created_at")

    @field_validator(
        "annotation_contract_content_hash",
        "label_registry_content_hash",
        "sample_content_hash",
        "annotation_batch_hash",
    )
    @classmethod
    def validate_hash(cls, value: str) -> str:
        _validate_sha256(value, "validated annotation hash")
        return value


class TaxonomyGoldSetDeclaration(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: Literal["taxonomy-gold-set-v1"] = GOLD_SET_SPEC_VERSION
    annotation_contract_version: Literal["phase3-draft-v1"] = ANNOTATION_CONTRACT_VERSION
    label_registry_version: Literal[1] = LABEL_REGISTRY_VERSION
    gold_set_id: str
    sample_id: str
    sample_content_hash: str
    adjudicator_id: str
    adjudicated_at: datetime
    source_annotation_batch_hashes: tuple[str, ...] = Field(min_length=1)
    labels: tuple[TaxonomyManualLabel, ...] = Field(min_length=100, max_length=200)

    @field_validator("gold_set_id", "sample_id", "adjudicator_id")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        return _trimmed_identifier(value, "taxonomy gold-set identifier")

    @field_validator("sample_content_hash")
    @classmethod
    def validate_sample_hash(cls, value: str) -> str:
        _validate_sha256(value, "sample_content_hash")
        return value

    @field_validator("adjudicated_at")
    @classmethod
    def validate_adjudicated_at(cls, value: datetime) -> datetime:
        return _utc_datetime(value, "adjudicated_at")

    @field_validator("source_annotation_batch_hashes")
    @classmethod
    def validate_source_hashes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("gold set source annotation batch hashes must be unique")
        for value in values:
            _validate_sha256(value, "source annotation batch hash")
        return values

    @model_validator(mode="after")
    def validate_unique_members(self) -> Self:
        _validate_unique_label_members(self.labels, "taxonomy gold set")
        return self


class TaxonomyGoldSetSourceBatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    batch_id: str
    annotator_id: str
    annotation_batch_hash: str

    @field_validator("batch_id", "annotator_id")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        return _trimmed_identifier(value, "taxonomy gold-set source identifier")

    @field_validator("annotation_batch_hash")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        _validate_sha256(value, "annotation_batch_hash")
        return value


class TaxonomyGoldSetReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: Literal["taxonomy-gold-set-v1"] = GOLD_SET_SPEC_VERSION
    annotation_spec_version: Literal["taxonomy-manual-annotation-v1"] = ANNOTATION_SPEC_VERSION
    annotation_contract_version: Literal["phase3-draft-v1"] = ANNOTATION_CONTRACT_VERSION
    annotation_contract_content_hash: str = ANNOTATION_CONTRACT_V1_CONTENT_HASH
    label_registry_version: Literal[1] = LABEL_REGISTRY_VERSION
    label_registry_content_hash: str = TAXONOMY_LABEL_REGISTRY_V1_CONTENT_HASH
    gold_set_id: str
    sample_id: str
    sample_content_hash: str
    adjudicator_id: str
    adjudicated_at: datetime
    source_batches: tuple[TaxonomyGoldSetSourceBatch, ...] = Field(min_length=1)
    labels: tuple[TaxonomyManualLabel, ...] = Field(min_length=100, max_length=200)
    gold_set_content_hash: str

    @field_validator("gold_set_id", "sample_id", "adjudicator_id")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        return _trimmed_identifier(value, "taxonomy gold-set report identifier")

    @field_validator("adjudicated_at")
    @classmethod
    def validate_adjudicated_at(cls, value: datetime) -> datetime:
        return _utc_datetime(value, "adjudicated_at")

    @field_validator(
        "annotation_contract_content_hash",
        "label_registry_content_hash",
        "sample_content_hash",
        "gold_set_content_hash",
    )
    @classmethod
    def validate_hash(cls, value: str) -> str:
        _validate_sha256(value, "taxonomy gold-set report hash")
        return value


def validate_taxonomy_annotation_batch(
    sample: TaxonomyDiversitySampleReport,
    batch: TaxonomyAnnotationBatch,
) -> ValidatedTaxonomyAnnotationBatch:
    """Validate one independent manual annotation batch against an exact sample artifact."""

    sample = TaxonomyDiversitySampleReport.model_validate(sample.model_dump(mode="python"))
    batch = TaxonomyAnnotationBatch.model_validate(batch.model_dump(mode="python"))
    _validate_annotation_contract()
    _validate_sample_shape(sample)
    _validate_sample_binding(
        sample=sample,
        sample_id=batch.sample_id,
        sample_content_hash=batch.sample_content_hash,
        labels=batch.labels,
    )
    batch_hash = _content_hash(_annotation_batch_payload(batch))
    return ValidatedTaxonomyAnnotationBatch(
        batch_id=batch.batch_id,
        annotator_id=batch.annotator_id,
        sample_id=batch.sample_id,
        sample_content_hash=batch.sample_content_hash,
        created_at=batch.created_at,
        labels=batch.labels,
        annotation_batch_hash=batch_hash,
    )


def build_taxonomy_gold_set(
    sample: TaxonomyDiversitySampleReport,
    declaration: TaxonomyGoldSetDeclaration,
    annotation_batches: tuple[TaxonomyAnnotationBatch, ...],
) -> TaxonomyGoldSetReport:
    """Build one adjudicated gold set from explicit validated source annotation batches."""

    sample = TaxonomyDiversitySampleReport.model_validate(sample.model_dump(mode="python"))
    declaration = TaxonomyGoldSetDeclaration.model_validate(
        declaration.model_dump(mode="python")
    )
    _validate_annotation_contract()
    _validate_sample_shape(sample)
    _validate_sample_binding(
        sample=sample,
        sample_id=declaration.sample_id,
        sample_content_hash=declaration.sample_content_hash,
        labels=declaration.labels,
    )

    validated = tuple(
        validate_taxonomy_annotation_batch(sample, batch) for batch in annotation_batches
    )
    if not validated:
        raise TaxonomyGoldSetError("gold set requires at least one source annotation batch")
    batch_ids = tuple(batch.batch_id for batch in validated)
    if len(batch_ids) != len(set(batch_ids)):
        raise TaxonomyGoldSetError("gold set source annotation batch IDs must be unique")
    annotator_ids = tuple(batch.annotator_id for batch in validated)
    if len(annotator_ids) != len(set(annotator_ids)):
        raise TaxonomyGoldSetError("gold set source annotation batches require unique annotators")
    validated_hashes = tuple(batch.annotation_batch_hash for batch in validated)
    if set(validated_hashes) != set(declaration.source_annotation_batch_hashes):
        raise TaxonomyGoldSetError(
            "gold set source_annotation_batch_hashes must exactly match supplied validated batches"
        )
    by_hash = {batch.annotation_batch_hash: batch for batch in validated}
    ordered_batches = tuple(
        by_hash[batch_hash] for batch_hash in declaration.source_annotation_batch_hashes
    )
    source_batches = tuple(
        TaxonomyGoldSetSourceBatch(
            batch_id=batch.batch_id,
            annotator_id=batch.annotator_id,
            annotation_batch_hash=batch.annotation_batch_hash,
        )
        for batch in ordered_batches
    )
    gold_hash = _content_hash(
        _gold_set_payload(
            gold_set_id=declaration.gold_set_id,
            sample_id=declaration.sample_id,
            sample_content_hash=declaration.sample_content_hash,
            adjudicator_id=declaration.adjudicator_id,
            adjudicated_at=declaration.adjudicated_at,
            source_batches=source_batches,
            labels=declaration.labels,
        )
    )
    return TaxonomyGoldSetReport(
        gold_set_id=declaration.gold_set_id,
        sample_id=declaration.sample_id,
        sample_content_hash=declaration.sample_content_hash,
        adjudicator_id=declaration.adjudicator_id,
        adjudicated_at=declaration.adjudicated_at,
        source_batches=source_batches,
        labels=declaration.labels,
        gold_set_content_hash=gold_hash,
    )


def validate_taxonomy_gold_set_report(
    sample: TaxonomyDiversitySampleReport,
    report: TaxonomyGoldSetReport,
) -> TaxonomyGoldSetReport:
    """Revalidate a persisted gold-set artifact against its exact sample and frozen contract."""

    sample = TaxonomyDiversitySampleReport.model_validate(sample.model_dump(mode="python"))
    report = TaxonomyGoldSetReport.model_validate(report.model_dump(mode="python"))
    _validate_annotation_contract()
    _validate_sample_shape(sample)
    _validate_sample_binding(
        sample=sample,
        sample_id=report.sample_id,
        sample_content_hash=report.sample_content_hash,
        labels=report.labels,
    )
    if report.annotation_contract_content_hash != ANNOTATION_CONTRACT_V1_CONTENT_HASH:
        raise TaxonomyGoldSetError("gold set annotation-contract content hash does not match v1")
    if report.label_registry_content_hash != TAXONOMY_LABEL_REGISTRY_V1_CONTENT_HASH:
        raise TaxonomyGoldSetError("gold set label-registry content hash does not match v1")
    _validate_source_batch_refs(report.source_batches)
    expected_hash = _content_hash(
        _gold_set_payload(
            gold_set_id=report.gold_set_id,
            sample_id=report.sample_id,
            sample_content_hash=report.sample_content_hash,
            adjudicator_id=report.adjudicator_id,
            adjudicated_at=report.adjudicated_at,
            source_batches=report.source_batches,
            labels=report.labels,
        )
    )
    if report.gold_set_content_hash != expected_hash:
        raise TaxonomyGoldSetError("gold set content hash does not match report content")
    return report


def taxonomy_annotation_contract_content_hash() -> str:
    payload = {
        "annotation_contract_version": ANNOTATION_CONTRACT_VERSION,
        "label_fields": list(_MANUAL_LABEL_FIELDS),
        "primary_archetypes": [item.value for item in PrimaryGameplayArchetype],
        "controlled_dimensions": [item.value for item in _CONTROLLED_DIMENSIONS],
        "confidence_values": [item.value for item in TaxonomyAnnotationConfidence],
        "rationale_required_primary_states": [
            item.value for item in _RATIONALE_REQUIRED_PRIMARY_STATES
        ],
        "exclusive_meta_labels": list(_EXCLUSIVE_META_LABELS),
        "label_registry_version": LABEL_REGISTRY_VERSION,
        "label_registry_content_hash": TAXONOMY_LABEL_REGISTRY_V1_CONTENT_HASH,
    }
    return _content_hash(payload)


def _validate_annotation_contract() -> None:
    if taxonomy_annotation_contract_content_hash() != ANNOTATION_CONTRACT_V1_CONTENT_HASH:
        raise TaxonomyGoldSetError(
            "taxonomy annotation contract changed without a new contract version/content identity"
        )


def _validate_sample_shape(sample: TaxonomyDiversitySampleReport) -> None:
    if not 100 <= len(sample.selected) <= 200:
        raise TaxonomyGoldSetError(
            "manual gold-set tooling requires a real 100-200 member sample"
        )
    if len(sample.selected) != sample.target_size:
        raise TaxonomyGoldSetError("taxonomy sample selected membership does not match target_size")
    if sample.candidate_pool_size < len(sample.selected):
        raise TaxonomyGoldSetError(
            "taxonomy sample candidate pool is smaller than selected membership"
        )
    if (
        sample.parser_name != _SAMPLE_PARSER_NAME
        or sample.parser_version != _SAMPLE_PARSER_VERSION
    ):
        raise TaxonomyGoldSetError("manual gold-set tooling requires the frozen sampling parser")
    if sample.max_per_developer != _SAMPLE_MAX_PER_DEVELOPER:
        raise TaxonomyGoldSetError(
            "manual gold-set tooling requires the frozen sampling developer cap"
        )
    input_run_ids = sample.input_run_ids
    if any(not run_id or run_id != run_id.strip() for run_id in input_run_ids):
        raise TaxonomyGoldSetError("taxonomy sample input run IDs must be nonblank and trimmed")
    if len(input_run_ids) != len(set(input_run_ids)):
        raise TaxonomyGoldSetError("taxonomy sample input run IDs must be unique")
    _validate_sha256(sample.sample_content_hash, "taxonomy sample content hash")
    expected_hash = _taxonomy_sample_content_hash(sample)
    if sample.sample_content_hash != expected_hash:
        raise TaxonomyGoldSetError("taxonomy sample content hash does not match report content")
    ordinals = tuple(member.ordinal for member in sample.selected)
    if ordinals != tuple(range(len(sample.selected))):
        raise TaxonomyGoldSetError("taxonomy sample member ordinals are not contiguous from zero")


def _validate_sample_binding(
    *,
    sample: TaxonomyDiversitySampleReport,
    sample_id: str,
    sample_content_hash: str,
    labels: tuple[TaxonomyManualLabel, ...],
) -> None:
    if sample_id != sample.sample_id or sample_content_hash != sample.sample_content_hash:
        raise TaxonomyGoldSetError(
            "manual labels do not reference the exact taxonomy sample identity"
        )
    expected_ids = tuple(member.platform_listing_id for member in sample.selected)
    actual_ids = tuple(label.platform_listing_id for label in labels)
    if actual_ids != expected_ids:
        raise TaxonomyGoldSetError(
            "manual labels must cover every taxonomy sample member exactly in sample ordinal order"
        )


def _validate_source_batch_refs(source_batches: tuple[TaxonomyGoldSetSourceBatch, ...]) -> None:
    batch_ids = tuple(batch.batch_id for batch in source_batches)
    annotator_ids = tuple(batch.annotator_id for batch in source_batches)
    hashes = tuple(batch.annotation_batch_hash for batch in source_batches)
    if len(batch_ids) != len(set(batch_ids)):
        raise TaxonomyGoldSetError("gold set source batch IDs must be unique")
    if len(annotator_ids) != len(set(annotator_ids)):
        raise TaxonomyGoldSetError("gold set source annotators must be unique")
    if len(hashes) != len(set(hashes)):
        raise TaxonomyGoldSetError("gold set source batch hashes must be unique")


def _annotation_batch_payload(batch: TaxonomyAnnotationBatch) -> dict[str, object]:
    return {
        "spec_version": batch.spec_version,
        "annotation_contract_version": batch.annotation_contract_version,
        "annotation_contract_content_hash": ANNOTATION_CONTRACT_V1_CONTENT_HASH,
        "label_registry_version": batch.label_registry_version,
        "label_registry_content_hash": TAXONOMY_LABEL_REGISTRY_V1_CONTENT_HASH,
        "batch_id": batch.batch_id,
        "annotator_id": batch.annotator_id,
        "sample_id": batch.sample_id,
        "sample_content_hash": batch.sample_content_hash,
        "created_at": batch.created_at.isoformat(),
        "labels": [label.model_dump(mode="json") for label in batch.labels],
    }


def _gold_set_payload(
    *,
    gold_set_id: str,
    sample_id: str,
    sample_content_hash: str,
    adjudicator_id: str,
    adjudicated_at: datetime,
    source_batches: tuple[TaxonomyGoldSetSourceBatch, ...],
    labels: tuple[TaxonomyManualLabel, ...],
) -> dict[str, object]:
    return {
        "spec_version": GOLD_SET_SPEC_VERSION,
        "annotation_spec_version": ANNOTATION_SPEC_VERSION,
        "annotation_contract_version": ANNOTATION_CONTRACT_VERSION,
        "annotation_contract_content_hash": ANNOTATION_CONTRACT_V1_CONTENT_HASH,
        "label_registry_version": LABEL_REGISTRY_VERSION,
        "label_registry_content_hash": TAXONOMY_LABEL_REGISTRY_V1_CONTENT_HASH,
        "gold_set_id": gold_set_id,
        "sample_id": sample_id,
        "sample_content_hash": sample_content_hash,
        "adjudicator_id": adjudicator_id,
        "adjudicated_at": adjudicated_at.isoformat(),
        "source_batches": [batch.model_dump(mode="json") for batch in source_batches],
        "labels": [label.model_dump(mode="json") for label in labels],
    }


def _taxonomy_sample_content_hash(sample: TaxonomyDiversitySampleReport) -> str:
    payload = {
        "spec_version": sample.spec_version,
        "sample_id": sample.sample_id,
        "target_size": sample.target_size,
        "max_per_developer": sample.max_per_developer,
        "input_run_ids": sample.input_run_ids,
        "selected": [member.model_dump(mode="json") for member in sample.selected],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _trimmed_identifier(value: str, field_name: str) -> str:
    if not value or value != value.strip():
        raise ValueError(f"{field_name} must be nonblank and trimmed")
    return value


def _validate_unique_label_members(
    labels: tuple[TaxonomyManualLabel, ...],
    artifact_name: str,
) -> None:
    listing_ids = tuple(label.platform_listing_id for label in labels)
    if len(listing_ids) != len(set(listing_ids)):
        raise ValueError(f"{artifact_name} cannot contain duplicate listing IDs")


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


_validate_annotation_contract()
