from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Literal, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from yandex_analytics_reaper.comparables import YandexSearchComparableSetBuilder
from yandex_analytics_reaper.domain import ProbeContext, ProbeKind, ProbeRunStatus
from yandex_analytics_reaper.sources.yandex.parsers import (
    YandexFeedParser,
    YandexGetGamesParser,
    YandexPlayPageParser,
)
from yandex_analytics_reaper.sources.yandex.probes import probe_page_from_yandex
from yandex_analytics_reaper.storage import (
    FilesystemRawSnapshotStore,
    SQLiteComparableSetStore,
    SQLiteProbeRunStore,
    SQLiteQueryFamilyStore,
)

ANALYST_SNAPSHOT_SPEC_VERSION: Literal["analyst-snapshot-v1"] = "analyst-snapshot-v1"
_COLLECTION_PARAMETERS_STATUS: Literal["provisional_uncalibrated"] = (
    "provisional_uncalibrated"
)
_YANDEX_SOURCE_ID: Literal["yandex_public"] = "yandex_public"


class AnalystSnapshotError(ValueError):
    """An analyst snapshot cannot be built without weakening its evidence contract."""


class AnalystComparableSetReference(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    set_id: str
    version: int = Field(ge=1)

    @field_validator("set_id")
    @classmethod
    def validate_set_id(cls, value: str) -> str:
        if not value or value != value.strip():
            raise ValueError("set_id must be non-blank and already trimmed")
        return value


class AnalystRawSnapshotReference(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: Literal["yandex_public"]
    raw_snapshot_id: str
    request_key: Literal["catalogue.get_games", "game.page"]

    @field_validator("raw_snapshot_id")
    @classmethod
    def validate_snapshot_id(cls, value: str) -> str:
        if not value or value != value.strip():
            raise ValueError("raw_snapshot_id must be non-blank and already trimmed")
        return value


class AnalystSnapshotDeclaration(BaseModel):
    """Explicit immutable inputs for one current-market analyst session."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: Literal["analyst-snapshot-v1"]
    snapshot_id: str
    created_at: AwareDatetime
    collection_parameters_status: Literal["provisional_uncalibrated"]
    comparable_sets: tuple[AnalystComparableSetReference, ...] = Field(min_length=1)
    feed_run_ids: tuple[str, ...] = ()
    rich_metadata_snapshots: tuple[AnalystRawSnapshotReference, ...] = Field(min_length=1)

    @field_validator("snapshot_id")
    @classmethod
    def validate_snapshot_id(cls, value: str) -> str:
        if not value or value != value.strip():
            raise ValueError("snapshot_id must be non-blank and already trimmed")
        return value

    @field_validator("feed_run_ids")
    @classmethod
    def validate_feed_run_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not value or value != value.strip() for value in values):
            raise ValueError("feed_run_ids must be non-blank and already trimmed")
        if len(set(values)) != len(values):
            raise ValueError("feed_run_ids must be unique")
        return values

    @model_validator(mode="after")
    def validate_reference_uniqueness(self) -> Self:
        comparable_keys = [(item.set_id, item.version) for item in self.comparable_sets]
        if len(set(comparable_keys)) != len(comparable_keys):
            raise ValueError("comparable-set references must be unique")
        raw_keys = [
            (item.source_id, item.raw_snapshot_id)
            for item in self.rich_metadata_snapshots
        ]
        if len(set(raw_keys)) != len(raw_keys):
            raise ValueError("rich-metadata raw snapshot references must be unique")
        return self


class AnalystComparableSetBinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    set_id: str
    version: int = Field(ge=1)
    query_family_id: str
    query_family_version: int = Field(ge=1)
    construction_method: str
    context_id: str
    requested_page_limit: int = Field(ge=1)
    observed_from: AwareDatetime
    observed_to: AwareDatetime
    search_run_ids: tuple[str, ...] = Field(min_length=1)
    member_listing_ids: tuple[str, ...] = Field(min_length=1)


class AnalystFeedRunBinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    context_id: str
    requested_page_limit: int = Field(ge=1)
    started_at: AwareDatetime
    completed_at: AwareDatetime
    raw_snapshot_ids: tuple[str, ...] = Field(min_length=1)
    parser_name: str
    parser_version: str


class AnalystRichMetadataBinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: Literal["yandex_public"]
    request_key: Literal["catalogue.get_games", "game.page"]
    raw_snapshot_id: str
    retrieved_at: AwareDatetime
    content_hash: str
    parser_name: str
    parser_version: str
    parsed_listing_ids: tuple[str, ...] = Field(min_length=1)
    relevant_listing_ids: tuple[str, ...] = Field(min_length=1)

    @field_validator("content_hash")
    @classmethod
    def validate_content_hash(cls, value: str) -> str:
        _require_sha256(value, "rich metadata content_hash")
        return value


class AnalystSnapshotPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: Literal["analyst-snapshot-v1"]
    snapshot_id: str
    created_at: AwareDatetime
    collection_parameters_status: Literal["provisional_uncalibrated"]
    effective_context: ProbeContext
    search_page_limit: int = Field(ge=1)
    comparable_sets: tuple[AnalystComparableSetBinding, ...] = Field(min_length=1)
    feed_runs: tuple[AnalystFeedRunBinding, ...]
    rich_metadata: tuple[AnalystRichMetadataBinding, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_snapshot_semantics(self) -> Self:
        comparable_keys = [(item.set_id, item.version) for item in self.comparable_sets]
        if len(set(comparable_keys)) != len(comparable_keys):
            raise ValueError("snapshot comparable-set bindings must be unique")
        feed_run_ids = [item.run_id for item in self.feed_runs]
        if len(set(feed_run_ids)) != len(feed_run_ids):
            raise ValueError("snapshot feed-run bindings must be unique")
        rich_raw_ids = [
            (item.source_id, item.raw_snapshot_id) for item in self.rich_metadata
        ]
        if len(set(rich_raw_ids)) != len(rich_raw_ids):
            raise ValueError("snapshot rich-metadata bindings must be unique")

        context_ids = {item.context_id for item in self.comparable_sets}
        if len(context_ids) != 1:
            raise ValueError("snapshot comparable sets must share one context_id")
        expected_context_id = next(iter(context_ids))
        if any(
            item.requested_page_limit != self.search_page_limit
            for item in self.comparable_sets
        ):
            raise ValueError("snapshot comparable sets must share search_page_limit")
        if any(item.context_id != expected_context_id for item in self.feed_runs):
            raise ValueError("snapshot feed runs must share the comparable-set context_id")

        member_ids = {
            listing_id
            for comparable in self.comparable_sets
            for listing_id in comparable.member_listing_ids
        }
        if any(
            not set(item.relevant_listing_ids).issubset(member_ids)
            for item in self.rich_metadata
        ):
            raise ValueError("rich metadata relevant listings must belong to comparable sets")
        if any(
            not set(item.relevant_listing_ids).issubset(set(item.parsed_listing_ids))
            for item in self.rich_metadata
        ):
            raise ValueError("rich metadata relevant listings must be parsed from that snapshot")

        evidence_times = [item.observed_to for item in self.comparable_sets]
        evidence_times.extend(item.completed_at for item in self.feed_runs)
        evidence_times.extend(item.retrieved_at for item in self.rich_metadata)
        if self.created_at < max(evidence_times):
            raise ValueError("snapshot created_at cannot precede bound evidence")
        return self


class AnalystSnapshotReport(AnalystSnapshotPayload):
    content_hash: str

    @field_validator("content_hash")
    @classmethod
    def validate_content_hash(cls, value: str) -> str:
        _require_sha256(value, "content_hash")
        return value


class AnalystSnapshotBuilder:
    """Bind existing current-market evidence into one reproducible analyst artifact."""

    def __init__(
        self,
        *,
        raw_store: FilesystemRawSnapshotStore,
        database_path: Path,
    ) -> None:
        self.raw_store = raw_store
        self.probe_store = SQLiteProbeRunStore(database_path)
        self.query_family_store = SQLiteQueryFamilyStore(database_path)
        self.comparable_store = SQLiteComparableSetStore(database_path)

    def build(self, declaration: AnalystSnapshotDeclaration) -> AnalystSnapshotReport:
        declaration = AnalystSnapshotDeclaration.model_validate(declaration.model_dump())
        comparable_bindings: list[AnalystComparableSetBinding] = []
        member_order: list[str] = []
        effective_context: ProbeContext | None = None
        context_id: str | None = None
        search_page_limit: int | None = None
        latest_evidence_at: datetime | None = None

        for reference in declaration.comparable_sets:
            comparable = self.comparable_store.get(reference.set_id, reference.version)
            if comparable is None:
                raise AnalystSnapshotError(
                    f"comparable set is not persisted: {reference.set_id}@{reference.version}"
                )
            family = self.query_family_store.get(
                comparable.query_family_id,
                comparable.query_family_version,
            )
            if family is None:
                raise AnalystSnapshotError(
                    "comparable set references a missing query-family version: "
                    f"{comparable.query_family_id}@{comparable.query_family_version}"
                )
            rebuilt = YandexSearchComparableSetBuilder(
                raw_store=self.raw_store,
                probe_store=self.probe_store,
            ).build(
                family,
                tuple(item.probe_run_id for item in comparable.runs),
                set_id=comparable.set_id,
                version=comparable.version,
                created_at=comparable.created_at,
            )
            if rebuilt != comparable:
                raise AnalystSnapshotError(
                    f"comparable set {comparable.set_id}@{comparable.version} "
                    "does not match a fresh raw-evidence replay"
                )

            first_run = self.probe_store.get_run(comparable.runs[0].probe_run_id)
            if first_run is None:
                raise AnalystSnapshotError("comparable-set search run disappeared")
            if effective_context is None:
                effective_context = first_run.context
                context_id = comparable.context_id
                search_page_limit = comparable.requested_page_limit
            elif (
                comparable.context_id != context_id
                or first_run.context != effective_context
                or comparable.requested_page_limit != search_page_limit
            ):
                raise AnalystSnapshotError(
                    "analyst snapshot comparable sets must share one effective context "
                    "and one search requested_page_limit"
                )

            for member in comparable.members:
                if member.platform_listing_id not in member_order:
                    member_order.append(member.platform_listing_id)
            latest_evidence_at = _max_datetime(
                latest_evidence_at,
                comparable.observed_to,
            )
            comparable_bindings.append(
                AnalystComparableSetBinding(
                    set_id=comparable.set_id,
                    version=comparable.version,
                    query_family_id=comparable.query_family_id,
                    query_family_version=comparable.query_family_version,
                    construction_method=comparable.construction_method.value,
                    context_id=comparable.context_id,
                    requested_page_limit=comparable.requested_page_limit,
                    observed_from=comparable.observed_from,
                    observed_to=comparable.observed_to,
                    search_run_ids=tuple(item.probe_run_id for item in comparable.runs),
                    member_listing_ids=tuple(
                        item.platform_listing_id for item in comparable.members
                    ),
                )
            )

        if effective_context is None or context_id is None or search_page_limit is None:
            raise AnalystSnapshotError("analyst snapshot requires comparable-set evidence")
        if not member_order:
            raise AnalystSnapshotError("declared comparable sets contain no organic members")

        feed_bindings: list[AnalystFeedRunBinding] = []
        feed_parser = YandexFeedParser()
        for run_id in declaration.feed_run_ids:
            record = self.probe_store.get_run(run_id)
            if record is None:
                raise AnalystSnapshotError(f"feed run is not persisted: {run_id}")
            run = record.run
            if (
                run.status is not ProbeRunStatus.COMPLETED
                or run.kind is not ProbeKind.RECOMMENDATION_FEED
                or run.request_key != "catalogue.feed"
                or run.source_id != _YANDEX_SOURCE_ID
                or not record.pages
            ):
                raise AnalystSnapshotError(
                    f"feed run {run_id} must be a completed non-empty Yandex feed run"
                )
            if run.context_id != context_id or record.context != effective_context:
                raise AnalystSnapshotError(
                    f"feed run {run_id} does not match the analyst snapshot effective context"
                )
            for page in record.pages:
                metadata = self.raw_store.get_metadata(
                    run.source_id,
                    page.raw_snapshot_id,
                )
                body = self.raw_store.get_body(run.source_id, page.raw_snapshot_id)
                if not 200 <= metadata.http_status < 300:
                    raise AnalystSnapshotError(
                        f"feed run {run_id} references a non-2xx raw page"
                    )
                parsed = feed_parser.parse(body)
                rebuilt_page = probe_page_from_yandex(
                    run=run,
                    context=record.context,
                    metadata=metadata,
                    page_index=page.page_index,
                    page_info=parsed.page_info,
                )
                if rebuilt_page != page:
                    raise AnalystSnapshotError(
                        f"feed run {run_id} page {page.page_index} "
                        "failed raw linkage replay"
                    )
            if run.completed_at is None:
                raise AnalystSnapshotError(
                    f"completed feed run {run_id} has no completed_at"
                )
            latest_evidence_at = _max_datetime(latest_evidence_at, run.completed_at)
            feed_bindings.append(
                AnalystFeedRunBinding(
                    run_id=run.id,
                    context_id=run.context_id,
                    requested_page_limit=run.requested_page_limit,
                    started_at=run.started_at,
                    completed_at=run.completed_at,
                    raw_snapshot_ids=tuple(
                        page.raw_snapshot_id for page in record.pages
                    ),
                    parser_name=type(feed_parser).__name__,
                    parser_version=feed_parser.version,
                )
            )

        rich_bindings: list[AnalystRichMetadataBinding] = []
        for reference in declaration.rich_metadata_snapshots:
            metadata = self.raw_store.get_metadata(
                reference.source_id,
                reference.raw_snapshot_id,
            )
            body = self.raw_store.get_body(
                reference.source_id,
                reference.raw_snapshot_id,
            )
            if metadata.request_key != reference.request_key:
                raise AnalystSnapshotError(
                    f"raw snapshot {reference.raw_snapshot_id} request_key "
                    "does not match declaration"
                )
            if not 200 <= metadata.http_status < 300:
                raise AnalystSnapshotError(
                    f"raw snapshot {reference.raw_snapshot_id} is not a successful response"
                )
            parser_name, parser_version, parsed_listing_ids = _parse_rich_metadata(
                reference.request_key,
                body,
            )
            relevant_listing_ids = tuple(
                listing_id
                for listing_id in member_order
                if listing_id in parsed_listing_ids
            )
            if not relevant_listing_ids:
                raise AnalystSnapshotError(
                    f"raw snapshot {reference.raw_snapshot_id} contains no listing from "
                    "the declared comparable sets"
                )
            latest_evidence_at = _max_datetime(
                latest_evidence_at,
                metadata.retrieved_at,
            )
            rich_bindings.append(
                AnalystRichMetadataBinding(
                    source_id=reference.source_id,
                    request_key=reference.request_key,
                    raw_snapshot_id=metadata.id,
                    retrieved_at=metadata.retrieved_at,
                    content_hash=metadata.content_hash,
                    parser_name=parser_name,
                    parser_version=parser_version,
                    parsed_listing_ids=parsed_listing_ids,
                    relevant_listing_ids=relevant_listing_ids,
                )
            )

        if latest_evidence_at is None or declaration.created_at < latest_evidence_at:
            raise AnalystSnapshotError(
                "snapshot created_at cannot precede evidence bound into the snapshot"
            )

        payload = AnalystSnapshotPayload(
            spec_version=ANALYST_SNAPSHOT_SPEC_VERSION,
            snapshot_id=declaration.snapshot_id,
            created_at=declaration.created_at,
            collection_parameters_status=_COLLECTION_PARAMETERS_STATUS,
            effective_context=effective_context,
            search_page_limit=search_page_limit,
            comparable_sets=tuple(comparable_bindings),
            feed_runs=tuple(feed_bindings),
            rich_metadata=tuple(rich_bindings),
        )
        return AnalystSnapshotReport.model_validate(
            {
                **payload.model_dump(),
                "content_hash": _payload_hash(payload),
            }
        )


def validate_analyst_snapshot_report(
    report: AnalystSnapshotReport,
) -> AnalystSnapshotReport:
    validated = AnalystSnapshotReport.model_validate(report.model_dump())
    payload = AnalystSnapshotPayload.model_validate(
        validated.model_dump(exclude={"content_hash"})
    )
    if validated.content_hash != _payload_hash(payload):
        raise AnalystSnapshotError(
            "analyst snapshot content_hash does not match report content"
        )
    return validated


def _parse_rich_metadata(
    request_key: str,
    body: bytes,
) -> tuple[str, str, tuple[str, ...]]:
    if request_key == "catalogue.get_games":
        get_games_parser = YandexGetGamesParser()
        get_games = get_games_parser.parse(body)
        listing_ids = tuple(
            f"yandex_games:{game.app_id}" for game in get_games.games
        )
        return type(get_games_parser).__name__, get_games_parser.version, listing_ids
    if request_key == "game.page":
        play_page_parser = YandexPlayPageParser()
        play_page = play_page_parser.parse(body)
        listing_ids = (
            ()
            if play_page.app_id is None
            else (f"yandex_games:{play_page.app_id}",)
        )
        return type(play_page_parser).__name__, play_page_parser.version, listing_ids
    raise AnalystSnapshotError(f"unsupported rich metadata request_key: {request_key}")


def _payload_hash(payload: AnalystSnapshotPayload) -> str:
    encoded = json.dumps(
        payload.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _require_sha256(value: str, field_name: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 hex digest")


def _max_datetime(current: datetime | None, candidate: datetime) -> datetime:
    return candidate if current is None or candidate > current else current
