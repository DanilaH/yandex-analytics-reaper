from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from yandex_analytics_reaper.domain import (
    ComparableSetConstructionMethod,
    ComparableSetMember,
    ComparableSetMemberEvidence,
    ComparableSetRun,
    ComparableSetVersion,
    Platform,
    ProbeKind,
    ProbeRunStatus,
    QueryFamilyVersion,
    SessionProfile,
)
from yandex_analytics_reaper.sources.yandex.parsers import YandexFeedParser
from yandex_analytics_reaper.sources.yandex.probes import probe_page_from_yandex
from yandex_analytics_reaper.storage import FilesystemRawSnapshotStore, SQLiteProbeRunStore

_SOURCE_ID = "yandex_public"
_REQUEST_KEY = "catalogue.search"
_PARSER_NAME = "YandexFeedParser"
_PARSER_VERSION = "2"


class ComparableSetConstructionError(ValueError):
    """Explicit search evidence cannot form one valid provisional comparable set."""


class YandexSearchComparableSetBuilder:
    """Replay one exact query-family execution into an organic search union."""

    def __init__(
        self,
        *,
        raw_store: FilesystemRawSnapshotStore,
        probe_store: SQLiteProbeRunStore,
    ) -> None:
        self.raw_store = raw_store
        self.probe_store = probe_store

    def build(
        self,
        family: QueryFamilyVersion,
        run_ids: Sequence[str],
        *,
        set_id: str,
        version: int,
        created_at: datetime,
    ) -> ComparableSetVersion:
        if family.source_id != _SOURCE_ID:
            raise ComparableSetConstructionError(
                f"yandex_search_union_v1 requires query family source_id={_SOURCE_ID}"
            )
        normalized_run_ids = tuple(run_id.strip() for run_id in run_ids)
        if any(not run_id for run_id in normalized_run_ids):
            raise ComparableSetConstructionError("comparable-set run IDs cannot be blank")
        if len(set(normalized_run_ids)) != len(normalized_run_ids):
            raise ComparableSetConstructionError("comparable-set run IDs must be unique")
        if len(normalized_run_ids) != len(family.members):
            raise ComparableSetConstructionError(
                "comparable-set construction requires exactly one run per query-family member"
            )

        declared_queries = {
            member.query_text: ordinal for ordinal, member in enumerate(family.members)
        }
        records_by_query = {}
        expected_context = None
        expected_context_id: str | None = None
        requested_page_limit: int | None = None
        observed_from: datetime | None = None
        observed_to: datetime | None = None

        for run_id in normalized_run_ids:
            record = self.probe_store.get_run(run_id)
            if record is None:
                raise ComparableSetConstructionError(f"probe run does not exist: {run_id}")
            run = record.run
            context = record.context
            if run.source_id != _SOURCE_ID:
                raise ComparableSetConstructionError(
                    f"search run {run.id} does not use source_id={_SOURCE_ID}"
                )
            if run.request_key != _REQUEST_KEY or run.kind is not ProbeKind.SEARCH:
                raise ComparableSetConstructionError(
                    f"run {run.id} is not a {_REQUEST_KEY} search probe"
                )
            if run.status is not ProbeRunStatus.COMPLETED or run.completed_at is None:
                raise ComparableSetConstructionError(
                    f"search run {run.id} must have completed status"
                )
            query_text = run.query_text
            if query_text is None or query_text not in declared_queries:
                raise ComparableSetConstructionError(
                    f"search run {run.id} query_text is not declared by the query family"
                )
            if query_text in records_by_query:
                raise ComparableSetConstructionError(
                    f"multiple search runs were supplied for query_text={query_text!r}"
                )
            if context.language != family.language:
                raise ComparableSetConstructionError(
                    f"search run {run.id} language does not match query family"
                )
            if (
                context.session_profile is not SessionProfile.CLEAN_ANONYMOUS
                or context.session_instance_id is not None
                or context.cookie_state_hash is not None
                or context.profile_age_days != 0
                or context.country_observed is not None
                or context.collector_region is not None
            ):
                raise ComparableSetConstructionError(
                    "yandex_search_union_v1 requires clean anonymous runs with null region"
                )
            if expected_context is None:
                expected_context = context
                expected_context_id = run.context_id
                requested_page_limit = run.requested_page_limit
            else:
                if context != expected_context or run.context_id != expected_context_id:
                    raise ComparableSetConstructionError(
                        "all comparable-set search runs must share one exact ProbeContext"
                    )
                if run.requested_page_limit != requested_page_limit:
                    raise ComparableSetConstructionError(
                        "all comparable-set search runs must share requested_page_limit"
                    )

            page_count = len(record.pages)
            if not 1 <= page_count <= run.requested_page_limit:
                raise ComparableSetConstructionError(
                    f"search run {run.id} has invalid persisted page count"
                )
            if tuple(page.page_index for page in record.pages) != tuple(range(page_count)):
                raise ComparableSetConstructionError(
                    f"search run {run.id} pages are not contiguous from zero"
                )
            if page_count < run.requested_page_limit and record.pages[-1].has_next_page:
                raise ComparableSetConstructionError(
                    f"search run {run.id} stopped before its limit without source exhaustion"
                )

            records_by_query[query_text] = record
            observed_from = (
                run.started_at
                if observed_from is None or run.started_at < observed_from
                else observed_from
            )
            observed_to = (
                run.completed_at
                if observed_to is None or run.completed_at > observed_to
                else observed_to
            )

        missing_queries = set(declared_queries) - set(records_by_query)
        if missing_queries:
            raise ComparableSetConstructionError(
                "missing search runs for query-family members: "
                + ", ".join(sorted(missing_queries))
            )
        if expected_context_id is None or requested_page_limit is None:
            raise RuntimeError("validated comparable-set run cohort unexpectedly became empty")
        if observed_from is None or observed_to is None:
            raise RuntimeError("validated comparable-set observation interval is missing")

        parser = YandexFeedParser()
        if parser.version != _PARSER_VERSION:
            raise ComparableSetConstructionError(
                f"yandex_search_union_v1 requires {_PARSER_NAME}@{_PARSER_VERSION}; "
                f"current parser is @{parser.version}"
            )

        member_ids: list[str] = []
        seen_members: set[str] = set()
        evidence: list[ComparableSetMemberEvidence] = []
        run_refs: list[ComparableSetRun] = []

        for query_ordinal, family_member in enumerate(family.members):
            record = records_by_query[family_member.query_text]
            run = record.run
            run_refs.append(
                ComparableSetRun(
                    query_ordinal=query_ordinal,
                    query_text=family_member.query_text,
                    probe_run_id=run.id,
                )
            )
            for page in record.pages:
                try:
                    metadata = self.raw_store.get_metadata(
                        run.source_id,
                        page.raw_snapshot_id,
                    )
                    body = self.raw_store.get_body(run.source_id, page.raw_snapshot_id)
                except (OSError, ValueError) as exc:
                    raise ComparableSetConstructionError(
                        f"raw replay failed for {run.id} page {page.page_index}: {exc}"
                    ) from exc
                if metadata.request_key != _REQUEST_KEY:
                    raise ComparableSetConstructionError(
                        f"raw page for {run.id} does not use request_key={_REQUEST_KEY}"
                    )
                if not 200 <= metadata.http_status < 300:
                    raise ComparableSetConstructionError(
                        f"raw page for {run.id} does not have successful HTTP status"
                    )
                try:
                    parsed = parser.parse(body)
                    replayed_page = probe_page_from_yandex(
                        run=run,
                        context=record.context,
                        metadata=metadata,
                        page_index=page.page_index,
                        page_info=parsed.page_info,
                    )
                except ValueError as exc:
                    raise ComparableSetConstructionError(
                        f"raw page for {run.id} cannot be replayed consistently: {exc}"
                    ) from exc
                if replayed_page != page:
                    raise ComparableSetConstructionError(
                        f"replayed page for {run.id}[{page.page_index}] does not match storage"
                    )

                for card in parsed.games:
                    if card.sponsored:
                        continue
                    if card.source_object_path is None:
                        raise ComparableSetConstructionError(
                            "parsed organic search card is missing source_object_path"
                        )
                    listing_id = f"{Platform.YANDEX_GAMES.value}:{card.app_id}"
                    evidence.append(
                        ComparableSetMemberEvidence(
                            platform_listing_id=listing_id,
                            probe_run_id=run.id,
                            raw_snapshot_id=metadata.id,
                            page_index=page.page_index,
                            source_object_path=card.source_object_path,
                        )
                    )
                    if listing_id not in seen_members:
                        seen_members.add(listing_id)
                        member_ids.append(listing_id)

        members = tuple(
            ComparableSetMember(ordinal=ordinal, platform_listing_id=listing_id)
            for ordinal, listing_id in enumerate(member_ids)
        )
        return ComparableSetVersion(
            set_id=set_id,
            version=version,
            construction_method=ComparableSetConstructionMethod.YANDEX_SEARCH_UNION_V1,
            query_family_id=family.family_id,
            query_family_version=family.version,
            source_id=family.source_id,
            language=family.language,
            context_id=expected_context_id,
            requested_page_limit=requested_page_limit,
            parser_name=_PARSER_NAME,
            parser_version=_PARSER_VERSION,
            observed_from=observed_from,
            observed_to=observed_to,
            created_at=created_at,
            runs=tuple(run_refs),
            members=members,
            evidence=tuple(evidence),
        )
