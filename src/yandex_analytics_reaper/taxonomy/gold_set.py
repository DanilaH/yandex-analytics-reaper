from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .models import PrimaryGameplayArchetype
from .registries import (
    ControlledLabelDimension,
    TAXONOMY_LABEL_REGISTRY_V1_CONTENT_HASH,
    get_taxonomy_label_registry,
    normalize_taxonomy_label,
)
from .sampling import TaxonomyDiversitySampleReport

ANNOTATION_SPEC_VERSION = "taxonomy-manual-annotation-v1"
GOLD_SET_SPEC_VERSION = "taxonomy-gold-set-v1"
ANNOTATION_CONTRACT_VERSION = "phase3-draft-v1"
LABEL_REGISTRY_VERSION: Literal[1] = 1


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
        if not value or value != value.strip():
            raise ValueError("taxonomy annotation listing ID must be nonblank and trimmed")
        return value

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
        if not value or value != value.strip():
            raise ValueError("taxonomy annotation rationale must be nonblank and trimmed")
        return value

    @model_validator(mode="after")
    def validate_semantics(self) -> Self:
        registry = get_taxonomy_label_registry(LABEL_REGISTRY_VERSION)
        registry.validate_membership(ControlledLabelDimension.MECHANICS, self.mechanics)
        registry.validate_membership(ControlledLabelDimension.OBJECTIVES, self.objectives)
        registry.validate_membership(ControlledLabelDimension.META_SYSTEMS, self.meta_systems)
        registry.validate_membership(ControlledLabelDimension.TONES, self.tones)
        if "none" in self.meta_systems and len(self.meta_systems) != 1:
            raise ValueError("meta_systems label 'none' cannot be combined with other labels")
        if self.primary_archetype in {
            PrimaryGameplayArchetype.UNKNOWN,
            PrimaryGameplayArchetype.OTHER,
        } and self.rationale is None:
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
        if not value or value != value.strip():
            raise ValueError("taxonomy annotation identifiers must be nonblank and trimmed")
        return value

    @field_validator("sample_content_hash")
    @classmethod
    def validate_sample_hash(cls, value: str) -> str:
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise ValueError("sample_content_hash must be 64 lowercase hexadecimal characters")
        return value

    @model_validator(mode="after")
    def validate_unique_members(self) -> Self:
        listing_ids = tuple(label.platform_listing_id for label in self.labels)
        if len(listing_ids) != len(set(listing_ids)):
            raise ValueError("taxonomy annotation batch cannot contain duplicate listing IDs")
        return self


class ValidatedTaxonomyAnnotationBatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: Literal["taxonomy-manual-annotation-v1"] = ANNOTATION_SPEC_VERSION
    annotation_contract_version: Literal["phase3-draft-v1"] = ANNOTATION_CONTRACT_VERSION
    label_registry_version: Literal[1] = LABEL_REGISTRY_VERSION
    label_registry_content_hash: str = TAXONOMY_LABEL_REGISTRY_V1_CONTENT_HASH
    batch_id: str
    annotator_id: str
    sample_id: str
    sample_content_hash: str
    created_at: datetime
    labels: tuple[TaxonomyManualLabel, ...]
    annotation_batch_hash: str


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
        if not value or value != value.strip():
            raise ValueError("taxonomy gold-set identifiers must be nonblank and trimmed")
        return value

    @field_validator("sample_content_hash")
    @classmethod
    def validate_sample_hash(cls, value: str) -> str:
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise ValueError("sample_content_hash must be 64 lowercase hexadecimal characters")
        return value

    @field_validator("source_annotation_batch_hashes")
    @classmethod
    def validate_source_hashes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("gold set source annotation batch hashes must be unique")
        for value in values:
            if len(value) != 64 or any(
                character not in "0123456789abcdef" for character in value
            ):
                raise ValueError(
                    "source annotation batch hashes must be 64 lowercase hexadecimal characters"
                )
        return values

    @model_validator(mode="after")
    def validate_unique_members(self) -> Self:
        listing_ids = tuple(label.platform_listing_id for label in self.labels)
        if len(listing_ids) != len(set(listing_ids)):
            raise ValueError("taxonomy gold set cannot contain duplicate listing IDs")
        return self


class TaxonomyGoldSetSourceBatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    batch_id: str
    annotator_id: str
    annotation_batch_hash: str


class TaxonomyGoldSetReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: Literal["taxonomy-gold-set-v1"] = GOLD_SET_SPEC_VERSION
    annotation_spec_version: Literal["taxonomy-manual-annotation-v1"] = ANNOTATION_SPEC_VERSION
    annotation_contract_version: Literal["phase3-draft-v1"] = ANNOTATION_CONTRACT_VERSION
    label_registry_version: Literal[1] = LABEL_REGISTRY_VERSION
    label_registry_content_hash: str = TAXONOMY_LABEL_REGISTRY_V1_CONTENT_HASH
    gold_set_id: str
    sample_id: str
    sample_content_hash: str
    adjudicator_id: str
    adjudicated_at: datetime
    source_batches: tuple[TaxonomyGoldSetSourceBatch, ...]
    labels: tuple[TaxonomyManualLabel, ...]
    gold_set_content_hash: str


def validate_taxonomy_annotation_batch(
    sample: TaxonomyDiversitySampleReport,
    batch: TaxonomyAnnotationBatch,
) -> ValidatedTaxonomyAnnotationBatch:
    """Validate one independent manual annotation batch against an exact sample artifact."""

    sample = TaxonomyDiversitySampleReport.model_validate(sample.model_dump(mode="python"))
    batch = TaxonomyAnnotationBatch.model_validate(batch.model_dump(mode="python"))
    _validate_sample_shape(sample)
    _validate_sample_binding(
        sample=sample,
        sample_id=batch.sample_id,
        sample_content_hash=batch.sample_content_hash,
        labels=batch.labels,
    )
    batch_hash = _content_hash(
        {
            "spec_version": batch.spec_version,
            "annotation_contract_version": batch.annotation_contract_version,
            "label_registry_version": batch.label_registry_version,
            "label_registry_content_hash": TAXONOMY_LABEL_REGISTRY_V1_CONTENT_HASH,
            "batch_id": batch.batch_id,
            "annotator_id": batch.annotator_id,
            "sample_id": batch.sample_id,
            "sample_content_hash": batch.sample_content_hash,
            "created_at": batch.created_at.isoformat(),
            "labels": [label.model_dump(mode="json") for label in batch.labels],
        }
    )
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
        {
            "spec_version": declaration.spec_version,
            "annotation_spec_version": ANNOTATION_SPEC_VERSION,
            "annotation_contract_version": declaration.annotation_contract_version,
            "label_registry_version": declaration.label_registry_version,
            "label_registry_content_hash": TAXONOMY_LABEL_REGISTRY_V1_CONTENT_HASH,
            "gold_set_id": declaration.gold_set_id,
            "sample_id": declaration.sample_id,
            "sample_content_hash": declaration.sample_content_hash,
            "adjudicator_id": declaration.adjudicator_id,
            "adjudicated_at": declaration.adjudicated_at.isoformat(),
            "source_batches": [batch.model_dump(mode="json") for batch in source_batches],
            "labels": [label.model_dump(mode="json") for label in declaration.labels],
        }
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


def _validate_sample_shape(sample: TaxonomyDiversitySampleReport) -> None:
    if not 100 <= len(sample.selected) <= 200:
        raise TaxonomyGoldSetError("manual gold-set tooling requires a real 100–200 member sample")
    if len(sample.selected) != sample.target_size:
        raise TaxonomyGoldSetError("taxonomy sample selected membership does not match target_size")
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
        raise TaxonomyGoldSetError("manual labels do not reference the exact taxonomy sample identity")
    expected_ids = tuple(member.platform_listing_id for member in sample.selected)
    actual_ids = tuple(label.platform_listing_id for label in labels)
    if actual_ids != expected_ids:
        raise TaxonomyGoldSetError(
            "manual labels must cover every taxonomy sample member exactly in sample ordinal order"
        )


def _content_hash(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
