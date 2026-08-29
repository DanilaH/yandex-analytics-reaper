from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from yandex_analytics_reaper.domain import (
    ComparableSetConstructionMethod,
    ComparableSetMember,
    ComparableSetMemberEvidence,
    ComparableSetRun,
    ComparableSetVersion,
    ProbeKind,
    ProbeRunStatus,
    SessionProfile,
)

from .sqlite import SQLiteDatabase

_YANDEX_SOURCE_ID = "yandex_public"
_YANDEX_SEARCH_REQUEST_KEY = "catalogue.search"
_YANDEX_PARSER_NAME = "YandexFeedParser"
_YANDEX_PARSER_VERSION = "2"


class ComparableSetStore(Protocol):
    def persist(self, comparable_set: ComparableSetVersion) -> ComparableSetVersion: ...

    def get(self, set_id: str, version: int) -> ComparableSetVersion | None: ...

    def latest(self, set_id: str) -> ComparableSetVersion | None: ...


class SQLiteComparableSetStore:
    """Immutable persistence for reproducible comparable-set versions."""

    def __init__(self, path: Path) -> None:
        self.database = SQLiteDatabase(path)

    @property
    def path(self) -> Path:
        return self.database.path

    def persist(self, comparable_set: ComparableSetVersion) -> ComparableSetVersion:
        with self.database.connect() as connection:
            self._validate_references(connection, comparable_set)
            existing = self._load(connection, comparable_set.set_id, comparable_set.version)
            if existing is not None:
                if existing != comparable_set:
                    raise ValueError(
                        "conflicting comparable-set content for existing set_id/version"
                    )
                return existing

            connection.execute(
                """
                INSERT INTO comparable_set_versions (
                    set_id,
                    version,
                    construction_method,
                    query_family_id,
                    query_family_version,
                    source_id,
                    language,
                    context_id,
                    requested_page_limit,
                    parser_name,
                    parser_version,
                    observed_from,
                    observed_to,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    comparable_set.set_id,
                    comparable_set.version,
                    comparable_set.construction_method.value,
                    comparable_set.query_family_id,
                    comparable_set.query_family_version,
                    comparable_set.source_id,
                    comparable_set.language,
                    comparable_set.context_id,
                    comparable_set.requested_page_limit,
                    comparable_set.parser_name,
                    comparable_set.parser_version,
                    _timestamp(comparable_set.observed_from),
                    _timestamp(comparable_set.observed_to),
                    _timestamp(comparable_set.created_at),
                ),
            )
            connection.executemany(
                """
                INSERT INTO comparable_set_runs (
                    set_id,
                    version,
                    query_ordinal,
                    query_text,
                    probe_run_id
                ) VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        comparable_set.set_id,
                        comparable_set.version,
                        run.query_ordinal,
                        run.query_text,
                        run.probe_run_id,
                    )
                    for run in comparable_set.runs
                ],
            )
            connection.executemany(
                """
                INSERT INTO comparable_set_members (
                    set_id,
                    version,
                    ordinal,
                    platform_listing_id
                ) VALUES (?, ?, ?, ?)
                """,
                [
                    (
                        comparable_set.set_id,
                        comparable_set.version,
                        member.ordinal,
                        member.platform_listing_id,
                    )
                    for member in comparable_set.members
                ],
            )
            connection.executemany(
                """
                INSERT INTO comparable_set_member_evidence (
                    set_id,
                    version,
                    evidence_ordinal,
                    platform_listing_id,
                    probe_run_id,
                    raw_snapshot_id,
                    page_index,
                    source_object_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        comparable_set.set_id,
                        comparable_set.version,
                        evidence_ordinal,
                        item.platform_listing_id,
                        item.probe_run_id,
                        item.raw_snapshot_id,
                        item.page_index,
                        item.source_object_path,
                    )
                    for evidence_ordinal, item in enumerate(comparable_set.evidence)
                ],
            )

            stored = self._load(connection, comparable_set.set_id, comparable_set.version)
            if stored is None:
                raise RuntimeError("comparable-set version was not persisted")
            if stored != comparable_set:
                raise RuntimeError("persisted comparable-set version does not round-trip exactly")
            return stored

    def get(self, set_id: str, version: int) -> ComparableSetVersion | None:
        identity = _identity(set_id, version)
        with self.database.connect() as connection:
            return self._load(connection, identity[0], identity[1])

    def latest(self, set_id: str) -> ComparableSetVersion | None:
        normalized_id = _set_id(set_id)
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT version
                FROM comparable_set_versions
                WHERE set_id = ?
                ORDER BY version DESC
                LIMIT 1
                """,
                (normalized_id,),
            ).fetchone()
            if row is None:
                return None
            return self._load(connection, normalized_id, int(row["version"]))

    @staticmethod
    def _validate_references(
        connection: sqlite3.Connection,
        comparable_set: ComparableSetVersion,
    ) -> None:
        if comparable_set.construction_method is ComparableSetConstructionMethod.YANDEX_SEARCH_UNION_V1:
            if (
                comparable_set.source_id != _YANDEX_SOURCE_ID
                or comparable_set.parser_name != _YANDEX_PARSER_NAME
                or comparable_set.parser_version != _YANDEX_PARSER_VERSION
            ):
                raise ValueError(
                    "yandex_search_union_v1 requires frozen Yandex source/parser semantics"
                )

        family_row = connection.execute(
            """
            SELECT source_id, language
            FROM query_family_versions
            WHERE family_id = ? AND version = ?
            """,
            (comparable_set.query_family_id, comparable_set.query_family_version),
        ).fetchone()
        if family_row is None:
            raise ValueError("referenced query-family version is not persisted")
        if (
            str(family_row["source_id"]) != comparable_set.source_id
            or str(family_row["language"]) != comparable_set.language
        ):
            raise ValueError("comparable-set source/language disagrees with query family")

        family_members = connection.execute(
            """
            SELECT ordinal, query_text
            FROM query_family_members
            WHERE family_id = ? AND version = ?
            ORDER BY ordinal
            """,
            (comparable_set.query_family_id, comparable_set.query_family_version),
        ).fetchall()
        expected_queries = tuple(
            (int(row["ordinal"]), str(row["query_text"])) for row in family_members
        )
        actual_queries = tuple(
            (run.query_ordinal, run.query_text) for run in comparable_set.runs
        )
        if actual_queries != expected_queries:
            raise ValueError(
                "comparable-set runs do not exactly match persisted query-family membership"
            )

        context_row = connection.execute(
            """
            SELECT
                language,
                country_observed,
                collector_region,
                session_profile,
                session_instance_id,
                cookie_state_hash,
                profile_age_days
            FROM probe_contexts
            WHERE id = ?
            """,
            (comparable_set.context_id,),
        ).fetchone()
        if context_row is None:
            raise ValueError("referenced comparable-set ProbeContext is not persisted")
        if (
            str(context_row["language"]) != comparable_set.language
            or context_row["country_observed"] is not None
            or context_row["collector_region"] is not None
            or str(context_row["session_profile"]) != SessionProfile.CLEAN_ANONYMOUS.value
            or context_row["session_instance_id"] is not None
            or context_row["cookie_state_hash"] is not None
            or int(context_row["profile_age_days"]) != 0
        ):
            raise ValueError(
                "yandex_search_union_v1 requires one persisted clean-anonymous null-region context"
            )

        starts: list[datetime] = []
        completions: list[datetime] = []
        for run in comparable_set.runs:
            row = connection.execute(
                """
                SELECT
                    source_id,
                    request_key,
                    probe_kind,
                    context_id,
                    query_text,
                    requested_page_limit,
                    started_at,
                    completed_at,
                    status
                FROM probe_runs
                WHERE id = ?
                """,
                (run.probe_run_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"referenced probe run is not persisted: {run.probe_run_id}")
            if (
                str(row["source_id"]) != comparable_set.source_id
                or str(row["request_key"]) != _YANDEX_SEARCH_REQUEST_KEY
                or str(row["probe_kind"]) != ProbeKind.SEARCH.value
                or str(row["context_id"]) != comparable_set.context_id
                or str(row["query_text"]) != run.query_text
                or int(row["requested_page_limit"]) != comparable_set.requested_page_limit
                or str(row["status"]) != ProbeRunStatus.COMPLETED.value
                or row["completed_at"] is None
            ):
                raise ValueError(
                    f"probe run {run.probe_run_id} disagrees with comparable-set metadata"
                )
            starts.append(_parse_timestamp(str(row["started_at"])))
            completions.append(_parse_timestamp(str(row["completed_at"])))

        if min(starts) != comparable_set.observed_from:
            raise ValueError("comparable-set observed_from does not match referenced runs")
        if max(completions) != comparable_set.observed_to:
            raise ValueError("comparable-set observed_to does not match referenced runs")

        for item in comparable_set.evidence:
            page = connection.execute(
                """
                SELECT source_id, raw_snapshot_id
                FROM probe_pages
                WHERE run_id = ? AND page_index = ?
                """,
                (item.probe_run_id, item.page_index),
            ).fetchone()
            if page is None:
                raise ValueError(
                    "comparable-set evidence references a missing persisted probe page"
                )
            if (
                str(page["source_id"]) != comparable_set.source_id
                or str(page["raw_snapshot_id"]) != item.raw_snapshot_id
            ):
                raise ValueError(
                    "comparable-set evidence raw snapshot disagrees with persisted probe page"
                )

    @staticmethod
    def _load(
        connection: sqlite3.Connection,
        set_id: str,
        version: int,
    ) -> ComparableSetVersion | None:
        row = connection.execute(
            """
            SELECT
                set_id,
                version,
                construction_method,
                query_family_id,
                query_family_version,
                source_id,
                language,
                context_id,
                requested_page_limit,
                parser_name,
                parser_version,
                observed_from,
                observed_to,
                created_at
            FROM comparable_set_versions
            WHERE set_id = ? AND version = ?
            """,
            (set_id, version),
        ).fetchone()
        if row is None:
            return None

        run_rows = connection.execute(
            """
            SELECT query_ordinal, query_text, probe_run_id
            FROM comparable_set_runs
            WHERE set_id = ? AND version = ?
            ORDER BY query_ordinal
            """,
            (set_id, version),
        ).fetchall()
        run_ordinals = tuple(int(item["query_ordinal"]) for item in run_rows)
        if run_ordinals != tuple(range(len(run_rows))):
            raise RuntimeError("stored comparable-set query ordinals are not contiguous")

        member_rows = connection.execute(
            """
            SELECT ordinal, platform_listing_id
            FROM comparable_set_members
            WHERE set_id = ? AND version = ?
            ORDER BY ordinal
            """,
            (set_id, version),
        ).fetchall()
        member_ordinals = tuple(int(item["ordinal"]) for item in member_rows)
        if member_ordinals != tuple(range(len(member_rows))):
            raise RuntimeError("stored comparable-set member ordinals are not contiguous")

        evidence_rows = connection.execute(
            """
            SELECT
                evidence_ordinal,
                platform_listing_id,
                probe_run_id,
                raw_snapshot_id,
                page_index,
                source_object_path
            FROM comparable_set_member_evidence
            WHERE set_id = ? AND version = ?
            ORDER BY evidence_ordinal
            """,
            (set_id, version),
        ).fetchall()
        evidence_ordinals = tuple(int(item["evidence_ordinal"]) for item in evidence_rows)
        if evidence_ordinals != tuple(range(len(evidence_rows))):
            raise RuntimeError("stored comparable-set evidence ordinals are not contiguous")

        try:
            comparable_set = ComparableSetVersion(
                set_id=str(row["set_id"]),
                version=int(row["version"]),
                construction_method=ComparableSetConstructionMethod(
                    str(row["construction_method"])
                ),
                query_family_id=str(row["query_family_id"]),
                query_family_version=int(row["query_family_version"]),
                source_id=str(row["source_id"]),
                language=str(row["language"]),
                context_id=str(row["context_id"]),
                requested_page_limit=int(row["requested_page_limit"]),
                parser_name=str(row["parser_name"]),
                parser_version=str(row["parser_version"]),
                observed_from=_parse_timestamp(str(row["observed_from"])),
                observed_to=_parse_timestamp(str(row["observed_to"])),
                created_at=_parse_timestamp(str(row["created_at"])),
                runs=tuple(
                    ComparableSetRun(
                        query_ordinal=int(item["query_ordinal"]),
                        query_text=str(item["query_text"]),
                        probe_run_id=str(item["probe_run_id"]),
                    )
                    for item in run_rows
                ),
                members=tuple(
                    ComparableSetMember(
                        ordinal=int(item["ordinal"]),
                        platform_listing_id=str(item["platform_listing_id"]),
                    )
                    for item in member_rows
                ),
                evidence=tuple(
                    ComparableSetMemberEvidence(
                        platform_listing_id=str(item["platform_listing_id"]),
                        probe_run_id=str(item["probe_run_id"]),
                        raw_snapshot_id=str(item["raw_snapshot_id"]),
                        page_index=int(item["page_index"]),
                        source_object_path=str(item["source_object_path"]),
                    )
                    for item in evidence_rows
                ),
            )
        except (TypeError, ValueError) as exc:
            raise RuntimeError("stored comparable-set version is invalid") from exc

        try:
            SQLiteComparableSetStore._validate_references(connection, comparable_set)
        except (TypeError, ValueError) as exc:
            raise RuntimeError("stored comparable-set provenance is invalid") from exc
        return comparable_set


def _identity(set_id: str, version: int) -> tuple[str, int]:
    normalized_id = _set_id(set_id)
    if version < 1:
        raise ValueError("comparable-set version must be at least 1")
    return normalized_id, version


def _set_id(value: str) -> str:
    if not value:
        raise ValueError("set_id cannot be blank")
    if value != value.strip():
        raise ValueError("set_id must already be trimmed")
    return value


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("comparable-set timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
