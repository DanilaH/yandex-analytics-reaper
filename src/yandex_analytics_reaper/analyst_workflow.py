from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import time
from collections.abc import Callable, Iterable, Iterator, Sequence
from contextlib import contextmanager, suppress
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Literal, Self
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from yandex_analytics_reaper import __version__
from yandex_analytics_reaper.analyst import (
    AnalystComparableSetReference,
    AnalystMarketExporter,
    AnalystMarketExportReport,
    AnalystMarketFeatureBuilder,
    AnalystMarketFeaturesReport,
    AnalystRawSnapshotReference,
    AnalystSnapshotBuilder,
    AnalystSnapshotDeclaration,
    AnalystSnapshotReport,
    validate_analyst_market_export,
    validate_analyst_market_features,
    validate_analyst_snapshot_report,
    write_analyst_export_csv,
)
from yandex_analytics_reaper.comparables import YandexSearchComparableSetBuilder
from yandex_analytics_reaper.config import load_settings
from yandex_analytics_reaper.domain import (
    ComparableSetVersion,
    ProbeContext,
    QueryFamilyMember,
    QueryFamilyVersion,
    QueryVariantKind,
    SessionProfile,
)
from yandex_analytics_reaper.experiment_runtime import (
    AnalystExperimentRunState,
    ExperimentEventEmitter,
    ExperimentTimingRecorder,
    WorkdirLock,
    format_failure_summary,
    write_run_state,
)
from yandex_analytics_reaper.ingestion import (
    PaginatedProbePageEvent,
    PaginatedProbeResult,
    RichMetadataCollectionResult,
    YandexNormalizationPersistence,
    YandexPaginatedProbeRunner,
    YandexRichMetadataCollector,
    YandexSessionManager,
)
from yandex_analytics_reaper.schema_drift import SQLiteSchemaDriftRegistry
from yandex_analytics_reaper.sources.yandex import YandexPublicClient
from yandex_analytics_reaper.storage import (
    FilesystemRawSnapshotStore,
    SQLiteComparableSetStore,
    SQLiteProbeRunStore,
    SQLiteQueryFamilyStore,
)

ANALYST_EXPERIMENT_SCHEMA_VERSION: Literal[1] = 1
ANALYST_EXPERIMENT_WORKFLOW_VERSION: Literal["analyst-experiment-v1.2"] = (
    "analyst-experiment-v1.2"
)
_VERIFICATION_SPEC_VERSION: Literal["analyst-experiment-verification-v1"] = (
    "analyst-experiment-verification-v1"
)
_ARTIFACT_MANIFEST_SPEC_VERSION: Literal["analyst-experiment-artifact-v1"] = (
    "analyst-experiment-artifact-v1"
)
_SOURCE_ID: Literal["yandex_public"] = "yandex_public"
_MAX_RICH_BATCH_SIZE = 100
_MAX_TRANSPORT_ATTEMPTS = 3
_EXPERIMENT_ID_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
_TRANSPORT_ERRORS = (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.ConnectError)


class AnalystExperimentError(RuntimeError):
    """A declarative analyst experiment could not complete without weakening its contract."""


class AnalystExperimentContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    pages: int = Field(ge=1)
    session_profile: Literal["clean_anonymous"]
    lang: str
    device: Literal["desktop", "mobile"]
    platform: str

    @field_validator("lang", "platform")
    @classmethod
    def validate_trimmed_non_blank(cls, value: str) -> str:
        if not value or value != value.strip():
            raise ValueError("experiment context text fields must be non-blank and trimmed")
        return value


