from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict

from yandex_analytics_reaper.domain import (
    ProbeContext,
    ProbeKind,
    ProbePage,
    ProbeRun,
    ProbeRunStatus,
    SessionProfile,
)

from .sqlite import SQLiteDatabase


class ProbeRunRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run: ProbeRun
    context: ProbeContext
    pages: tuple[ProbePage, ...]


class ProbeRunStore(Protocol):
    def create_run(
        self,
        *,
        source_id: str,
        request_key: str,
        kind: ProbeKind,
        context: ProbeContext,
        requested_page_limit: int,
        started_at: AwareDatetime,
        query_text: str | None = None,
    ) -> ProbeRun: ...

    def append_page(self, page: ProbePage) -> ProbePage: ...

    def finish_run(
        self,
        run_id: str,
        *,
        status: ProbeRunStatus,
        completed_at: AwareDatetime,
        error: str | None = None,
        error_raw_snapshot_id: str | None = None,
    ) -> ProbeRun: ...

    def get_run(self, run_id: str) -> ProbeRunRecord | None: ...


class SQLiteProbeRunStore:
    """Operational persistence for contextual paginated collection runs."""

    def __init__(self, path: Path) -> None:
        self.database = SQLiteDatabase(path)

    @property
    def path(self) -> Path:
        return self.database.path

    def create_run(
        self,
        *,
        source_id: str,
        request_key: str,
        kind: ProbeKind,
        context: ProbeContext,
        requested_page_limit: int,
        started_at: AwareDatetime,
        query_text: str | None = None,
    ) -> ProbeRun:
        _require_aware(started_at, "started_at")
        context_id = _context_id(context)
        run = ProbeRun(
            id=f"probe:{uuid4().hex}",
            source_id=source_id,
            request_key=request_key,
            kind=kind,
            context_id=context_id,
            query_text=query_text,
            requested_page_limit=requested_page_limit,
            started_at=started_at,
        )
        with self.database.connect() as connection:
            self._persist_context(connection, context_id, context)
            connection.execute(
                """
                INSERT INTO probe_runs (
                    id,
                    source_id,
                    request_key,
                    probe_kind,
                    context_id,
                    query_text,
                    requested_page_limit,
                    started_at,
                    completed_at,
                    status,
                    error,
                    error_raw_snapshot_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, NULL, NULL)
                """,
                (
                    run.id,
                    run.source_id,
                    run.request_key,
                    run.kind.value,
                    run.context_id,
                    run.query_text,
                    run.requested_page_limit,
                    _timestamp(run.started_at),
                    run.status.value,
                ),
            )
        return run

    def append_page(self, page: ProbePage) -> ProbePage:
        _require_aware(page.retrieved_at, "page.retrieved_at")
        with self.database.connect() as connection:
            run = self._load_run(connection, page.run_id)
            if run is None:
                raise ValueError(f"probe run {page.run_id} does not exist")

            existing = self._load_page(connection, page.run_id, page.page_index)
            if existing is not None:
                if existing != page:
                    raise ValueError(
                        f"conflicting probe page {page.run_id}[{page.page_index}]"
                    )
                return existing

            if run.status is not ProbeRunStatus.RUNNING:
                raise ValueError("cannot append a page to a terminal probe run")
            if page.retrieved_at < run.started_at:
                raise ValueError("probe page cannot be retrieved before run start")

            row = connection.execute(
                "SELECT COUNT(*) AS count FROM probe_pages WHERE run_id = ?",
                (run.id,),
            ).fetchone()
            current_count = 0 if row is None else int(row["count"])
            if page.page_index != current_count:
                raise ValueError(
                    f"probe pages must be contiguous; expected index {current_count}"
                )
            if current_count >= run.requested_page_limit:
                raise ValueError("probe run already reached requested_page_limit")

            if current_count == 0:
                if page.request_page_id is not None or page.request_rtx_reqid is not None:
                    raise ValueError("first probe page cannot carry pagination request tokens")
            else:
                previous = self._load_page(connection, run.id, current_count - 1)
                if previous is None:
                    raise RuntimeError("contiguous probe page history is missing its previous page")
                if not previous.has_next_page:
                    raise ValueError("cannot append after source reported has_next_page=false")
                if (
                    previous.response_next_page_id is None
                    or previous.response_rtx_reqid is None
                ):
                    raise ValueError(
                        "cannot append after source omitted required continuation tokens"
                    )
                if previous.response_next_page_id != page.request_page_id:
                    raise ValueError("probe page_id does not continue previous page cursor")
                if previous.response_rtx_reqid != page.request_rtx_reqid:
                    raise ValueError("probe rtx_reqid does not continue previous page token")
                if page.retrieved_at < previous.retrieved_at:
                    raise ValueError("probe page retrieval time cannot move backwards")

            try:
                connection.execute(
                    """
                    INSERT INTO probe_pages (
                        run_id,
                        page_index,
                        source_id,
                        raw_snapshot_id,
                        retrieved_at,
                        request_page_id,
                        request_rtx_reqid,
                        response_next_page_id,
                        response_rtx_reqid,
                        has_next_page
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        page.run_id,
                        page.page_index,
                        run.source_id,
                        page.raw_snapshot_id,
                        _timestamp(page.retrieved_at),
                        page.request_page_id,
                        page.request_rtx_reqid,
                        page.response_next_page_id,
                        page.response_rtx_reqid,
                        int(page.has_next_page),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError(
                    f"raw snapshot {run.source_id}/{page.raw_snapshot_id} "
                    "is already assigned to a probe page"
                ) from exc
        return page

    def finish_run(
        self,
        run_id: str,
        *,
        status: ProbeRunStatus,
        completed_at: AwareDatetime,
        error: str | None = None,
        error_raw_snapshot_id: str | None = None,
    ) -> ProbeRun:
        _require_aware(completed_at, "completed_at")
        if status is ProbeRunStatus.RUNNING:
            raise ValueError("finish_run requires a terminal status")

        with self.database.connect() as connection:
            run = self._load_run(connection, run_id)
            if run is None:
                raise ValueError(f"probe run {run_id} does not exist")

            if run.status is not ProbeRunStatus.RUNNING:
                candidate = run.model_copy(
                    update={
                        "status": status,
                        "completed_at": completed_at,
                        "error": error,
                        "error_raw_snapshot_id": error_raw_snapshot_id,
                    }
                )
                candidate = ProbeRun.model_validate(candidate.model_dump())
                if candidate != run:
                    raise ValueError("probe run is already terminal with different state")
                return run

            pages = self._load_pages(connection, run_id)
            if completed_at < run.started_at:
                raise ValueError("probe completed_at cannot be earlier than started_at")
            if pages and completed_at < pages[-1].retrieved_at:
                raise ValueError("probe completed_at cannot be earlier than the last page")

            if status is ProbeRunStatus.COMPLETED:
                if not pages:
                    raise ValueError("completed probe run must contain at least one page")
                reached_limit = len(pages) == run.requested_page_limit
                source_exhausted = not pages[-1].has_next_page
                if not reached_limit and not source_exhausted:
                    raise ValueError(
                        "completed probe must reach requested_page_limit or source exhaustion"
                    )
            elif status is ProbeRunStatus.PARTIAL:
                if not pages:
                    raise ValueError("partial probe run must contain at least one page")
            elif status is ProbeRunStatus.FAILED and pages:
                raise ValueError("probe run with collected pages must use partial, not failed")

            updated = ProbeRun(
                id=run.id,
                source_id=run.source_id,
                request_key=run.request_key,
                kind=run.kind,
                context_id=run.context_id,
                query_text=run.query_text,
                requested_page_limit=run.requested_page_limit,
                started_at=run.started_at,
                completed_at=completed_at,
                status=status,
                error=error,
                error_raw_snapshot_id=error_raw_snapshot_id,
            )
            connection.execute(
                """
                UPDATE probe_runs
                SET completed_at = ?, status = ?, error = ?, error_raw_snapshot_id = ?
                WHERE id = ? AND status = ?
                """,
                (
                    _timestamp(completed_at),
                    status.value,
                    updated.error,
                    updated.error_raw_snapshot_id,
                    run.id,
                    ProbeRunStatus.RUNNING.value,
                ),
            )
            return updated

    def get_run(self, run_id: str) -> ProbeRunRecord | None:
        with self.database.connect() as connection:
            run = self._load_run(connection, run_id)
            if run is None:
                return None
            context = self._load_context(connection, run.context_id)
            if context is None:
                raise RuntimeError(f"probe context {run.context_id} is missing")
            pages = self._load_pages(connection, run.id)
        return ProbeRunRecord(run=run, context=context, pages=pages)

    @staticmethod
    def _persist_context(
        connection: sqlite3.Connection,
        context_id: str,
        context: ProbeContext,
    ) -> None:
        connection.execute(
            """
            INSERT OR IGNORE INTO probe_contexts (
                id,
                language,
                device_type,
                platform,
                country_observed,
                collector_region,
                session_profile,
                session_instance_id,
                cookie_state_hash,
                profile_age_days
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                context_id,
                context.language,
                context.device_type,
                context.platform,
                context.country_observed,
                context.collector_region,
                context.session_profile.value,
                context.session_instance_id,
                context.cookie_state_hash,
                context.profile_age_days,
            ),
        )
        stored = SQLiteProbeRunStore._load_context(connection, context_id)
        if stored != context:
            raise ValueError("probe context identity collision or conflicting stored context")

    @staticmethod
    def _load_context(
        connection: sqlite3.Connection,
        context_id: str,
    ) -> ProbeContext | None:
        row = connection.execute(
            "SELECT * FROM probe_contexts WHERE id = ?",
            (context_id,),
        ).fetchone()
        if row is None:
            return None
        return ProbeContext(
            language=str(row["language"]),
            device_type=str(row["device_type"]),
            platform=str(row["platform"]),
            country_observed=_optional_str(row["country_observed"]),
            collector_region=_optional_str(row["collector_region"]),
            session_profile=SessionProfile(str(row["session_profile"])),
            session_instance_id=_optional_str(row["session_instance_id"]),
            cookie_state_hash=_optional_str(row["cookie_state_hash"]),
            profile_age_days=(
                None if row["profile_age_days"] is None else int(row["profile_age_days"])
            ),
        )

    @staticmethod
    def _load_run(connection: sqlite3.Connection, run_id: str) -> ProbeRun | None:
        row = connection.execute(
            "SELECT * FROM probe_runs WHERE id = ?",
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        return ProbeRun(
            id=str(row["id"]),
            source_id=str(row["source_id"]),
            request_key=str(row["request_key"]),
            kind=ProbeKind(str(row["probe_kind"])),
            context_id=str(row["context_id"]),
            query_text=_optional_str(row["query_text"]),
            requested_page_limit=int(row["requested_page_limit"]),
            started_at=_parse_timestamp(str(row["started_at"])),
            completed_at=(
                None
                if row["completed_at"] is None
                else _parse_timestamp(str(row["completed_at"]))
            ),
            status=ProbeRunStatus(str(row["status"])),
            error=_optional_str(row["error"]),
            error_raw_snapshot_id=_optional_str(row["error_raw_snapshot_id"]),
        )

    @staticmethod
    def _load_page(
        connection: sqlite3.Connection,
        run_id: str,
        page_index: int,
    ) -> ProbePage | None:
        row = connection.execute(
            "SELECT * FROM probe_pages WHERE run_id = ? AND page_index = ?",
            (run_id, page_index),
        ).fetchone()
        return None if row is None else _page_from_row(row)

    @staticmethod
    def _load_pages(
        connection: sqlite3.Connection,
        run_id: str,
    ) -> tuple[ProbePage, ...]:
        rows = connection.execute(
            "SELECT * FROM probe_pages WHERE run_id = ? ORDER BY page_index",
            (run_id,),
        ).fetchall()
        return tuple(_page_from_row(row) for row in rows)


def _context_id(context: ProbeContext) -> str:
    encoded = json.dumps(
        context.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    return "probe-context:" + hashlib.sha256(encoded).hexdigest()[:32]


def _page_from_row(row: sqlite3.Row) -> ProbePage:
    return ProbePage(
        run_id=str(row["run_id"]),
        page_index=int(row["page_index"]),
        raw_snapshot_id=str(row["raw_snapshot_id"]),
        retrieved_at=_parse_timestamp(str(row["retrieved_at"])),
        request_page_id=_optional_str(row["request_page_id"]),
        request_rtx_reqid=_optional_str(row["request_rtx_reqid"]),
        response_next_page_id=_optional_str(row["response_next_page_id"]),
        response_rtx_reqid=_optional_str(row["response_rtx_reqid"]),
        has_next_page=bool(row["has_next_page"]),
    )


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _timestamp(value: datetime) -> str:
    _require_aware(value, "timestamp")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)
