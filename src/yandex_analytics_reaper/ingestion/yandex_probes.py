from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from yandex_analytics_reaper.domain import (
    ProbeContext,
    ProbeKind,
    ProbeRun,
    ProbeRunStatus,
    SessionProfile,
)
from yandex_analytics_reaper.schema_drift import DriftSeverity, SQLiteSchemaDriftRegistry
from yandex_analytics_reaper.sources.capabilities import CollectedResponse
from yandex_analytics_reaper.sources.yandex.parsers import FeedPage, YandexFeedParser
from yandex_analytics_reaper.sources.yandex.probes import probe_page_from_yandex
from yandex_analytics_reaper.sources.yandex.schema_contracts import (
    schema_comparison_scope_for_snapshot,
    schema_contract_for_request,
)
from yandex_analytics_reaper.storage import (
    FilesystemRawSnapshotStore,
    ProbeRunRecord,
    SQLiteProbeRunStore,
)


class YandexPaginatedClient(Protocol):
    source_id: str

    def collect_feed(
        self,
        context: ProbeContext,
        *,
        count: int = 20,
        page_id: str | None = None,
        rtx_reqid: str | None = None,
    ) -> CollectedResponse: ...

    def collect_search(
        self,
        query: str,
        context: ProbeContext,
        *,
        page_id: str | None = None,
        rtx_reqid: str | None = None,
    ) -> CollectedResponse: ...


class ProbeCollectionError(RuntimeError):
    """A paginated probe could not be completed without compromising run semantics."""


@dataclass(frozen=True, slots=True)
class PaginatedProbeResult:
    record: ProbeRunRecord
    parsed_pages: tuple[FeedPage, ...]


