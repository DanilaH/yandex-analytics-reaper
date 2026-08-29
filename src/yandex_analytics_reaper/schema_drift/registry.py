from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from yandex_analytics_reaper.storage import RawSnapshotMetadata
from yandex_analytics_reaper.storage.sqlite import SQLiteDatabase

from .models import (
    DriftEvent,
    DriftKind,
    DriftSeverity,
    FieldProfile,
    JsonValueType,
    SchemaAnalysis,
    SchemaContract,
    SchemaProfile,
    SchemaProfileStatus,
)
from .profiler import profile_json_snapshot

ANALYZER_VERSION = "2"
_MISSINGNESS_DELTA_THRESHOLD = 0.25
_MIN_MISSINGNESS_SAMPLE = 4


class SQLiteSchemaDriftRegistry:
    """Versioned raw-schema profiler and drift/event registry."""

    def __init__(self, path: Path) -> None:
        self.database = SQLiteDatabase(path)

    def observe_json(
        self,
        metadata: RawSnapshotMetadata,
        body: bytes,
        *,
        comparison_scope_id: str,
        contract: SchemaContract | None = None,
    ) -> SchemaAnalysis:
        scope_id = _require_non_blank(comparison_scope_id, "comparison_scope_id")
        if contract is not None and contract.request_key != metadata.request_key:
            raise ValueError("schema contract request_key does not match raw snapshot")
        _require_body_matches_metadata(metadata, body)

        contract_id = contract.contract_id if contract is not None else "uncontracted"
        analysis_id = _analysis_id(metadata.id, ANALYZER_VERSION, contract_id, scope_id)
        with self.database.connect() as connection:
            existing = self._load_analysis(connection, analysis_id)
            if existing is not None:
                _assert_analysis_matches_metadata(existing, metadata, scope_id)
                return existing

            profile = profile_json_snapshot(metadata, body)
            previous = self._previous_profile(
                connection,
                profile,
                analyzer_version=ANALYZER_VERSION,
                contract_id=contract_id,
                comparison_scope_id=scope_id,
            )
            analysis = SchemaAnalysis(
                analysis_id=analysis_id,
                analyzer_version=ANALYZER_VERSION,
                contract_id=contract_id,
                comparison_scope_id=scope_id,
                profile=profile,
                events=_evaluate(
                    analysis_id=analysis_id,
                    current=profile,
                    previous=previous,
                    contract=contract,
                ),
            )
            self._persist_analysis(connection, analysis)
            stored = self._load_analysis(connection, analysis_id)
            if stored is None:
                raise RuntimeError("schema analysis was not persisted")
            return stored

    def record_parser_failure(
        self,
        metadata: RawSnapshotMetadata,
        *,
        comparison_scope_id: str,
        parser_name: str,
        parser_version: str,
        error: str,
    ) -> SchemaAnalysis:
        scope_id = _require_non_blank(comparison_scope_id, "comparison_scope_id")
        parser_name = _require_non_blank(parser_name, "parser_name")
        parser_version = _require_non_blank(parser_version, "parser_version")
        error = _require_non_blank(error, "error")

        contract_id = f"parser:{parser_name}:{parser_version}"
        analysis_id = _analysis_id(metadata.id, ANALYZER_VERSION, contract_id, scope_id)
        profile = SchemaProfile(
            raw_snapshot_id=metadata.id,
            source_id=metadata.source_id,
            request_key=metadata.request_key,
            retrieved_at=metadata.retrieved_at,
            content_hash=metadata.content_hash,
            schema_hash=metadata.schema_hash,
            status=SchemaProfileStatus.NOT_PROFILED,
        )
        event = _make_event(
            analysis_id=analysis_id,
            raw_snapshot_id=metadata.id,
            kind=DriftKind.PARSER_FAILURE,
            severity=DriftSeverity.BREAKING,
            details={"parser_name": parser_name, "parser_version": parser_version},
            message=f"{parser_name}@{parser_version} failed to parse raw snapshot: {error}",
        )
        analysis = SchemaAnalysis(
            analysis_id=analysis_id,
            analyzer_version=ANALYZER_VERSION,
            contract_id=contract_id,
            comparison_scope_id=scope_id,
            profile=profile,
            events=(event,),
        )
        with self.database.connect() as connection:
            existing = self._load_analysis(connection, analysis_id)
            if existing is not None:
                _assert_analysis_matches_metadata(existing, metadata, scope_id)
                if existing != analysis:
                    raise ValueError("conflicting parser-failure analysis for the same identity")
                return existing
            self._persist_analysis(connection, analysis)
            return analysis

    def analyses_for_snapshot(self, raw_snapshot_id: str) -> tuple[SchemaAnalysis, ...]:
        snapshot_id = _require_non_blank(raw_snapshot_id, "raw_snapshot_id")
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT id
                FROM schema_observations
                WHERE raw_snapshot_id = ?
                ORDER BY analyzer_version, contract_id, comparison_scope_id, id
                """,
                (snapshot_id,),
            ).fetchall()
            analyses = [self._load_analysis(connection, str(row["id"])) for row in rows]
        return tuple(item for item in analyses if item is not None)

    def _previous_profile(
        self,
        connection: sqlite3.Connection,
        current: SchemaProfile,
        *,
        analyzer_version: str,
        contract_id: str,
        comparison_scope_id: str,
    ) -> SchemaProfile | None:
        row = connection.execute(
            """
            SELECT id
            FROM schema_observations
            WHERE source_id = ?
              AND request_key = ?
              AND analyzer_version = ?
              AND contract_id = ?
              AND comparison_scope_id = ?
              AND profile_status = ?
              AND retrieved_at < ?
            ORDER BY retrieved_at DESC, raw_snapshot_id DESC
            LIMIT 1
            """,
            (
                current.source_id,
                current.request_key,
                analyzer_version,
                contract_id,
                comparison_scope_id,
                SchemaProfileStatus.PROFILED.value,
                _timestamp(current.retrieved_at),
            ),
        ).fetchone()
        if row is None:
            return None
        analysis = self._load_analysis(connection, str(row["id"]))
        return None if analysis is None else analysis.profile

    @staticmethod
    def _persist_analysis(connection: sqlite3.Connection, analysis: SchemaAnalysis) -> None:
        profile = analysis.profile
        connection.execute(
            """
            INSERT INTO schema_observations (
                id,
                raw_snapshot_id,
                analyzer_version,
                contract_id,
                comparison_scope_id,
                source_id,
                request_key,
                retrieved_at,
                content_hash,
                schema_hash,
                profile_status,
                root_type,
                error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                analysis.analysis_id,
                profile.raw_snapshot_id,
                analysis.analyzer_version,
                analysis.contract_id,
                analysis.comparison_scope_id,
                profile.source_id,
                profile.request_key,
                _timestamp(profile.retrieved_at),
                profile.content_hash,
                profile.schema_hash,
                profile.status.value,
                profile.root_type.value if profile.root_type is not None else None,
                profile.error,
            ),
        )
        connection.executemany(
            """
            INSERT INTO schema_field_profiles (
                schema_observation_id,
                field_path,
                value_types_json,
                present_count,
                parent_count,
                presence_ratio
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    analysis.analysis_id,
                    field.path,
                    _types_json(field.value_types),
                    field.present_count,
                    field.parent_count,
                    field.presence_ratio,
                )
                for field in profile.fields
            ],
        )
        connection.executemany(
            """
            INSERT INTO schema_drift_events (
                id,
                schema_observation_id,
                raw_snapshot_id,
                kind,
                severity,
                field_path,
                previous_types_json,
                current_types_json,
                previous_presence_ratio,
                current_presence_ratio,
                details_json,
                message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    event.event_id,
                    analysis.analysis_id,
                    event.raw_snapshot_id,
                    event.kind.value,
                    event.severity.value,
                    event.field_path,
                    _types_json(event.previous_types),
                    _types_json(event.current_types),
                    event.previous_presence_ratio,
                    event.current_presence_ratio,
                    json.dumps(event.details, sort_keys=True, separators=(",", ":")),
                    event.message,
                )
                for event in analysis.events
            ],
        )

    @staticmethod
    def _load_analysis(
        connection: sqlite3.Connection,
        analysis_id: str,
    ) -> SchemaAnalysis | None:
        row = connection.execute(
            "SELECT * FROM schema_observations WHERE id = ?",
            (analysis_id,),
        ).fetchone()
        if row is None:
            return None
        field_rows = connection.execute(
            """
            SELECT *
            FROM schema_field_profiles
            WHERE schema_observation_id = ?
            ORDER BY field_path
            """,
            (analysis_id,),
        ).fetchall()
        event_rows = connection.execute(
            """
            SELECT *
            FROM schema_drift_events
            WHERE schema_observation_id = ?
            ORDER BY
                CASE severity
                    WHEN 'breaking' THEN 3
                    WHEN 'warning' THEN 2
                    WHEN 'info' THEN 1
                    ELSE 0
                END DESC,
                kind,
                COALESCE(field_path, ''),
                id
            """,
            (analysis_id,),
        ).fetchall()
        profile = SchemaProfile(
            raw_snapshot_id=str(row["raw_snapshot_id"]),
            source_id=str(row["source_id"]),
            request_key=str(row["request_key"]),
            retrieved_at=_parse_timestamp(str(row["retrieved_at"])),
            content_hash=str(row["content_hash"]),
            schema_hash=_optional_str(row["schema_hash"]),
            status=SchemaProfileStatus(str(row["profile_status"])),
            root_type=(
                None if row["root_type"] is None else JsonValueType(str(row["root_type"]))
            ),
            fields=tuple(_field_from_row(item) for item in field_rows),
            error=_optional_str(row["error"]),
        )
        return SchemaAnalysis(
            analysis_id=str(row["id"]),
            analyzer_version=str(row["analyzer_version"]),
            contract_id=str(row["contract_id"]),
            comparison_scope_id=str(row["comparison_scope_id"]),
            profile=profile,
            events=tuple(_event_from_row(item) for item in event_rows),
        )


