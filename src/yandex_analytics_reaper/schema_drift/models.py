from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator


class JsonValueType(StrEnum):
    NULL = "null"
    BOOLEAN = "boolean"
    INTEGER = "integer"
    NUMBER = "number"
    STRING = "string"
    OBJECT = "object"
    ARRAY = "array"


class SchemaProfileStatus(StrEnum):
    PROFILED = "profiled"
    PARSE_FAILED = "parse_failed"
    NOT_PROFILED = "not_profiled"


class DriftKind(StrEnum):
    NEW_FIELD = "new_field"
    REMOVED_FIELD = "removed_field"
    TYPE_CHANGED = "type_changed"
    MISSINGNESS_CHANGED = "missingness_changed"
    REQUIRED_FIELD_MISSING = "required_field_missing"
    CONTRACT_TYPE_MISMATCH = "contract_type_mismatch"
    ROOT_TYPE_MISMATCH = "root_type_mismatch"
    RAW_PARSE_FAILURE = "raw_parse_failure"
    PARSER_FAILURE = "parser_failure"


class DriftSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    BREAKING = "breaking"


class FieldExpectation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str
    allowed_types: tuple[JsonValueType, ...]
    required: bool = False
    minimum_presence_ratio: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped.startswith("$"):
            raise ValueError("schema expectation path must start with '$'")
        return stripped

    @field_validator("allowed_types")
    @classmethod
    def require_allowed_types(
        cls,
        value: tuple[JsonValueType, ...],
    ) -> tuple[JsonValueType, ...]:
        if not value:
            raise ValueError("schema expectation must allow at least one JSON type")
        if len(set(value)) != len(value):
            raise ValueError("schema expectation allowed_types cannot contain duplicates")
        return value


class SchemaContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    contract_id: str
    request_key: str
    allowed_root_types: tuple[JsonValueType, ...] = (JsonValueType.OBJECT,)
    fields: tuple[FieldExpectation, ...] = ()

    @field_validator("contract_id", "request_key")
    @classmethod
    def require_non_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("schema contract identifiers cannot be blank")
        return stripped

    @field_validator("allowed_root_types")
    @classmethod
    def require_root_types(
        cls,
        value: tuple[JsonValueType, ...],
    ) -> tuple[JsonValueType, ...]:
        if not value:
            raise ValueError("schema contract must allow at least one root type")
        if len(set(value)) != len(value):
            raise ValueError("schema contract root types cannot contain duplicates")
        return value

    @model_validator(mode="after")
    def validate_unique_field_paths(self) -> Self:
        paths = [field.path for field in self.fields]
        if len(paths) != len(set(paths)):
            raise ValueError("schema contract cannot define the same field path twice")
        return self


class FieldProfile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str
    value_types: tuple[JsonValueType, ...]
    present_count: int = Field(ge=0)
    parent_count: int = Field(ge=0)
    presence_ratio: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        if self.present_count > self.parent_count:
            raise ValueError("present_count cannot exceed parent_count")
        if self.parent_count == 0 and self.presence_ratio != 0.0:
            raise ValueError("presence_ratio must be zero when parent_count is zero")
        if self.parent_count > 0:
            expected = self.present_count / self.parent_count
            if abs(self.presence_ratio - expected) > 1e-12:
                raise ValueError("presence_ratio must equal present_count / parent_count")
        if not self.path.startswith("$"):
            raise ValueError("profile field path must start with '$'")
        if not self.value_types:
            raise ValueError("profiled field must contain at least one observed JSON type")
        return self


class SchemaProfile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    raw_snapshot_id: str
    source_id: str
    request_key: str
    retrieved_at: AwareDatetime
    content_hash: str
    schema_hash: str | None = None
    status: SchemaProfileStatus
    root_type: JsonValueType | None = None
    fields: tuple[FieldProfile, ...] = ()
    error: str | None = None

    @field_validator("raw_snapshot_id", "source_id", "request_key")
    @classmethod
    def require_profile_identity(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("schema profile identity fields cannot be blank")
        return stripped

    @field_validator("content_hash")
    @classmethod
    def validate_content_hash(cls, value: str) -> str:
        normalized = value.strip().lower()
        if len(normalized) != 64:
            raise ValueError("content_hash must be a SHA-256 hex digest")
        try:
            int(normalized, 16)
        except ValueError as exc:
            raise ValueError("content_hash must be a SHA-256 hex digest") from exc
        return normalized

    @model_validator(mode="after")
    def validate_status_payload(self) -> Self:
        if self.status is SchemaProfileStatus.PROFILED:
            if self.root_type is None:
                raise ValueError("profiled schema requires root_type")
            if self.error is not None:
                raise ValueError("profiled schema cannot carry an error")
        elif self.status is SchemaProfileStatus.PARSE_FAILED:
            if self.root_type is not None or self.fields:
                raise ValueError("parse-failed schema cannot carry a structural profile")
            if self.error is None or not self.error.strip():
                raise ValueError("parse-failed schema requires an error")
        elif self.status is SchemaProfileStatus.NOT_PROFILED:
            if self.root_type is not None or self.fields or self.error is not None:
                raise ValueError("not-profiled schema cannot carry profile/error payload")
        return self


class DriftEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str
    raw_snapshot_id: str
    kind: DriftKind
    severity: DriftSeverity
    field_path: str | None = None
    previous_types: tuple[JsonValueType, ...] = ()
    current_types: tuple[JsonValueType, ...] = ()
    previous_presence_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    current_presence_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    details: dict[str, str] = Field(default_factory=dict)
    message: str

    @field_validator("event_id", "raw_snapshot_id", "message")
    @classmethod
    def require_event_identity(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("schema drift event identity/message cannot be blank")
        return stripped

    @field_validator("field_path")
    @classmethod
    def validate_optional_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped.startswith("$"):
            raise ValueError("drift field_path must start with '$'")
        return stripped


class SchemaAnalysis(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    analysis_id: str
    analyzer_version: str
    contract_id: str
    comparison_scope_id: str
    profile: SchemaProfile
    events: tuple[DriftEvent, ...] = ()

    @field_validator(
        "analysis_id",
        "analyzer_version",
        "contract_id",
        "comparison_scope_id",
    )
    @classmethod
    def require_analysis_identity(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("schema analysis identity fields cannot be blank")
        return stripped

    @model_validator(mode="after")
    def validate_events(self) -> Self:
        event_ids = [event.event_id for event in self.events]
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("schema analysis cannot contain duplicate event ids")
        if any(event.raw_snapshot_id != self.profile.raw_snapshot_id for event in self.events):
            raise ValueError("schema analysis events must reference the analyzed raw snapshot")
        return self