class YandexPaginatedProbeRunner:
    """Own one feed/search collection run from raw capture through page grouping."""

    def __init__(
        self,
        *,
        client: YandexPaginatedClient,
        raw_store: FilesystemRawSnapshotStore,
        probe_store: SQLiteProbeRunStore,
        schema_registry: SQLiteSchemaDriftRegistry,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.client = client
        self.raw_store = raw_store
        self.probe_store = probe_store
        self.schema_registry = schema_registry
        self.clock = clock or _utc_now

    def run_feed(
        self,
        context: ProbeContext,
        *,
        page_limit: int,
        count: int = 20,
    ) -> PaginatedProbeResult:
        if not 1 <= count <= 100:
            raise ValueError("count must be between 1 and 100")
        return self._run(
            context=context,
            kind=ProbeKind.RECOMMENDATION_FEED,
            request_key="catalogue.feed",
            page_limit=page_limit,
            query_text=None,
            collect=lambda page_id, rtx_reqid: self.client.collect_feed(
                context,
                count=count,
                page_id=page_id,
                rtx_reqid=rtx_reqid,
            ),
        )

    def run_search(
        self,
        query: str,
        context: ProbeContext,
        *,
        page_limit: int,
    ) -> PaginatedProbeResult:
        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("query cannot be blank")
        return self._run(
            context=context,
            kind=ProbeKind.SEARCH,
            request_key="catalogue.search",
            page_limit=page_limit,
            query_text=normalized_query,
            collect=lambda page_id, rtx_reqid: self.client.collect_search(
                normalized_query,
                context,
                page_id=page_id,
                rtx_reqid=rtx_reqid,
            ),
        )

    def _run(
        self,
        *,
        context: ProbeContext,
        kind: ProbeKind,
        request_key: str,
        page_limit: int,
        query_text: str | None,
        collect: Callable[[str | None, str | None], CollectedResponse],
    ) -> PaginatedProbeResult:
        if page_limit < 1:
            raise ValueError("page_limit must be at least 1")
        _validate_effective_session_context(context)

        run = self.probe_store.create_run(
            source_id=self.client.source_id,
            request_key=request_key,
            kind=kind,
            context=context,
            requested_page_limit=page_limit,
            started_at=_aware(self.clock(), "clock result"),
            query_text=query_text,
        )
        parser = YandexFeedParser()
        parsed_pages: list[FeedPage] = []
        page_id: str | None = None
        rtx_reqid: str | None = None
        last_retrieved_at: datetime | None = None
        error_raw_snapshot_id: str | None = None

        try:
            for page_index in range(page_limit):
                error_raw_snapshot_id = None
                response = collect(page_id, rtx_reqid)
                metadata = self.raw_store.persist(response)
                last_retrieved_at = metadata.retrieved_at
                error_raw_snapshot_id = metadata.id

                if not 200 <= response.status_code < 300:
                    raise ProbeCollectionError(
                        f"source returned HTTP {response.status_code}; raw response was preserved"
                    )

                analysis = self.schema_registry.observe_json(
                    metadata,
                    response.body,
                    comparison_scope_id=schema_comparison_scope_for_snapshot(metadata),
                    contract=schema_contract_for_request(metadata.request_key),
                )
                if any(event.severity is DriftSeverity.BREAKING for event in analysis.events):
                    raise ProbeCollectionError(
                        "breaking source-schema drift detected; raw response and analysis were preserved"
                    )

                try:
                    parsed = parser.parse(response.body)
                except ValueError as exc:
                    self.schema_registry.record_parser_failure(
                        metadata,
                        comparison_scope_id=schema_comparison_scope_for_snapshot(metadata),
                        parser_name=type(parser).__name__,
                        parser_version=parser.version,
                        error=str(exc),
                    )
                    raise ProbeCollectionError(str(exc)) from exc

                page = probe_page_from_yandex(
                    run=run,
                    context=context,
                    metadata=metadata,
                    page_index=page_index,
                    page_info=parsed.page_info,
                )
                self.probe_store.append_page(page)
                parsed_pages.append(parsed)

                if not parsed.page_info.has_next_page:
                    break
                if page_index + 1 >= page_limit:
                    break

                page_id = _required_token(
                    parsed.page_info.next_page_id,
                    "hasNextPage=true without nextPageId",
                )
                rtx_reqid = _required_token(
                    parsed.page_info.rtx_reqid,
                    "hasNextPage=true without rtxReqId",
                )
                error_raw_snapshot_id = None

            error_raw_snapshot_id = None
            self.probe_store.finish_run(
                run.id,
                status=ProbeRunStatus.COMPLETED,
                completed_at=_completion_time(self.clock(), run, last_retrieved_at),
            )
        except Exception as exc:
            try:
                record = self.probe_store.get_run(run.id)
                if record is None:
                    raise RuntimeError("probe run disappeared during collection")
                if record.run.status is ProbeRunStatus.RUNNING:
                    status = ProbeRunStatus.PARTIAL if record.pages else ProbeRunStatus.FAILED
                    self.probe_store.finish_run(
                        run.id,
                        status=status,
                        completed_at=_completion_time(self.clock(), run, last_retrieved_at),
                        error=_error_text(exc),
                        error_raw_snapshot_id=error_raw_snapshot_id,
                    )
            except Exception as finalization_exc:
                exc.add_note(
                    "probe terminal-state persistence also failed: "
                    f"{_error_text(finalization_exc)}"
                )
            raise

        record = self.probe_store.get_run(run.id)
        if record is None:
            raise RuntimeError("completed probe run could not be reloaded")
        return PaginatedProbeResult(record=record, parsed_pages=tuple(parsed_pages))


def _validate_effective_session_context(context: ProbeContext) -> None:
    if context.session_profile is SessionProfile.CLEAN_ANONYMOUS:
        if context.cookie_state_hash is not None or context.profile_age_days != 0:
            raise ValueError(
                "clean_anonymous probe requires a fresh effective context "
                "with no cookie fingerprint and profile_age_days=0"
            )
        return

    if context.session_profile is SessionProfile.PERSISTENT_ANONYMOUS:
        fingerprint = context.cookie_state_hash
        if (
            fingerprint is None
            or len(fingerprint) != 64
            or any(character not in "0123456789abcdef" for character in fingerprint)
            or context.profile_age_days is None
        ):
            raise ValueError(
                "persistent_anonymous probe requires effective cookie fingerprint and profile age"
            )
        return

    if context.session_profile is SessionProfile.AUTHENTICATED_TEST:
        raise ValueError(
            "authenticated_test probe requires an explicit credential provider; "
            "the current paginated collector fails closed"
        )

    raise ValueError(f"unsupported session profile: {context.session_profile}")


def _required_token(value: str | None, error: str) -> str:
    if value is None or not value.strip():
        raise ProbeCollectionError(error)
    return value.strip()


def _completion_time(
    current: datetime,
    run: ProbeRun,
    last_retrieved_at: datetime | None,
) -> datetime:
    candidate = _aware(current, "clock result")
    floor = run.started_at
    if last_retrieved_at is not None and last_retrieved_at > floor:
        floor = last_retrieved_at
    return candidate if candidate >= floor else floor


def _error_text(exc: Exception) -> str:
    text = str(exc).strip() or type(exc).__name__
    return f"{type(exc).__name__}: {text}"[:2000]


def _aware(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


def _utc_now() -> datetime:
    return datetime.now(UTC)