def _evaluate(
    *,
    analysis_id: str,
    current: SchemaProfile,
    previous: SchemaProfile | None,
    contract: SchemaContract | None,
) -> tuple[DriftEvent, ...]:
    events: dict[tuple[DriftKind, str | None], DriftEvent] = {}

    def add(event: DriftEvent) -> None:
        key = (event.kind, event.field_path)
        existing = events.get(key)
        if existing is None or _severity_rank(event.severity) > _severity_rank(existing.severity):
            events[key] = event

    if current.status is SchemaProfileStatus.PARSE_FAILED:
        add(
            _make_event(
                analysis_id=analysis_id,
                raw_snapshot_id=current.raw_snapshot_id,
                kind=DriftKind.RAW_PARSE_FAILURE,
                severity=DriftSeverity.BREAKING,
                message=f"raw JSON could not be profiled: {current.error or 'unknown error'}",
            )
        )
        return _sorted_events(events.values())

    current_fields = {item.path: item for item in current.fields}
    if contract is not None:
        if current.root_type not in contract.allowed_root_types:
            add(
                _make_event(
                    analysis_id=analysis_id,
                    raw_snapshot_id=current.raw_snapshot_id,
                    kind=DriftKind.ROOT_TYPE_MISMATCH,
                    severity=DriftSeverity.BREAKING,
                    current_types=((current.root_type,) if current.root_type is not None else ()),
                    message=f"root type {current.root_type} violates contract {contract.contract_id}",
                )
            )
        for expectation in contract.fields:
            field = current_fields.get(expectation.path)
            if field is None:
                parent_path = _parent_path(expectation.path)
                parent_observed = parent_path is not None and parent_path in current_fields
                ratio_requires_presence = (
                    expectation.minimum_presence_ratio is not None
                    and expectation.minimum_presence_ratio > 0.0
                    and parent_observed
                )
                if expectation.required or ratio_requires_presence:
                    add(
                        _make_event(
                            analysis_id=analysis_id,
                            raw_snapshot_id=current.raw_snapshot_id,
                            kind=DriftKind.REQUIRED_FIELD_MISSING,
                            severity=DriftSeverity.BREAKING,
                            field_path=expectation.path,
                            current_presence_ratio=(0.0 if parent_observed else None),
                            message=f"required field {expectation.path} is missing",
                        )
                    )
                continue
            unexpected_types = set(field.value_types) - set(expectation.allowed_types)
            if unexpected_types:
                add(
                    _make_event(
                        analysis_id=analysis_id,
                        raw_snapshot_id=current.raw_snapshot_id,
                        kind=DriftKind.CONTRACT_TYPE_MISMATCH,
                        severity=DriftSeverity.BREAKING,
                        field_path=expectation.path,
                        current_types=field.value_types,
                        details={
                            "allowed_types": ",".join(item.value for item in expectation.allowed_types)
                        },
                        message=f"field {expectation.path} has a type outside its contract",
                    )
                )
            if (
                expectation.minimum_presence_ratio is not None
                and field.presence_ratio < expectation.minimum_presence_ratio
            ):
                add(
                    _make_event(
                        analysis_id=analysis_id,
                        raw_snapshot_id=current.raw_snapshot_id,
                        kind=DriftKind.REQUIRED_FIELD_MISSING,
                        severity=DriftSeverity.BREAKING,
                        field_path=expectation.path,
                        current_presence_ratio=field.presence_ratio,
                        details={
                            "minimum_presence_ratio": str(expectation.minimum_presence_ratio)
                        },
                        message=f"field {expectation.path} fell below required presence ratio",
                    )
                )

    if previous is not None and previous.status is SchemaProfileStatus.PROFILED:
        previous_fields = {item.path: item for item in previous.fields}
        for path, field in current_fields.items():
            old = previous_fields.get(path)
            if old is None:
                add(
                    _make_event(
                        analysis_id=analysis_id,
                        raw_snapshot_id=current.raw_snapshot_id,
                        kind=DriftKind.NEW_FIELD,
                        severity=DriftSeverity.INFO,
                        field_path=path,
                        current_types=field.value_types,
                        current_presence_ratio=field.presence_ratio,
                        message=f"new field observed: {path}",
                    )
                )
                continue
            if set(old.value_types) != set(field.value_types):
                add(
                    _make_event(
                        analysis_id=analysis_id,
                        raw_snapshot_id=current.raw_snapshot_id,
                        kind=DriftKind.TYPE_CHANGED,
                        severity=DriftSeverity.WARNING,
                        field_path=path,
                        previous_types=old.value_types,
                        current_types=field.value_types,
                        message=f"observed JSON types changed for {path}",
                    )
                )
            if (
                old.parent_count >= _MIN_MISSINGNESS_SAMPLE
                and field.parent_count >= _MIN_MISSINGNESS_SAMPLE
                and abs(old.presence_ratio - field.presence_ratio)
                >= _MISSINGNESS_DELTA_THRESHOLD
            ):
                add(
                    _make_event(
                        analysis_id=analysis_id,
                        raw_snapshot_id=current.raw_snapshot_id,
                        kind=DriftKind.MISSINGNESS_CHANGED,
                        severity=DriftSeverity.WARNING,
                        field_path=path,
                        previous_presence_ratio=old.presence_ratio,
                        current_presence_ratio=field.presence_ratio,
                        message=f"field presence changed materially for {path}",
                    )
                )

        for path, old in previous_fields.items():
            if path not in current_fields:
                add(
                    _make_event(
                        analysis_id=analysis_id,
                        raw_snapshot_id=current.raw_snapshot_id,
                        kind=DriftKind.REMOVED_FIELD,
                        severity=DriftSeverity.WARNING,
                        field_path=path,
                        previous_types=old.value_types,
                        previous_presence_ratio=old.presence_ratio,
                        message=f"previously observed field disappeared: {path}",
                    )
                )

        if previous.root_type != current.root_type:
            add(
                _make_event(
                    analysis_id=analysis_id,
                    raw_snapshot_id=current.raw_snapshot_id,
                    kind=DriftKind.ROOT_TYPE_MISMATCH,
                    severity=DriftSeverity.BREAKING,
                    previous_types=((previous.root_type,) if previous.root_type else ()),
                    current_types=((current.root_type,) if current.root_type else ()),
                    message="raw JSON root type changed",
                )
            )

    return _sorted_events(events.values())


