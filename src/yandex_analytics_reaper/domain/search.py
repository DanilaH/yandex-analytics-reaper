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


class QueryVariantKind(StrEnum):
    SEED = "seed"
    SYNONYM = "synonym"
    SPELLING_VARIANT = "spelling_variant"
    TRANSLITERATION = "transliteration"
    OTHER = "other"


class QueryFamilyMember(BaseModel):
    """One exact outgoing query string in a frozen query-family version."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    query_text: str
    kind: QueryVariantKind

    @field_validator("query_text")
    @classmethod
    def validate_query_text(cls, value: str) -> str:
        if not value:
            raise ValueError("query_text cannot be blank")
        if value != value.strip():
            raise ValueError("query_text must already be trimmed")
        return value


class QueryFamilyVersion(BaseModel):
    """Immutable versioned declaration of exact search queries for one intent."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    family_id: str
    version: int = Field(ge=1)
    label: str
    source_id: str
    language: str
    created_at: AwareDatetime
    members: tuple[QueryFamilyMember, ...]

    @field_validator("family_id", "label", "source_id", "language")
    @classmethod
    def validate_trimmed_non_blank(cls, value: str) -> str:
        if not value:
            raise ValueError("query-family text fields cannot be blank")
        if value != value.strip():
            raise ValueError("query-family text fields must already be trimmed")
        return value

    @model_validator(mode="after")
    def validate_members(self) -> Self:
        if not self.members:
            raise ValueError("query family must contain at least one member")
        seed_indexes = [
            index
            for index, member in enumerate(self.members)
            if member.kind is QueryVariantKind.SEED
        ]
        if seed_indexes != [0]:
            raise ValueError("query family must contain exactly one seed and it must be member 0")
        query_texts = [member.query_text for member in self.members]
        if len(set(query_texts)) != len(query_texts):
            raise ValueError("query family query_text values must be unique")
        return self
