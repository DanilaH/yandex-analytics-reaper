from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


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


class SchemaContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    contract_id: str
    request_key: str
    allowed_root_types: tuple[JsonValueType, ...] = (JsonValueType.OBJECT,)
    fields: tuple[FieldExpectation, ...] = ()


class FieldProfile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str
    value_types: tuple[JsonValueType, ...]
    present_count: int = Field(ge=0)
    parent_count: int = Field(ge=0)
    presence_ratio: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_counts(self) -> FieldProfile:
        if self.present_count > self.parent_count:
            raise ValueError("present_count cannot exceed parent_count")
        return self


class SchemaProfile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    raw_snapshot_id: str
    source_id: str
    request_key: str
    retrieved_at: datetime
    schema_hash: str | None = None
    status: SchemaProfileStatus
    root_type: JsonValueType | None = None
    fields: tuple[FieldProfile, ...] = ()
    error: str | None = None


class DriftEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str
    raw_snapshot_id: str
    kind: DriftKind
    severity: DriftSeverity
    field_path: str | None = None
    previous_types: tuple[JsonValueType, ...] = ()
    current_types: tuple[JsonValueType, ...] = ()
    previous_presence_ratio: float | None = None
    current_presence_ratio: float | None = None
    details: dict[str, str] = Field(default_factory=dict)
    message: str
