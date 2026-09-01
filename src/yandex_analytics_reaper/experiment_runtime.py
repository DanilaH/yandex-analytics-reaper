from __future__ import annotations

import os
import sys
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator

_WORKFLOW_VERSION: Literal["analyst-experiment-v1.2"] = "analyst-experiment-v1.2"
_TIMINGS_SPEC_VERSION: Literal["analyst-experiment-timings-v1"] = "analyst-experiment-timings-v1"


class ExperimentRuntimeError(RuntimeError):
    """Runner lifecycle/observability state could not be established safely."""


class AnalystExperimentRunState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    experiment_id: str
    run_id: str
    started_at: datetime
    manifest_sha256: str
    workflow_version: Literal["analyst-experiment-v1.2"] = _WORKFLOW_VERSION

    @field_validator("started_at")
    @classmethod
    def validate_started_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("started_at must be timezone-aware")
        return value

    @field_validator("manifest_sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        _require_sha256(value)
        return value


class AnalystExecutionEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    timestamp: datetime
    experiment_id: str
    run_id: str
    event: str
    stage: str
    elapsed_seconds: float = Field(ge=0.0)
    duration_seconds: float | None = Field(default=None, ge=0.0)
    worker: str | None = None
    family_id: str | None = None
    query: str | None = None
    query_index: int | None = Field(default=None, ge=1)
    query_total: int | None = Field(default=None, ge=1)
    page: int | None = Field(default=None, ge=1)
    page_limit: int | None = Field(default=None, ge=1)
    attempt: int | None = Field(default=None, ge=1)
    max_attempts: int | None = Field(default=None, ge=1)
    probe_run_id: str | None = None
    listing_count: int | None = Field(default=None, ge=0)
    batch_index: int | None = Field(default=None, ge=1)
    batch_total: int | None = Field(default=None, ge=1)
    raw_snapshot_id: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    retry_delay_seconds: float | None = Field(default=None, ge=0.0)


class AnalystTimingSpan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    elapsed_seconds: float = Field(ge=0.0)


class AnalystQueryTiming(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    family_id: str
    query: str
    query_index: int = Field(ge=1)
    query_total: int = Field(ge=1)
    action: Literal["collected", "reused"]
    elapsed_seconds: float | None = Field(default=None, ge=0.0)


class AnalystPageTiming(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    query: str
    page: int = Field(ge=1)
    page_limit: int = Field(ge=1)
    elapsed_seconds: float = Field(ge=0.0)


class AnalystRetryTiming(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    unit: Literal["query", "rich_batch"]
    attempt: int = Field(ge=1)
    delay_seconds: float = Field(ge=0.0)
    query: str | None = None
    batch_index: int | None = Field(default=None, ge=1)


class AnalystRichBatchTiming(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    batch_index: int = Field(ge=1)
    batch_total: int = Field(ge=1)
    listing_count: int = Field(ge=0)
    elapsed_seconds: float = Field(ge=0.0)


class AnalystExperimentTimings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: Literal["analyst-experiment-timings-v1"] = _TIMINGS_SPEC_VERSION
    experiment_id: str
    run_id: str
    invocation_mode: Literal["run", "resume"]
    query_workers: int = Field(ge=1)
    stages: tuple[AnalystTimingSpan, ...]
    queries: tuple[AnalystQueryTiming, ...]
    pages: tuple[AnalystPageTiming, ...]
    retries: tuple[AnalystRetryTiming, ...]
    rich_batches: tuple[AnalystRichBatchTiming, ...]


class WorkdirLock:
    """One process-owned non-blocking lock for an experiment workdir."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._handle: IO[bytes] | None = None

    def __enter__(self) -> Self:
        return self.acquire()

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.release()

    def acquire(self) -> Self:
        if self._handle is not None:
            raise ExperimentRuntimeError("workdir lock is already held by this object")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+b")
        try:
            _lock_file(handle)
        except Exception as exc:
            handle.close()
            if isinstance(exc, ExperimentRuntimeError):
                raise
            raise ExperimentRuntimeError(
                f"workdir is already owned by another live process: {self.path}"
            ) from exc
        self._handle = handle
        return self

    def release(self) -> None:
        handle = self._handle
        if handle is None:
            return
        self._handle = None
        try:
            _unlock_file(handle)
        finally:
            handle.close()


class ExperimentTimingRecorder:
    def __init__(self, *, monotonic: Callable[[], float] = time.monotonic) -> None:
        self.monotonic = monotonic
        self._lock = threading.Lock()
        self._stages: list[AnalystTimingSpan] = []
        self._queries: list[AnalystQueryTiming] = []
        self._pages: list[AnalystPageTiming] = []
        self._retries: list[AnalystRetryTiming] = []
        self._rich_batches: list[AnalystRichBatchTiming] = []

    @contextmanager
    def measure_stage(self, name: str) -> Iterator[None]:
        started = self.monotonic()
        try:
            yield
        finally:
            self.record_stage(name, self.monotonic() - started)

    def record_stage(self, name: str, elapsed_seconds: float) -> None:
        with self._lock:
            self._stages.append(
                AnalystTimingSpan(name=name, elapsed_seconds=max(0.0, elapsed_seconds))
            )

    def record_query(
        self,
        *,
        family_id: str,
        query: str,
        query_index: int,
        query_total: int,
        action: Literal["collected", "reused"],
        elapsed_seconds: float | None,
    ) -> None:
        with self._lock:
            self._queries.append(
                AnalystQueryTiming(
                    family_id=family_id,
                    query=query,
                    query_index=query_index,
                    query_total=query_total,
                    action=action,
                    elapsed_seconds=(
                        None if elapsed_seconds is None else max(0.0, elapsed_seconds)
                    ),
                )
            )

    def record_page(
        self,
        *,
        query: str,
        page: int,
        page_limit: int,
        elapsed_seconds: float,
    ) -> None:
        with self._lock:
            self._pages.append(
                AnalystPageTiming(
                    query=query,
                    page=page,
                    page_limit=page_limit,
                    elapsed_seconds=max(0.0, elapsed_seconds),
                )
            )

    def record_retry(
        self,
        *,
        unit: Literal["query", "rich_batch"],
        attempt: int,
        delay_seconds: float,
        query: str | None = None,
        batch_index: int | None = None,
    ) -> None:
        with self._lock:
            self._retries.append(
                AnalystRetryTiming(
                    unit=unit,
                    attempt=attempt,
                    delay_seconds=max(0.0, delay_seconds),
                    query=query,
                    batch_index=batch_index,
                )
            )

    def record_rich_batch(
        self,
        *,
        batch_index: int,
        batch_total: int,
        listing_count: int,
        elapsed_seconds: float,
    ) -> None:
        with self._lock:
            self._rich_batches.append(
                AnalystRichBatchTiming(
                    batch_index=batch_index,
                    batch_total=batch_total,
                    listing_count=listing_count,
                    elapsed_seconds=max(0.0, elapsed_seconds),
                )
            )

    def report(
        self,
        *,
        experiment_id: str,
        run_id: str,
        invocation_mode: Literal["run", "resume"],
        query_workers: int,
    ) -> AnalystExperimentTimings:
        with self._lock:
            stages = tuple(self._stages)
            queries = tuple(sorted(self._queries, key=lambda item: item.query_index))
            pages = tuple(self._pages)
            retries = tuple(self._retries)
            rich_batches = tuple(self._rich_batches)
        return AnalystExperimentTimings(
            experiment_id=experiment_id,
            run_id=run_id,
            invocation_mode=invocation_mode,
            query_workers=query_workers,
            stages=stages,
            queries=queries,
            pages=pages,
            retries=retries,
            rich_batches=rich_batches,
        )


class ExperimentEventEmitter:
    """One append-only execution trace shared by console and workdir logs."""

    def __init__(
        self,
        workdir: Path,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], datetime] | None = None,
        experiment_id: str,
        run_id: str,
        output: Callable[[str], None] = print,
        heartbeat_interval_seconds: float = 15.0,
        started_monotonic: float | None = None,
    ) -> None:
        self.workdir = workdir
        self.experiment_id = experiment_id
        self.run_id = run_id
        self.monotonic = monotonic
        self.wall_clock = wall_clock or _utc_now
        self.output = output
        self.heartbeat_interval_seconds = heartbeat_interval_seconds
        self._started_monotonic = monotonic() if started_monotonic is None else started_monotonic
        self._last_emit_monotonic = self._started_monotonic
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_context: dict[str, object] = {"stage": "initialization"}
        logs = workdir / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        human_path = logs / "run.log"
        jsonl_path = logs / "events.jsonl"
        _ensure_append_boundary(human_path)
        _ensure_append_boundary(jsonl_path)
        self._human = human_path.open("a", encoding="utf-8")
        self._jsonl = jsonl_path.open("a", encoding="utf-8")

    def __enter__(self) -> Self:
        self.start_heartbeat()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    @property
    def elapsed_seconds(self) -> float:
        return max(0.0, self.monotonic() - self._started_monotonic)

    @property
    def last_context(self) -> dict[str, object]:
        with self._lock:
            return dict(self._last_context)

    def start_heartbeat(self) -> None:
        if self.heartbeat_interval_seconds <= 0 or self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._heartbeat_loop,
            name="analyst-experiment-heartbeat",
            daemon=True,
        )
        self._thread.start()

    def stop_heartbeat(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=max(1.0, self.heartbeat_interval_seconds * 2.0))
        self._thread = None

    def emit(self, event: str, *, stage: str, **context: object) -> AnalystExecutionEvent:
        with self._lock:
            now_mono = self.monotonic()
            payload = {
                key: value
                for key, value in context.items()
                if value is not None and key in AnalystExecutionEvent.model_fields
            }
            record = AnalystExecutionEvent.model_validate(
                {
                    "timestamp": _aware(self.wall_clock(), "event wall clock"),
                    "experiment_id": self.experiment_id,
                    "run_id": self.run_id,
                    "event": event,
                    "stage": stage,
                    "elapsed_seconds": max(0.0, now_mono - self._started_monotonic),
                    **payload,
                }
            )
            if event != "heartbeat":
                self._last_context = {
                    "stage": stage,
                    **{
                        key: value
                        for key, value in payload.items()
                        if key
                        in {
                            "worker",
                            "family_id",
                            "query",
                            "query_index",
                            "query_total",
                            "page",
                            "page_limit",
                            "attempt",
                            "max_attempts",
                            "probe_run_id",
                            "batch_index",
                            "batch_total",
                            "raw_snapshot_id",
                        }
                    },
                }
            self._last_emit_monotonic = now_mono
            json_line = record.model_dump_json(exclude_none=True)
            human_line = _human_event_line(record)
            self._jsonl.write(json_line + "\n")
            self._human.write(human_line + "\n")
            self._jsonl.flush()
            self._human.flush()
            self.output(human_line)
            return record

    def emit_heartbeat_if_due(self) -> bool:
        with self._lock:
            quiet_for = self.monotonic() - self._last_emit_monotonic
            if quiet_for < self.heartbeat_interval_seconds:
                return False
            context = dict(self._last_context)
        stage = str(context.pop("stage", "unknown"))
        self.emit("heartbeat", stage=stage, **context)
        return True

    def close(self) -> None:
        self.stop_heartbeat()
        with self._lock:
            self._jsonl.flush()
            self._human.flush()
            self._jsonl.close()
            self._human.close()

    def _heartbeat_loop(self) -> None:
        interval = self.heartbeat_interval_seconds
        poll = min(max(interval / 4.0, 0.01), 1.0)
        while not self._stop.wait(poll):
            self.emit_heartbeat_if_due()


def read_run_state(path: Path) -> AnalystExperimentRunState:
    try:
        return AnalystExperimentRunState.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ExperimentRuntimeError("run-state.json is missing or invalid") from exc


def write_run_state(path: Path, state: AnalystExperimentRunState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    payload = state.model_dump_json(indent=2) + "\n"
    try:
        with tmp.open("w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except Exception:
        with suppress(OSError):
            tmp.unlink(missing_ok=True)
        raise


def format_failure_summary(
    exc: BaseException,
    *,
    context: dict[str, object],
    elapsed_seconds: float,
    workdir: str,
    resume_command: str | None = None,
) -> str:
    lines = ["EXPERIMENT FAILED"]
    ordered = (
        ("stage", context.get("stage")),
        ("worker", context.get("worker")),
        ("family", context.get("family_id")),
        ("query", context.get("query")),
        ("query_index", _ratio(context.get("query_index"), context.get("query_total"))),
        ("page", _ratio(context.get("page"), context.get("page_limit"))),
        ("attempt", _ratio(context.get("attempt"), context.get("max_attempts"))),
        ("batch", _ratio(context.get("batch_index"), context.get("batch_total"))),
        ("error", f"{type(exc).__name__}: {str(exc).strip() or type(exc).__name__}"),
        ("elapsed_seconds", f"{max(0.0, elapsed_seconds):.3f}"),
        ("last_raw_snapshot", context.get("raw_snapshot_id")),
        ("workdir_preserved", workdir),
        ("resume", resume_command),
    )
    for label, value in ordered:
        if value is not None:
            lines.append(f"{label}: {value}")
    return "\n".join(lines)


def _ratio(left: object, right: object) -> str | None:
    if left is None:
        return None
    return str(left) if right is None else f"{left}/{right}"


def _human_event_line(event: AnalystExecutionEvent) -> str:
    parts = [
        event.timestamp.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        f"+{event.elapsed_seconds:.3f}s",
        event.event,
        f"experiment={event.experiment_id}",
        f"run={event.run_id}",
        f"stage={event.stage}",
    ]
    for key in (
        "duration_seconds",
        "worker",
        "family_id",
        "query",
        "query_index",
        "query_total",
        "page",
        "page_limit",
        "attempt",
        "max_attempts",
        "probe_run_id",
        "listing_count",
        "batch_index",
        "batch_total",
        "raw_snapshot_id",
        "error_type",
        "retry_delay_seconds",
    ):
        value = getattr(event, key)
        if value is not None:
            parts.append(f"{key}={value}")
    if event.error_message:
        parts.append(f"error_message={event.error_message}")
    return " ".join(parts)


def _ensure_append_boundary(path: Path) -> None:
    if not path.exists():
        return
    if not path.is_file():
        raise ExperimentRuntimeError(f"log path is not a regular file: {path}")
    with path.open("r+b") as handle:
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
        if size == 0:
            return
        handle.seek(-1, os.SEEK_END)
        if handle.read(1) == b"\n":
            return
        handle.seek(0, os.SEEK_END)
        handle.write(b"\n")
        handle.flush()
        os.fsync(handle.fileno())


def _lock_file(handle: IO[bytes]) -> None:
    if sys.platform == "win32":
        import msvcrt

        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise ExperimentRuntimeError("workdir is already locked") from exc
        return

    import fcntl

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        raise ExperimentRuntimeError("workdir is already locked") from exc


def _unlock_file(handle: IO[bytes]) -> None:
    if sys.platform == "win32":
        import msvcrt

        handle.seek(0)
        with suppress(OSError):
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    with suppress(OSError):
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _require_sha256(value: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError("value must be a lowercase SHA-256 hex digest")


def _aware(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


def _utc_now() -> datetime:
    return datetime.now(UTC)