def _analysis_id(
    raw_snapshot_id: str,
    analyzer_version: str,
    contract_id: str,
    comparison_scope_id: str,
) -> str:
    payload = (
        f"{raw_snapshot_id}\0{analyzer_version}\0{contract_id}\0{comparison_scope_id}"
    ).encode()
    return "schema:" + hashlib.sha256(payload).hexdigest()[:32]


def _make_event(
    *,
    analysis_id: str,
    raw_snapshot_id: str,
    kind: DriftKind,
    severity: DriftSeverity,
    message: str,
    field_path: str | None = None,
    previous_types: tuple[JsonValueType, ...] = (),
    current_types: tuple[JsonValueType, ...] = (),
    previous_presence_ratio: float | None = None,
    current_presence_ratio: float | None = None,
    details: dict[str, str] | None = None,
) -> DriftEvent:
    identity = json.dumps(
        {
            "analysis_id": analysis_id,
            "kind": kind.value,
            "field_path": field_path,
            "message": message,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return DriftEvent(
        event_id="drift:" + hashlib.sha256(identity).hexdigest()[:32],
        raw_snapshot_id=raw_snapshot_id,
        kind=kind,
        severity=severity,
        field_path=field_path,
        previous_types=previous_types,
        current_types=current_types,
        previous_presence_ratio=previous_presence_ratio,
        current_presence_ratio=current_presence_ratio,
        details=details or {},
        message=message,
    )


def _sorted_events(events: Iterable[DriftEvent]) -> tuple[DriftEvent, ...]:
    return tuple(
        sorted(
            events,
            key=lambda item: (
                -_severity_rank(item.severity),
                item.kind.value,
                item.field_path or "",
                item.event_id,
            ),
        )
    )


def _parent_path(path: str) -> str | None:
    if path == "$" or "." not in path:
        return None
    return path.rsplit(".", 1)[0]


def _field_from_row(row: sqlite3.Row) -> FieldProfile:
    return FieldProfile(
        path=str(row["field_path"]),
        value_types=_types_from_json(row["value_types_json"]),
        present_count=int(row["present_count"]),
        parent_count=int(row["parent_count"]),
        presence_ratio=float(row["presence_ratio"]),
    )


def _event_from_row(row: sqlite3.Row) -> DriftEvent:
    details_raw = json.loads(str(row["details_json"]))
    if not isinstance(details_raw, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in details_raw.items()
    ):
        raise ValueError("stored schema drift details_json is invalid")
    return DriftEvent(
        event_id=str(row["id"]),
        raw_snapshot_id=str(row["raw_snapshot_id"]),
        kind=DriftKind(str(row["kind"])),
        severity=DriftSeverity(str(row["severity"])),
        field_path=_optional_str(row["field_path"]),
        previous_types=_types_from_json(row["previous_types_json"]),
        current_types=_types_from_json(row["current_types_json"]),
        previous_presence_ratio=_optional_float(row["previous_presence_ratio"]),
        current_presence_ratio=_optional_float(row["current_presence_ratio"]),
        details={str(key): str(value) for key, value in details_raw.items()},
        message=str(row["message"]),
    )


def _types_json(types: tuple[JsonValueType, ...]) -> str:
    return json.dumps(sorted(item.value for item in types), separators=(",", ":"))


def _types_from_json(value: object) -> tuple[JsonValueType, ...]:
    parsed = json.loads(str(value))
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        raise ValueError("stored JSON type list is invalid")
    return tuple(JsonValueType(item) for item in parsed)


def _severity_rank(severity: DriftSeverity) -> int:
    return {
        DriftSeverity.INFO: 1,
        DriftSeverity.WARNING: 2,
        DriftSeverity.BREAKING: 3,
    }[severity]


def _require_body_matches_metadata(metadata: RawSnapshotMetadata, body: bytes) -> None:
    if hashlib.sha256(body).hexdigest() != metadata.content_hash:
        raise ValueError("raw body content hash does not match snapshot metadata")


def _assert_analysis_matches_metadata(
    analysis: SchemaAnalysis,
    metadata: RawSnapshotMetadata,
    comparison_scope_id: str,
) -> None:
    profile = analysis.profile
    if (
        profile.raw_snapshot_id != metadata.id
        or profile.source_id != metadata.source_id
        or profile.request_key != metadata.request_key
        or profile.retrieved_at != metadata.retrieved_at
        or profile.content_hash != metadata.content_hash
        or profile.schema_hash != metadata.schema_hash
        or analysis.comparison_scope_id != comparison_scope_id
    ):
        raise ValueError("cached schema analysis metadata conflicts with raw snapshot metadata")


def _require_non_blank(value: str, field_name: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field_name} cannot be blank")
    return stripped


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("schema timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)


def _optional_float(value: object) -> float | None:
    return None if value is None else float(value)
