from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator


class ProbeKind(StrEnum):
    RECOMMENDATION_FEED = "recommendation_feed"
    SEARCH = "search"


class ProbeRunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class ProbeRun(BaseModel):
    """One logical paginated source observation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    source_id: str
    request_key: str
    kind: ProbeKind
    context_id: str
    query_text: str | None = None
    requested_page_limit: int = Field(ge=1)
    started_at: AwareDatetime
    completed_at: AwareDatetime | None = None
    status: ProbeRunStatus = ProbeRunStatus.RUNNING
    error: str | None = None

    @field_validator("id", "source_id", "request_key", "context_id")
    @classmethod
    def require_identity(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("probe run identity fields cannot be blank")
        return stripped

    @field_validator("query_text")
    @classmethod
    def normalize_query(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("probe query_text cannot be blank")
        return stripped

    @model_validator(mode="after")
    def validate_run_semantics(self) -> Self:
        if self.kind is ProbeKind.SEARCH and self.query_text is None:
            raise ValueError("search probe run requires query_text")
        if self.kind is ProbeKind.RECOMMENDATION_FEED and self.query_text is not None:
            raise ValueError("feed probe run cannot carry query_text")
        if self.status is ProbeRunStatus.RUNNING:
            if self.completed_at is not None or self.error is not None:
                raise ValueError("running probe cannot have completed_at/error")
        else:
            if self.completed_at is None:
                raise ValueError("terminal probe run requires completed_at")
            if self.completed_at < self.started_at:
                raise ValueError("probe completed_at cannot be earlier than started_at")
            if self.status is ProbeRunStatus.COMPLETED and self.error is not None:
                raise ValueError("completed probe run cannot carry an error")
            if self.status in {ProbeRunStatus.PARTIAL, ProbeRunStatus.FAILED}:
                if self.error is None or not self.error.strip():
                    raise ValueError("partial/failed probe run requires an error")
        return self


class ProbePage(BaseModel):
    """One ordered raw page belonging to a logical probe run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    page_index: int = Field(ge=0)
    raw_snapshot_id: str
    retrieved_at: AwareDatetime
    request_page_id: str | None = None
    request_rtx_reqid: str | None = None
    response_next_page_id: str | None = None
    response_rtx_reqid: str | None = None
    has_next_page: bool

    @field_validator("run_id", "raw_snapshot_id")
    @classmethod
    def require_page_identity(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("probe page identity fields cannot be blank")
        return stripped

    @field_validator(
        "request_page_id",
        "request_rtx_reqid",
        "response_next_page_id",
        "response_rtx_reqid",
    )
    @classmethod
    def normalize_optional_token(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @model_validator(mode="after")
    def validate_first_page_cursor(self) -> Self:
        if self.page_index == 0 and (
            self.request_page_id is not None or self.request_rtx_reqid is not None
        ):
            raise ValueError("first probe page cannot carry pagination request tokens")
        return self