class AnalystExperimentFamily(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(pattern=_EXPERIMENT_ID_PATTERN, max_length=80)
    queries: tuple[str, ...] = Field(min_length=1)

    @field_validator("queries")
    @classmethod
    def validate_queries(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not value or value != value.strip() for value in values):
            raise ValueError("family queries must be non-blank and already trimmed")
        if len(set(values)) != len(values):
            raise ValueError("family queries must be unique")
        return values


class AnalystExperimentManifest(BaseModel):
    """One exact human-declared market exploration input."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1]
    experiment_id: str = Field(pattern=_EXPERIMENT_ID_PATTERN, max_length=80)
    context: AnalystExperimentContext
    families: tuple[AnalystExperimentFamily, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_family_identity(self) -> Self:
        family_ids = [family.id for family in self.families]
        if len(set(family_ids)) != len(family_ids):
            raise ValueError("experiment family ids must be unique")
        queries = [query for family in self.families for query in family.queries]
        if len(set(queries)) != len(queries):
            raise ValueError("an exact query may belong to only one experiment family")
        return self


class AnalystQueryDiagnostic(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    query: str
    selected_run_id: str
    unique_organic_listings: int = Field(ge=0)


class AnalystPairwiseCoherence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    left_query: str
    right_query: str
    intersection_count: int = Field(ge=0)
    union_count: int = Field(ge=0)
    jaccard: float | None = Field(default=None, ge=0.0, le=1.0)


class AnalystFamilyCoherence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    family_id: str
    query_diagnostics: tuple[AnalystQueryDiagnostic, ...] = Field(min_length=1)
    union_count: int = Field(ge=0)
    all_query_intersection_count: int = Field(ge=0)
    all_query_jaccard: float | None = Field(default=None, ge=0.0, le=1.0)
    pairwise: tuple[AnalystPairwiseCoherence, ...]


class AnalystExperimentVerification(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: Literal["analyst-experiment-verification-v1"]
    status: Literal["pass"]
    snapshot_content_hash: str
    market_export_content_hash: str
    market_features_content_hash: str

    @field_validator(
        "snapshot_content_hash",
        "market_export_content_hash",
        "market_features_content_hash",
    )
    @classmethod
    def validate_hash(cls, value: str) -> str:
        _require_sha256(value)
        return value


class AnalystRuntimeProvenance(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    package_version: str
    git_sha: str | None
    python: str
    platform: str


class AnalystExperimentExecutionSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    workflow_version: Literal["analyst-experiment-v1.2"]
    status: Literal["completed"]
    experiment_id: str
    run_id: str
    started_at: datetime
    completed_at: datetime
    manifest_sha256: str
    runtime: AnalystRuntimeProvenance
    family_count: int = Field(ge=1)
    query_count: int = Field(ge=1)
    comparable_unique_listing_count: int = Field(ge=0)
    rich_requested_listing_count: int = Field(ge=0)
    rich_observed_listing_count: int = Field(ge=0)
    rich_missing_listing_ids: tuple[str, ...]
    snapshot_content_hash: str
    market_export_content_hash: str
    market_features_content_hash: str
    final_invocation_mode: Literal["run", "resume"]
    final_invocation_started_at: datetime
    final_invocation_workers: int = Field(ge=1)
    was_resumed: bool
    reused_query_count: int = Field(ge=0)
    collected_query_count: int = Field(ge=0)
    verifier_status: Literal["pass"]

    @field_validator(
        "manifest_sha256",
        "snapshot_content_hash",
        "market_export_content_hash",
        "market_features_content_hash",
    )
    @classmethod
    def validate_hash(cls, value: str) -> str:
        _require_sha256(value)
        return value


class AnalystArtifactFile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str
    size: int = Field(ge=0)
    sha256: str

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or value != path.as_posix():
            raise ValueError("artifact paths must be safe normalized relative POSIX paths")
        if value == "artifact-manifest.json":
            raise ValueError("artifact manifest must not hash itself")
        return value

    @field_validator("sha256")
    @classmethod
    def validate_sha(cls, value: str) -> str:
        _require_sha256(value)
        return value


class AnalystArtifactManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: Literal["analyst-experiment-artifact-v1"]
    experiment_id: str
    run_id: str
    files: tuple[AnalystArtifactFile, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_paths(self) -> Self:
        paths = [item.path for item in self.files]
        if len(set(paths)) != len(paths):
            raise ValueError("artifact manifest file paths must be unique")
        if paths != sorted(paths):
            raise ValueError("artifact manifest file paths must be sorted")
        return self


class AnalystExperimentResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    experiment_id: str
    run_id: str
    artifact_path: str
    artifact_sha256: str
    artifact_manifest_sha256: str
    verifier: Literal["PASS"]
    family_count: int
    query_count: int
    comparable_unique_listing_count: int
    rich_requested_listing_count: int
    rich_observed_listing_count: int
    invocation_elapsed_seconds: float = Field(ge=0.0)

    @field_validator("artifact_sha256", "artifact_manifest_sha256")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        _require_sha256(value)
        return value


class AnalystExperimentRunner:
    """Thin application coordinator over the existing collection/analyst boundaries."""

    def __init__(
        self,
        *,
        repository_root: Path,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        output: Callable[[str], None] = print,
        heartbeat_interval_seconds: float = 15.0,
    ) -> None:
        self.repository_root = repository_root.resolve()
        self.sleeper = sleeper
        self.monotonic = monotonic
        self.output = output
        self.heartbeat_interval_seconds = heartbeat_interval_seconds
        self.settings = load_settings()

    def run(
        self,
        manifest: AnalystExperimentManifest,
        *,
        manifest_bytes: bytes,
        manifest_validation_elapsed_seconds: float = 0.0,
        invocation_started_monotonic: float | None = None,
    ) -> AnalystExperimentResult:
        invocation_started_at = datetime.now(UTC)
        started_at = invocation_started_at
        invocation_mono = (
            self.monotonic()
            if invocation_started_monotonic is None
            else invocation_started_monotonic
        )
        run_id, workdir, artifact_path = _allocate_run_paths(
            self.repository_root,
            manifest.experiment_id,
            started_at,
        )
        initialization_started = self.monotonic()
        lock = WorkdirLock(workdir / "run.lock")
        try:
            with lock:
                input_dir = workdir / "input"
                report_dir = workdir / "reports"
                input_dir.mkdir(parents=True)
                report_dir.mkdir(parents=True)
                (input_dir / "manifest.json").write_bytes(manifest_bytes)
                manifest_sha256 = _sha256_bytes(manifest_bytes)
                write_run_state(
                    workdir / "run-state.json",
                    AnalystExperimentRunState(
                        experiment_id=manifest.experiment_id,
                        run_id=run_id,
                        started_at=started_at,
                        manifest_sha256=manifest_sha256,
                    ),
                )
                timings = ExperimentTimingRecorder(monotonic=self.monotonic)
                timings.record_stage(
                    "manifest_validation",
                    max(0.0, manifest_validation_elapsed_seconds),
                )
                timings.record_stage(
                    "workdir_initialization",
                    max(0.0, self.monotonic() - initialization_started),
                )
                with ExperimentEventEmitter(
                    workdir,
                    monotonic=self.monotonic,
                    experiment_id=manifest.experiment_id,
                    run_id=run_id,
                    output=self.output,
                    heartbeat_interval_seconds=self.heartbeat_interval_seconds,
                    started_monotonic=invocation_mono,
                ) as events:
                    query_total = sum(len(item.queries) for item in manifest.families)
                    events.emit(
                        "run_started",
                        stage="workdir_initialization",
                        query_total=query_total,
                    )
                    events.emit(
                        "stage_completed",
                        stage="manifest_validation",
                    )
                    events.emit(
                        "stage_completed",
                        stage="workdir_initialization",
                    )
                    try:
                        result = self._run_in_workdir(
                            manifest,
                            started_at=started_at,
                            invocation_started_at=invocation_started_at,
                            manifest_sha256=manifest_sha256,
                            run_id=run_id,
                            workdir=workdir,
                            artifact_path=artifact_path,
                            events=events,
                            timings=timings,
                        )
                    except Exception as exc:
                        failure_context = events.last_context
                        stage = str(failure_context.get("stage", "unknown"))
                        events.emit(
                            "experiment_failed",
                            stage=stage,
                            error_type=type(exc).__name__,
                            error_message=str(exc).strip() or type(exc).__name__,
                            **{
                                key: value
                                for key, value in failure_context.items()
                                if key != "stage"
                            },
                        )
                        raise AnalystExperimentError(
                            format_failure_summary(
                                exc,
                                context=failure_context,
                                elapsed_seconds=events.elapsed_seconds,
                                workdir=_relative_display(workdir, self.repository_root),
                            )
                        ) from exc
                    events.emit(
                        "experiment_completed",
                        stage="complete",
                        query_total=query_total,
                    )
            shutil.rmtree(workdir)
            return result
        except AnalystExperimentError:
            raise
        except Exception as exc:
            raise AnalystExperimentError(
                f"{type(exc).__name__}: {exc}; workdir preserved at "
                f"{_relative_display(workdir, self.repository_root)}"
            ) from exc

    def _run_in_workdir(
        self,
        manifest: AnalystExperimentManifest,
        *,
        started_at: datetime,
        invocation_started_at: datetime,
        manifest_sha256: str,
        run_id: str,
        workdir: Path,
        artifact_path: Path,
        events: ExperimentEventEmitter,
        timings: ExperimentTimingRecorder,
    ) -> AnalystExperimentResult:
        report_dir = workdir / "reports"
        csv_dir = workdir / "csv"
        raw_store = FilesystemRawSnapshotStore(workdir / "raw")
        database_path = workdir / "market.sqlite3"

        context = _probe_context(manifest.context)
        query_store = SQLiteQueryFamilyStore(database_path)
        probe_store = SQLiteProbeRunStore(database_path)
        comparable_store = SQLiteComparableSetStore(database_path)
        schema_registry = SQLiteSchemaDriftRegistry(database_path)
        persistence = YandexNormalizationPersistence(database_path)
        session_manager = YandexSessionManager(
            state_root=workdir / "sessions",
            base_url=self.settings.yandex_base_url,
            timeout_seconds=self.settings.http_timeout_seconds,
            user_agent=self.settings.user_agent,
        )

        families: list[tuple[AnalystExperimentFamily, QueryFamilyVersion, list[str]]] = []
        query_total = sum(len(item.queries) for item in manifest.families)
        query_index = 0

        with _stage(events, timings, self.monotonic, "search_collection"):
            for family_input in manifest.families:
                family = _query_family(
                    family_input,
                    language=manifest.context.lang,
                    created_at=started_at,
                )
                query_store.persist(family)
                family_run_ids: list[str] = []
                for query in family_input.queries:
                    query_index += 1
                    query_started = self.monotonic()
                    events.emit(
                        "query_started",
                        stage="search_collection",
                        family_id=family_input.id,
                        query=query,
                        query_index=query_index,
                        query_total=query_total,
                    )
                    search_result = self._collect_search(
                        query,
                        context=context,
                        page_limit=manifest.context.pages,
                        raw_store=raw_store,
                        probe_store=probe_store,
                        schema_registry=schema_registry,
                        session_manager=session_manager,
                        family_id=family_input.id,
                        query_index=query_index,
                        query_total=query_total,
                        events=events,
                        timings=timings,
                    )
                    family_run_ids.append(search_result.record.run.id)
                    elapsed = max(0.0, self.monotonic() - query_started)
                    timings.record_query(
                        family_id=family_input.id,
                        query=query,
                        query_index=query_index,
                        query_total=query_total,
                        action="collected",
                        elapsed_seconds=elapsed,
                    )
                    events.emit(
                        "query_completed",
                        stage="search_collection",
                        family_id=family_input.id,
                        query=query,
                        query_index=query_index,
                        query_total=query_total,
                        probe_run_id=search_result.record.run.id,
                        listing_count=sum(len(page.games) for page in search_result.parsed_pages),
                        duration_seconds=elapsed,
                    )
                families.append((family_input, family, family_run_ids))

        comparable_sets: list[ComparableSetVersion] = []
        with _stage(events, timings, self.monotonic, "comparable_construction"):
            for family_input, family, family_run_ids in families:
                comparable = YandexSearchComparableSetBuilder(
                    raw_store=raw_store,
                    probe_store=probe_store,
                ).build(
                    family,
                    family_run_ids,
                    set_id=f"{manifest.experiment_id}--{family_input.id}",
                    version=1,
                    created_at=datetime.now(UTC),
                )
                comparable_sets.append(comparable_store.persist(comparable))

        with _stage(events, timings, self.monotonic, "family_coherence"):
            coherence_reports = [_coherence_report(item) for item in comparable_sets]
            _write_json(
                report_dir / "family-coherence.json",
                [report.model_dump(mode="json") for report in coherence_reports],
            )

        listing_ids = _ordered_unique(
            member.platform_listing_id
            for comparable in comparable_sets
            for member in comparable.members
        )
        listing_id_set = set(listing_ids)
        requested_app_ids = tuple(_yandex_app_id(listing_id) for listing_id in listing_ids)
        rich_results: list[RichMetadataCollectionResult] = []
        rich_batches = tuple(_batches(requested_app_ids, _MAX_RICH_BATCH_SIZE))
        with _stage(events, timings, self.monotonic, "rich_metadata"):
            for batch_index, batch in enumerate(rich_batches, start=1):
                rich_results.append(
                    self._collect_rich_batch(
                        batch,
                        raw_store=raw_store,
                        schema_registry=schema_registry,
                        persistence=persistence,
                        batch_index=batch_index,
                        batch_total=len(rich_batches),
                        events=events,
                        timings=timings,
                    )
                )

        observed_listing_ids = {
            listing_id
            for rich_result in rich_results
            for listing_id in rich_result.parsed_listing_ids
            if listing_id in listing_id_set
        }
        rich_references = tuple(
            AnalystRawSnapshotReference(
                source_id=_SOURCE_ID,
                raw_snapshot_id=rich_result.raw_snapshot.id,
                request_key="catalogue.get_games",
            )
            for rich_result in rich_results
            if set(rich_result.parsed_listing_ids) & listing_id_set
        )
        if listing_ids and not rich_references:
            raise AnalystExperimentError(
                "rich metadata collection returned no comparable listing; snapshot cannot be frozen"
            )

        with _stage(events, timings, self.monotonic, "analyst_snapshot"):
            snapshot_declaration = AnalystSnapshotDeclaration(
                spec_version="analyst-snapshot-v1",
                snapshot_id=f"experiment:{manifest.experiment_id}:{run_id}",
                created_at=datetime.now(UTC),
                collection_parameters_status="provisional_uncalibrated",
                comparable_sets=tuple(
                    AnalystComparableSetReference(set_id=item.set_id, version=item.version)
                    for item in comparable_sets
                ),
                feed_run_ids=(),
                rich_metadata_snapshots=rich_references,
            )
            snapshot = AnalystSnapshotBuilder(
                raw_store=raw_store,
                database_path=database_path,
            ).build(snapshot_declaration)
            snapshot = validate_analyst_snapshot_report(snapshot)
            _write_model(report_dir / "analyst-snapshot.json", snapshot)

        with _stage(events, timings, self.monotonic, "market_export"):
            market_export = AnalystMarketExporter(
                raw_store=raw_store,
                database_path=database_path,
            ).build(snapshot)
            market_export = validate_analyst_market_export(market_export)
            _write_model(report_dir / "market-export.json", market_export)

        with _stage(events, timings, self.monotonic, "csv_export"):
            write_analyst_export_csv(market_export, csv_dir)

        with _stage(events, timings, self.monotonic, "market_features"):
            market_features = AnalystMarketFeatureBuilder().build(snapshot, market_export)
            market_features = validate_analyst_market_features(market_features)
            _write_model(report_dir / "market-features.json", market_features)

        with _stage(events, timings, self.monotonic, "evidence_verification"):
            verification = _verify_working_chain(
                raw_store=raw_store,
                database_path=database_path,
                declaration=snapshot_declaration,
                snapshot=snapshot,
                market_export=market_export,
                market_features=market_features,
            )
            _write_model(report_dir / "verification.json", verification)

        missing_listing_ids = tuple(
            listing_id for listing_id in listing_ids if listing_id not in observed_listing_ids
        )
        completed_at = datetime.now(UTC)
        summary = AnalystExperimentExecutionSummary(
            workflow_version=ANALYST_EXPERIMENT_WORKFLOW_VERSION,
            status="completed",
            experiment_id=manifest.experiment_id,
            run_id=run_id,
            started_at=started_at,
            completed_at=completed_at,
            manifest_sha256=manifest_sha256,
            runtime=AnalystRuntimeProvenance(
                package_version=__version__,
                git_sha=_git_sha(self.repository_root),
                python=platform.python_version(),
                platform=platform.platform(),
            ),
            family_count=len(manifest.families),
            query_count=query_total,
            comparable_unique_listing_count=len(listing_ids),
            rich_requested_listing_count=len(listing_ids),
            rich_observed_listing_count=len(observed_listing_ids),
            rich_missing_listing_ids=missing_listing_ids,
            snapshot_content_hash=snapshot.content_hash,
            market_export_content_hash=market_export.content_hash,
            market_features_content_hash=market_features.content_hash,
            final_invocation_mode="run",
            final_invocation_started_at=invocation_started_at,
            final_invocation_workers=1,
            was_resumed=False,
            reused_query_count=0,
            collected_query_count=query_total,
            verifier_status="pass",
        )
        _write_model(workdir / "execution-summary.json", summary)

        timing_report = timings.report(
            experiment_id=manifest.experiment_id,
            run_id=run_id,
            invocation_mode="run",
            query_workers=1,
        )
        _write_model(report_dir / "execution-timings.json", timing_report)

        with _stage(events, timings, self.monotonic, "artifact_manifest_preparation"):
            artifact_manifest = build_artifact_manifest(
                workdir,
                experiment_id=manifest.experiment_id,
                run_id=run_id,
            )
            _write_model(workdir / "artifact-manifest.json", artifact_manifest)
            artifact_manifest_sha256 = _sha256_file(workdir / "artifact-manifest.json")

        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with _stage(events, timings, self.monotonic, "package_write"):
                package_workdir(workdir, artifact_path)
            with _stage(events, timings, self.monotonic, "package_verification"):
                verified_manifest = verify_packaged_artifact(
                    artifact_path,
                    expected_experiment_id=artifact_manifest.experiment_id,
                    expected_run_id=artifact_manifest.run_id,
                )
                if verified_manifest != artifact_manifest:
                    raise AnalystExperimentError(
                        "packaged artifact manifest does not match the manifest built "
                        "from the workdir"
                    )
            with _stage(events, timings, self.monotonic, "final_hashing"):
                artifact_sha256 = _sha256_file(artifact_path)
        except Exception:
            _discard_artifact(artifact_path)
            raise

        return AnalystExperimentResult(
            experiment_id=manifest.experiment_id,
            run_id=run_id,
            artifact_path=_relative_display(artifact_path, self.repository_root),
            artifact_sha256=artifact_sha256,
            artifact_manifest_sha256=artifact_manifest_sha256,
            verifier="PASS",
            family_count=summary.family_count,
            query_count=summary.query_count,
            comparable_unique_listing_count=summary.comparable_unique_listing_count,
            rich_requested_listing_count=summary.rich_requested_listing_count,
            rich_observed_listing_count=summary.rich_observed_listing_count,
            invocation_elapsed_seconds=events.elapsed_seconds,
        )

    def _collect_search(
        self,
        query: str,
        *,
        context: ProbeContext,
        page_limit: int,
        raw_store: FilesystemRawSnapshotStore,
        probe_store: SQLiteProbeRunStore,
        schema_registry: SQLiteSchemaDriftRegistry,
        session_manager: YandexSessionManager,
        family_id: str,
        query_index: int,
        query_total: int,
        events: ExperimentEventEmitter,
        timings: ExperimentTimingRecorder,
    ) -> PaginatedProbeResult:
        last_raw_snapshot_id: str | None = None

        def page_observer(page_event: PaginatedProbePageEvent) -> None:
            nonlocal last_raw_snapshot_id
            last_raw_snapshot_id = page_event.raw_snapshot_id
            timings.record_page(
                query=query,
                page=page_event.page_index + 1,
                page_limit=page_event.page_limit,
                elapsed_seconds=page_event.elapsed_seconds,
            )
            events.emit(
                "page_completed",
                stage="search_collection",
                family_id=family_id,
                query=query,
                query_index=query_index,
                query_total=query_total,
                page=page_event.page_index + 1,
                page_limit=page_event.page_limit,
                probe_run_id=page_event.probe_run_id,
                listing_count=page_event.listing_count,
                raw_snapshot_id=page_event.raw_snapshot_id,
                duration_seconds=page_event.elapsed_seconds,
            )

        for attempt in range(1, _MAX_TRANSPORT_ATTEMPTS + 1):
            try:
                with session_manager.open(context) as session:
                    return YandexPaginatedProbeRunner(
                        client=session.client,
                        raw_store=raw_store,
                        probe_store=probe_store,
                        schema_registry=schema_registry,
                        monotonic=self.monotonic,
                        page_observer=page_observer,
                    ).run_search(
                        query,
                        session.context,
                        page_limit=page_limit,
                    )
            except _TRANSPORT_ERRORS as exc:
                if attempt >= _MAX_TRANSPORT_ATTEMPTS:
                    events.emit(
                        "query_failed",
                        stage="search_collection",
                        family_id=family_id,
                        query=query,
                        query_index=query_index,
                        query_total=query_total,
                        attempt=attempt,
                        max_attempts=_MAX_TRANSPORT_ATTEMPTS,
                        error_type=type(exc).__name__,
                        error_message=str(exc).strip() or type(exc).__name__,
                        raw_snapshot_id=last_raw_snapshot_id,
                    )
                    raise
                delay = float(attempt)
                timings.record_retry(
                    unit="query",
                    attempt=attempt,
                    delay_seconds=delay,
                    query=query,
                )
                events.emit(
                    "query_retry",
                    stage="search_collection",
                    family_id=family_id,
                    query=query,
                    query_index=query_index,
                    query_total=query_total,
                    attempt=attempt,
                    max_attempts=_MAX_TRANSPORT_ATTEMPTS,
                    error_type=type(exc).__name__,
                    error_message=str(exc).strip() or type(exc).__name__,
                    retry_delay_seconds=delay,
                )
                self.sleeper(delay)
            except Exception as exc:
                events.emit(
                    "query_failed",
                    stage="search_collection",
                    family_id=family_id,
                    query=query,
                    query_index=query_index,
                    query_total=query_total,
                    attempt=attempt,
                    max_attempts=_MAX_TRANSPORT_ATTEMPTS,
                    error_type=type(exc).__name__,
                    error_message=str(exc).strip() or type(exc).__name__,
                    raw_snapshot_id=last_raw_snapshot_id,
                )
                raise
        raise RuntimeError("unreachable search retry state")

    def _collect_rich_batch(
        self,
        app_ids: Sequence[int],
        *,
        raw_store: FilesystemRawSnapshotStore,
        schema_registry: SQLiteSchemaDriftRegistry,
        persistence: YandexNormalizationPersistence,
        batch_index: int,
        batch_total: int,
        events: ExperimentEventEmitter,
        timings: ExperimentTimingRecorder,
    ) -> RichMetadataCollectionResult:
        batch_started = self.monotonic()
        events.emit(
            "rich_batch_started",
            stage="rich_metadata",
            batch_index=batch_index,
            batch_total=batch_total,
            listing_count=len(app_ids),
        )
        for attempt in range(1, _MAX_TRANSPORT_ATTEMPTS + 1):
            try:
                with YandexPublicClient(
                    base_url=self.settings.yandex_base_url,
                    timeout_seconds=self.settings.http_timeout_seconds,
                    user_agent=self.settings.user_agent,
                ) as client:
                    result = YandexRichMetadataCollector(
                        client=client,
                        raw_store=raw_store,
                        schema_registry=schema_registry,
                        persistence=persistence,
                    ).collect(app_ids)
                elapsed = max(0.0, self.monotonic() - batch_started)
                timings.record_rich_batch(
                    batch_index=batch_index,
                    batch_total=batch_total,
                    listing_count=len(app_ids),
                    elapsed_seconds=elapsed,
                )
                events.emit(
                    "rich_batch_completed",
                    stage="rich_metadata",
                    batch_index=batch_index,
                    batch_total=batch_total,
                    listing_count=len(result.parsed_listing_ids),
                    raw_snapshot_id=result.raw_snapshot.id,
                    duration_seconds=elapsed,
                )
                return result
            except _TRANSPORT_ERRORS as exc:
                if attempt >= _MAX_TRANSPORT_ATTEMPTS:
                    events.emit(
                        "rich_batch_failed",
                        stage="rich_metadata",
                        batch_index=batch_index,
                        batch_total=batch_total,
                        attempt=attempt,
                        max_attempts=_MAX_TRANSPORT_ATTEMPTS,
                        error_type=type(exc).__name__,
                        error_message=str(exc).strip() or type(exc).__name__,
                    )
                    raise
                delay = float(attempt)
                timings.record_retry(
                    unit="rich_batch",
                    attempt=attempt,
                    delay_seconds=delay,
                    batch_index=batch_index,
                )
                events.emit(
                    "rich_batch_retry",
                    stage="rich_metadata",
                    batch_index=batch_index,
                    batch_total=batch_total,
                    attempt=attempt,
                    max_attempts=_MAX_TRANSPORT_ATTEMPTS,
                    error_type=type(exc).__name__,
                    error_message=str(exc).strip() or type(exc).__name__,
                    retry_delay_seconds=delay,
                )
                self.sleeper(delay)
            except Exception as exc:
                events.emit(
                    "rich_batch_failed",
                    stage="rich_metadata",
                    batch_index=batch_index,
                    batch_total=batch_total,
                    attempt=attempt,
                    max_attempts=_MAX_TRANSPORT_ATTEMPTS,
                    error_type=type(exc).__name__,
                    error_message=str(exc).strip() or type(exc).__name__,
                )
                raise
        raise RuntimeError("unreachable rich-metadata retry state")


def run_analyst_experiment(manifest_path: Path) -> AnalystExperimentResult:
    """Validate a manifest before network I/O, then execute it inside the repository."""
    invocation_started_monotonic = time.monotonic()
    validation_started = invocation_started_monotonic
    try:
        manifest_bytes = manifest_path.read_bytes()
    except OSError as exc:
        raise AnalystExperimentError(str(exc)) from exc
    try:
        manifest = AnalystExperimentManifest.model_validate_json(manifest_bytes)
    except ValueError as exc:
        raise AnalystExperimentError(f"invalid experiment manifest: {exc}") from exc
    repository_root = find_repository_root(manifest_path)
    validation_elapsed = max(0.0, time.monotonic() - validation_started)
    return AnalystExperimentRunner(repository_root=repository_root).run(
        manifest,
        manifest_bytes=manifest_bytes,
        manifest_validation_elapsed_seconds=validation_elapsed,
        invocation_started_monotonic=invocation_started_monotonic,
    )


def find_repository_root(manifest_path: Path) -> Path:
    starts = (Path.cwd().resolve(), manifest_path.resolve().parent)
    checked: set[Path] = set()
    for start in starts:
        for candidate in (start, *start.parents):
            if candidate in checked:
                continue
            checked.add(candidate)
            pyproject = candidate / "pyproject.toml"
            try:
                content = pyproject.read_text(encoding="utf-8")
            except OSError:
                continue
            if 'name = "yandex-analytics-reaper"' in content:
                return candidate
    raise AnalystExperimentError(
        "repository root not found; run the command from the yandex-analytics-reaper worktree"
    )


def _query_family(
    family: AnalystExperimentFamily,
    *,
    language: str,
    created_at: datetime,
) -> QueryFamilyVersion:
    members = tuple(
        QueryFamilyMember(
            query_text=query,
            kind=QueryVariantKind.SEED if index == 0 else QueryVariantKind.OTHER,
        )
        for index, query in enumerate(family.queries)
    )
    return QueryFamilyVersion(
        family_id=family.id,
        version=1,
        label=family.id,
        source_id=_SOURCE_ID,
        language=language,
        created_at=created_at,
        members=members,
    )


def _probe_context(context: AnalystExperimentContext) -> ProbeContext:
    return ProbeContext(
        language=context.lang,
        device_type=context.device,
        platform=context.platform,
        session_profile=SessionProfile.CLEAN_ANONYMOUS,
    )


def _coherence_report(comparable: ComparableSetVersion) -> AnalystFamilyCoherence:
    by_run: dict[str, set[str]] = {run.probe_run_id: set() for run in comparable.runs}
    for evidence in comparable.evidence:
        by_run[evidence.probe_run_id].add(evidence.platform_listing_id)

    diagnostics = tuple(
        AnalystQueryDiagnostic(
            query=run.query_text,
            selected_run_id=run.probe_run_id,
            unique_organic_listings=len(by_run[run.probe_run_id]),
        )
        for run in comparable.runs
    )
    query_sets = [by_run[run.probe_run_id] for run in comparable.runs]
    union = set().union(*query_sets)
    intersection = query_sets[0].intersection(*query_sets[1:]) if query_sets else set()
    pairwise: list[AnalystPairwiseCoherence] = []
    for left_index, left_run in enumerate(comparable.runs):
        for right_run in comparable.runs[left_index + 1 :]:
            left = by_run[left_run.probe_run_id]
            right = by_run[right_run.probe_run_id]
            pair_union = left | right
            pairwise.append(
                AnalystPairwiseCoherence(
                    left_query=left_run.query_text,
                    right_query=right_run.query_text,
                    intersection_count=len(left & right),
                    union_count=len(pair_union),
                    jaccard=(len(left & right) / len(pair_union) if pair_union else None),
                )
            )
    return AnalystFamilyCoherence(
        family_id=comparable.query_family_id,
        query_diagnostics=diagnostics,
        union_count=len(union),
        all_query_intersection_count=len(intersection),
        all_query_jaccard=(len(intersection) / len(union) if union else None),
        pairwise=tuple(pairwise),
    )


def _verify_working_chain(
    *,
    raw_store: FilesystemRawSnapshotStore,
    database_path: Path,
    declaration: AnalystSnapshotDeclaration,
    snapshot: AnalystSnapshotReport,
    market_export: AnalystMarketExportReport,
    market_features: AnalystMarketFeaturesReport,
) -> AnalystExperimentVerification:
    rebuilt_snapshot = AnalystSnapshotBuilder(
        raw_store=raw_store,
        database_path=database_path,
    ).build(declaration)
    rebuilt_snapshot = validate_analyst_snapshot_report(rebuilt_snapshot)
    if rebuilt_snapshot != snapshot:
        raise AnalystExperimentError(
            "saved analyst snapshot does not match a fresh raw-evidence rebuild"
        )

    rebuilt_export = AnalystMarketExporter(
        raw_store=raw_store,
        database_path=database_path,
    ).build(snapshot)
    rebuilt_export = validate_analyst_market_export(rebuilt_export)
    if rebuilt_export != market_export:
        raise AnalystExperimentError(
            "saved market export does not match a fresh snapshot/raw/normalized rebuild"
        )

    rebuilt_features = AnalystMarketFeatureBuilder().build(snapshot, market_export)
    rebuilt_features = validate_analyst_market_features(rebuilt_features)
    if rebuilt_features != market_features:
        raise AnalystExperimentError(
            "saved market features do not match a fresh snapshot/export derivation"
        )

    return AnalystExperimentVerification(
        spec_version=_VERIFICATION_SPEC_VERSION,
        status="pass",
        snapshot_content_hash=snapshot.content_hash,
        market_export_content_hash=market_export.content_hash,
        market_features_content_hash=market_features.content_hash,
    )


def select_artifact_payload(workdir: Path) -> tuple[Path, ...]:
    """Select only stable analytical payload paths; exclude live/recovery state."""
    exact = {
        "input/manifest.json",
        "market.sqlite3",
        "reports/analyst-snapshot.json",
        "reports/market-export.json",
        "reports/market-features.json",
        "reports/family-coherence.json",
        "reports/verification.json",
        "reports/execution-timings.json",
        "execution-summary.json",
    }
    selected: list[Path] = []
    for path in workdir.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(workdir).as_posix()
        if relative in exact or relative.startswith(("raw/", "csv/")):
            selected.append(path)
    return tuple(sorted(selected, key=lambda item: item.relative_to(workdir).as_posix()))


def build_artifact_manifest(
    workdir: Path,
    *,
    experiment_id: str,
    run_id: str,
) -> AnalystArtifactManifest:
    files = tuple(
        AnalystArtifactFile(
            path=path.relative_to(workdir).as_posix(),
            size=path.stat().st_size,
            sha256=_sha256_file(path),
        )
        for path in select_artifact_payload(workdir)
    )
    return AnalystArtifactManifest(
        spec_version=_ARTIFACT_MANIFEST_SPEC_VERSION,
        experiment_id=experiment_id,
        run_id=run_id,
        files=files,
    )


def package_workdir(workdir: Path, artifact_path: Path) -> None:
    manifest_path = workdir / "artifact-manifest.json"
    try:
        with ZipFile(artifact_path, mode="x", compression=ZIP_DEFLATED) as archive:
            for path in select_artifact_payload(workdir):
                archive.write(path, path.relative_to(workdir).as_posix())
            archive.write(manifest_path, "artifact-manifest.json")
    except Exception:
        _discard_artifact(artifact_path)
        raise


def verify_packaged_artifact(
    artifact_path: Path,
    *,
    expected_experiment_id: str | None = None,
    expected_run_id: str | None = None,
) -> AnalystArtifactManifest:
    try:
        with ZipFile(artifact_path, mode="r") as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise AnalystExperimentError("packaged artifact contains duplicate paths")
            for name in names:
                path = PurePosixPath(name)
                if path.is_absolute() or ".." in path.parts or name != path.as_posix():
                    raise AnalystExperimentError(
                        f"packaged artifact contains unsafe path: {name}"
                    )
            if "artifact-manifest.json" not in names:
                raise AnalystExperimentError("packaged artifact is missing artifact-manifest.json")
            artifact_manifest = AnalystArtifactManifest.model_validate_json(
                archive.read("artifact-manifest.json")
            )
            if (
                expected_experiment_id is not None
                and artifact_manifest.experiment_id != expected_experiment_id
            ):
                raise AnalystExperimentError(
                    "packaged artifact experiment_id does not match the execution identity"
                )
            if expected_run_id is not None and artifact_manifest.run_id != expected_run_id:
                raise AnalystExperimentError(
                    "packaged artifact run_id does not match the execution identity"
                )
            expected = {item.path for item in artifact_manifest.files}
            if set(names) != expected | {"artifact-manifest.json"}:
                raise AnalystExperimentError(
                    "packaged artifact file set does not match artifact-manifest.json"
                )
            for item in artifact_manifest.files:
                payload = archive.read(item.path)
                if len(payload) != item.size or _sha256_bytes(payload) != item.sha256:
                    raise AnalystExperimentError(
                        f"packaged artifact hash/size mismatch for {item.path}"
                    )
            return artifact_manifest
    except (BadZipFile, OSError, ValueError) as exc:
        raise AnalystExperimentError(f"packaged artifact verification failed: {exc}") from exc


def finalize_verified_artifact(
    workdir: Path,
    artifact_path: Path,
    *,
    expected_manifest: AnalystArtifactManifest,
) -> str:
    """Publish, verify, identify, and hash one package or leave no final ZIP behind."""
    try:
        package_workdir(workdir, artifact_path)
        verified_manifest = verify_packaged_artifact(
            artifact_path,
            expected_experiment_id=expected_manifest.experiment_id,
            expected_run_id=expected_manifest.run_id,
        )
        if verified_manifest != expected_manifest:
            raise AnalystExperimentError(
                "packaged artifact manifest does not match the manifest built from the workdir"
            )
        return _sha256_file(artifact_path)
    except Exception:
        _discard_artifact(artifact_path)
        raise


@contextmanager
def _stage(
    events: ExperimentEventEmitter,
    timings: ExperimentTimingRecorder,
    monotonic: Callable[[], float],
    name: str,
) -> Iterator[None]:
    events.emit("stage_started", stage=name)
    started = monotonic()
    try:
        yield
    except Exception:
        timings.record_stage(name, max(0.0, monotonic() - started))
        raise
    else:
        elapsed = max(0.0, monotonic() - started)
        timings.record_stage(name, elapsed)
        events.emit("stage_completed", stage=name, duration_seconds=elapsed)


def _allocate_run_paths(
    repository_root: Path,
    experiment_id: str,
    started_at: datetime,
) -> tuple[str, Path, Path]:
    base = started_at.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    work_parent = repository_root / "artifacts" / "work" / experiment_id
    export_parent = repository_root / "artifacts" / "exports" / experiment_id
    work_parent.mkdir(parents=True, exist_ok=True)
    export_parent.mkdir(parents=True, exist_ok=True)

    suffix = 1
    while True:
        run_id = base if suffix == 1 else f"{base}-{suffix:02d}"
        workdir = work_parent / run_id
        artifact_path = export_parent / f"{run_id}.zip"
        if not workdir.exists() and not artifact_path.exists():
            workdir.mkdir()
            return run_id, workdir, artifact_path
        suffix += 1


def _batches(values: Sequence[int], size: int) -> Iterable[tuple[int, ...]]:
    for start in range(0, len(values), size):
        yield tuple(values[start : start + size])


def _ordered_unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _yandex_app_id(listing_id: str) -> int:
    prefix = "yandex_games:"
    if not listing_id.startswith(prefix):
        raise AnalystExperimentError(f"unsupported comparable listing id: {listing_id}")
    try:
        return int(listing_id.removeprefix(prefix))
    except ValueError as exc:
        raise AnalystExperimentError(
            f"Yandex comparable listing id is not numeric: {listing_id}"
        ) from exc


def _write_model(path: Path, model: BaseModel) -> None:
    path.write_text(model.model_dump_json(indent=2) + "\n", encoding="utf-8")


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _require_sha256(value: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError("value must be a lowercase SHA-256 hex digest")


def _git_sha(repository_root: Path) -> str | None:
    env_sha = os.getenv("GITHUB_SHA")
    if env_sha and len(env_sha) == 40:
        return env_sha
    try:
        result = subprocess.run(
            ["git", "-C", str(repository_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = result.stdout.strip()
    return value if len(value) == 40 else None


def _discard_artifact(path: Path) -> None:
    with suppress(OSError):
        path.unlink(missing_ok=True)


def _relative_display(path: Path, repository_root: Path) -> str:
    try:
        return path.resolve().relative_to(repository_root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())
