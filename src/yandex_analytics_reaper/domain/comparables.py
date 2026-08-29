from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class ComparableSetConstructionMethod(StrEnum):
    YANDEX_SEARCH_UNION_V1 = "yandex_search_union_v1"


class ComparableSetRun(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    query_ordinal: int = Field(ge=0)
    query_text: str
    probe_run_id: str

    @field_validator("query_text", "probe_run_id")
    @classmethod
    def validate_trimmed_non_blank(cls, value: str) -> str:
        if not value:
            raise ValueError("comparable-set run text fields cannot be blank")
        if value != value.strip():
            raise ValueError("comparable-set run text fields must already be trimmed")
        return value


class ComparableSetMember(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ordinal: int = Field(ge=0)
    platform_listing_id: str

    @field_validator("platform_listing_id")
    @classmethod
    def validate_listing_id(cls, value: str) -> str:
        if not value or value != value.strip():
            raise ValueError("platform_listing_id must be non-blank and trimmed")
        return value


class ComparableSetMemberEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    platform_listing_id: str
    probe_run_id: str
    raw_snapshot_id: str
    page_index: int = Field(ge=0)
    source_object_path: str

    @field_validator(
        "platform_listing_id",
        "probe_run_id",
        "raw_snapshot_id",
        "source_object_path",
    )
    @classmethod
    def validate_evidence_identity(cls, value: str) -> str:
        if not value or value != value.strip():
            raise ValueError("comparable-set evidence identity must be non-blank and trimmed")
        return value


class ComparableSetVersion(BaseModel):
    """Immutable provisional peer-set version with exact search/raw provenance."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    set_id: str
    version: int = Field(ge=1)
    construction_method: ComparableSetConstructionMethod
    query_family_id: str
    query_family_version: int = Field(ge=1)
    source_id: str
    language: str
    context_id: str
    requested_page_limit: int = Field(ge=1)
    parser_name: str
    parser_version: str
    observed_from: AwareDatetime
    observed_to: AwareDatetime
    created_at: AwareDatetime
    runs: tuple[ComparableSetRun, ...]
    members: tuple[ComparableSetMember, ...]
    evidence: tuple[ComparableSetMemberEvidence, ...]

    @field_validator(
        "set_id",
        "query_family_id",
        "source_id",
        "language",
        "context_id",
        "parser_name",
        "parser_version",
    )
    @classmethod
    def validate_trimmed_non_blank(cls, value: str) -> str:
        if not value or value != value.strip():
            raise ValueError("comparable-set text fields must be non-blank and trimmed")
        return value

    @model_validator(mode="after")
    def validate_structure(self) -> Self:
        if self.observed_to < self.observed_from:
            raise ValueError("comparable-set observed_to cannot precede observed_from")
        if self.created_at < self.observed_to:
            raise ValueError("comparable-set created_at cannot precede observed_to")
        if not self.runs:
            raise ValueError("comparable set must reference at least one search run")

        query_ordinals = tuple(run.query_ordinal for run in self.runs)
        if query_ordinals != tuple(range(len(self.runs))):
            raise ValueError("comparable-set query ordinals must be contiguous from zero")
        run_ids = [run.probe_run_id for run in self.runs]
        if len(set(run_ids)) != len(run_ids):
            raise ValueError("comparable-set probe_run_id values must be unique")
        query_texts = [run.query_text for run in self.runs]
        if len(set(query_texts)) != len(query_texts):
            raise ValueError("comparable-set query_text values must be unique")

        member_ordinals = tuple(member.ordinal for member in self.members)
        if member_ordinals != tuple(range(len(self.members))):
            raise ValueError("comparable-set member ordinals must be contiguous from zero")
        listing_ids = [member.platform_listing_id for member in self.members]
        if len(set(listing_ids)) != len(listing_ids):
            raise ValueError("comparable-set members must be unique by platform listing ID")

        member_ids = set(listing_ids)
        evidence_ids = {item.platform_listing_id for item in self.evidence}
        if evidence_ids != member_ids:
            raise ValueError("every comparable-set member must have evidence and no orphan evidence")
        valid_run_ids = set(run_ids)
        if any(item.probe_run_id not in valid_run_ids for item in self.evidence):
            raise ValueError("comparable-set evidence references an undeclared probe run")

        evidence_identity = [
            (
                item.platform_listing_id,
                item.probe_run_id,
                item.raw_snapshot_id,
                item.page_index,
                item.source_object_path,
            )
            for item in self.evidence
        ]
        if len(set(evidence_identity)) != len(evidence_identity):
            raise ValueError("comparable-set evidence rows must be unique")
        return self
