from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, Self

from pydantic import BaseModel, ConfigDict, model_validator

from yandex_analytics_reaper.domain import GameMetricName, GameMetricObservation
from yandex_analytics_reaper.evidence import EvidenceEnvelope

from .sqlite import SQLiteDatabase


class MetricWrite(BaseModel):
    """One normalized numeric metric plus the evidence required to interpret it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    metric: GameMetricObservation
    evidence: EvidenceEnvelope
    normalizer_name: str
    normalizer_version: str

    @model_validator(mode="after")
    def validate_contract(self) -> Self:
        _require_aware(self.metric.observed_at, "metric.observed_at")
        _require_aware(self.evidence.observed_at, "evidence.observed_at")
        if self.metric.observed_at != self.evidence.observed_at:
            raise ValueError("metric and evidence observed_at must match")
        if self.evidence.retrieved_at is None:
            raise ValueError("persisted evidence requires retrieved_at")
        _require_aware(self.evidence.retrieved_at, "evidence.retrieved_at")
        if self.evidence.observed_at > self.evidence.retrieved_at:
            raise ValueError("observed_at cannot be later than retrieved_at")
        if self.evidence.available_at is not None:
            _require_aware(self.evidence.available_at, "evidence.available_at")
            if self.evidence.available_at < self.evidence.observed_at:
                raise ValueError("available_at cannot be earlier than observed_at")
            if self.evidence.available_at > self.evidence.retrieved_at:
                raise ValueError("available_at cannot be later than retrieved_at")
        if self.evidence.period_start is not None:
            _require_aware(self.evidence.period_start, "evidence.period_start")
        if self.evidence.period_end is not None:
            _require_aware(self.evidence.period_end, "evidence.period_end")
        if (
            self.evidence.period_start is not None
            and self.evidence.period_end is not None
            and self.evidence.period_start > self.evidence.period_end
        ):
            raise ValueError("period_start cannot be later than period_end")
        if not self.normalizer_name.strip() or not self.normalizer_version.strip():
            raise ValueError("normalizer name/version cannot be blank")
        if not math.isfinite(float(self.metric.value)):
            raise ValueError("metric value must be finite")
        return self


class PersistedMetricObservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    observation_id: str
    metric: GameMetricObservation
    evidence: EvidenceEnvelope
    normalizer_name: str
    normalizer_version: str


class MetricStore(Protocol):
    def persist_metric(self, write: MetricWrite) -> str: ...

    def persist_metrics(self, writes: Sequence[MetricWrite]) -> tuple[str, ...]: ...

    def metric_history(
        self,
        listing_id: str,
        metric_name: GameMetricName | None = None,
    ) -> tuple[PersistedMetricObservation, ...]: ...


class SQLiteMetricStore:
    """SQLite persistence for normalized metric observations and evidence envelopes."""

    def __init__(self, path: Path) -> None:
        self.database = SQLiteDatabase(path)

    @property
    def path(self) -> Path:
        return self.database.path

    def persist_metric(self, write: MetricWrite) -> str:
        return self.persist_metrics((write,))[0]

    def persist_metrics(self, writes: Sequence[MetricWrite]) -> tuple[str, ...]:
        if not writes:
            return ()
        with self.database.connect() as connection:
            return tuple(self._persist_metric(connection, write) for write in writes)

    def metric_history(
        self,
        listing_id: str,
        metric_name: GameMetricName | None = None,
    ) -> tuple[PersistedMetricObservation, ...]:
        query = """
            SELECT
                n.id,
                n.source_id,
                n.observed_at,
                n.available_at,
                n.retrieved_at,
                n.normalizer_name,
                n.normalizer_version,
                m.platform_listing_id,
                m.metric_name,
                m.period_start,
                m.period_end,
                m.value_numeric,
                m.provenance,
                m.measurement_kind,
                m.semantic_confidence,
                m.coverage_status,
                m.historical_availability,
                m.revision_status,
                m.uncertainty_json,
                m.lineage_refs_json
            FROM normalized_observations AS n
            JOIN game_metric_observations AS m ON m.observation_id = n.id
            WHERE m.platform_listing_id = ?
        """
        params: list[object] = [listing_id]
        if metric_name is not None:
            query += " AND m.metric_name = ?"
            params.append(metric_name.value)
        query += " ORDER BY n.observed_at, n.retrieved_at, n.id"

        with self.database.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return tuple(_row_to_persisted(row) for row in rows)

    def _persist_metric(self, connection: sqlite3.Connection, write: MetricWrite) -> str:
        listing = connection.execute(
            "SELECT id FROM platform_listings WHERE id = ?",
            (write.metric.platform_listing_id,),
        ).fetchone()
        if listing is None:
            raise ValueError(
                f"listing {write.metric.platform_listing_id} must be persisted before metrics"
            )

        observation_id = _observation_id(write)
        expected = _expected_row(write, observation_id)

        connection.execute(
            """
            INSERT OR IGNORE INTO normalized_observations (
                id,
                source_id,
                observation_type,
                observed_at,
                available_at,
                retrieved_at,
                normalizer_name,
                normalizer_version
            ) VALUES (?, ?, 'game_metric', ?, ?, ?, ?, ?)
            """,
            (
                observation_id,
                write.evidence.source_id,
                _timestamp(write.evidence.observed_at),
                _optional_timestamp(write.evidence.available_at),
                _timestamp_required(write.evidence.retrieved_at),
                write.normalizer_name,
                write.normalizer_version,
            ),
        )
        connection.execute(
            """
            INSERT OR IGNORE INTO game_metric_observations (
                observation_id,
                platform_listing_id,
                metric_name,
                period_start,
                period_end,
                value_numeric,
                missing_reason,
                provenance,
                measurement_kind,
                semantic_confidence,
                coverage_status,
                historical_availability,
                revision_status,
                uncertainty_json,
                lineage_refs_json
            ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                observation_id,
                write.metric.platform_listing_id,
                write.metric.metric_name.value,
                _optional_timestamp(write.evidence.period_start),
                _optional_timestamp(write.evidence.period_end),
                write.metric.value,
                write.evidence.provenance.value,
                write.evidence.measurement_kind.value,
                write.evidence.semantic_confidence.value,
                write.evidence.coverage_status.value,
                write.evidence.historical_availability.value,
                write.evidence.revision_status.value,
                _uncertainty_json(write.evidence),
                _lineage_refs_json(write.evidence),
            ),
        )

        row = connection.execute(
            """
            SELECT
                n.id,
                n.source_id,
                n.observation_type,
                n.observed_at,
                n.available_at,
                n.retrieved_at,
                n.normalizer_name,
                n.normalizer_version,
                m.platform_listing_id,
                m.metric_name,
                m.period_start,
                m.period_end,
                m.value_numeric,
                m.missing_reason,
                m.provenance,
                m.measurement_kind,
                m.semantic_confidence,
                m.coverage_status,
                m.historical_availability,
                m.revision_status,
                m.uncertainty_json,
                m.lineage_refs_json
            FROM normalized_observations AS n
            JOIN game_metric_observations AS m ON m.observation_id = n.id
            WHERE n.id = ?
            """,
            (observation_id,),
        ).fetchone()
        if row is None or _canonical_row(row) != expected:
            raise ValueError(f"conflicting metric observation {observation_id}")
        return observation_id


def _observation_id(write: MetricWrite) -> str:
    payload = {
        "source_id": write.evidence.source_id,
        "observation_type": "game_metric",
        "platform_listing_id": write.metric.platform_listing_id,
        "metric_name": write.metric.metric_name.value,
        "observed_at": _timestamp(write.evidence.observed_at),
        "available_at": _optional_timestamp(write.evidence.available_at),
        "retrieved_at": _timestamp_required(write.evidence.retrieved_at),
        "period_start": _optional_timestamp(write.evidence.period_start),
        "period_end": _optional_timestamp(write.evidence.period_end),
        "normalizer_name": write.normalizer_name,
        "normalizer_version": write.normalizer_version,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return "metric:" + hashlib.sha256(encoded).hexdigest()[:32]


def _expected_row(write: MetricWrite, observation_id: str) -> dict[str, object]:
    return {
        "id": observation_id,
        "source_id": write.evidence.source_id,
        "observation_type": "game_metric",
        "observed_at": _timestamp(write.evidence.observed_at),
        "available_at": _optional_timestamp(write.evidence.available_at),
        "retrieved_at": _timestamp_required(write.evidence.retrieved_at),
        "normalizer_name": write.normalizer_name,
        "normalizer_version": write.normalizer_version,
        "platform_listing_id": write.metric.platform_listing_id,
        "metric_name": write.metric.metric_name.value,
        "period_start": _optional_timestamp(write.evidence.period_start),
        "period_end": _optional_timestamp(write.evidence.period_end),
        "value_numeric": write.metric.value,
        "missing_reason": None,
        "provenance": write.evidence.provenance.value,
        "measurement_kind": write.evidence.measurement_kind.value,
        "semantic_confidence": write.evidence.semantic_confidence.value,
        "coverage_status": write.evidence.coverage_status.value,
        "historical_availability": write.evidence.historical_availability.value,
        "revision_status": write.evidence.revision_status.value,
        "uncertainty_json": _uncertainty_json(write.evidence),
        "lineage_refs_json": _lineage_refs_json(write.evidence),
    }


def _canonical_row(row: sqlite3.Row) -> dict[str, object]:
    return {
        "id": str(row["id"]),
        "source_id": str(row["source_id"]),
        "observation_type": str(row["observation_type"]),
        "observed_at": str(row["observed_at"]),
        "available_at": _optional_str(row["available_at"]),
        "retrieved_at": str(row["retrieved_at"]),
        "normalizer_name": str(row["normalizer_name"]),
        "normalizer_version": str(row["normalizer_version"]),
        "platform_listing_id": str(row["platform_listing_id"]),
        "metric_name": str(row["metric_name"]),
        "period_start": _optional_str(row["period_start"]),
        "period_end": _optional_str(row["period_end"]),
        "value_numeric": row["value_numeric"],
        "missing_reason": _optional_str(row["missing_reason"]),
        "provenance": str(row["provenance"]),
        "measurement_kind": str(row["measurement_kind"]),
        "semantic_confidence": str(row["semantic_confidence"]),
        "coverage_status": str(row["coverage_status"]),
        "historical_availability": str(row["historical_availability"]),
        "revision_status": str(row["revision_status"]),
        "uncertainty_json": _optional_str(row["uncertainty_json"]),
        "lineage_refs_json": str(row["lineage_refs_json"]),
    }


def _row_to_persisted(row: sqlite3.Row) -> PersistedMetricObservation:
    evidence = EvidenceEnvelope.model_validate(
        {
            "source_id": str(row["source_id"]),
            "observed_at": _parse_timestamp(str(row["observed_at"])),
            "available_at": _parse_optional_timestamp(row["available_at"]),
            "retrieved_at": _parse_timestamp(str(row["retrieved_at"])),
            "period_start": _parse_optional_timestamp(row["period_start"]),
            "period_end": _parse_optional_timestamp(row["period_end"]),
            "provenance": str(row["provenance"]),
            "measurement_kind": str(row["measurement_kind"]),
            "semantic_confidence": str(row["semantic_confidence"]),
            "coverage_status": str(row["coverage_status"]),
            "historical_availability": str(row["historical_availability"]),
            "revision_status": str(row["revision_status"]),
            "uncertainty": _json_or_none(row["uncertainty_json"]),
            "lineage_refs": tuple(_json_list(row["lineage_refs_json"])),
        }
    )
    metric = GameMetricObservation(
        platform_listing_id=str(row["platform_listing_id"]),
        observed_at=evidence.observed_at,
        metric_name=GameMetricName(str(row["metric_name"])),
        value=_numeric(row["value_numeric"]),
    )
    return PersistedMetricObservation(
        observation_id=str(row["id"]),
        metric=metric,
        evidence=evidence,
        normalizer_name=str(row["normalizer_name"]),
        normalizer_version=str(row["normalizer_version"]),
    )


def _uncertainty_json(evidence: EvidenceEnvelope) -> str | None:
    if evidence.uncertainty is None:
        return None
    return json.dumps(
        evidence.uncertainty.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )


def _lineage_refs_json(evidence: EvidenceEnvelope) -> str:
    return json.dumps(
        sorted(set(evidence.lineage_refs)),
        separators=(",", ":"),
    )


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")


def _timestamp(value: datetime) -> str:
    _require_aware(value, "timestamp")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _timestamp_required(value: datetime | None) -> str:
    if value is None:
        raise ValueError("timestamp is required")
    return _timestamp(value)


def _optional_timestamp(value: datetime | None) -> str | None:
    return None if value is None else _timestamp(value)


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _parse_optional_timestamp(value: object) -> datetime | None:
    return None if value is None else _parse_timestamp(str(value))


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)


def _json_or_none(value: object) -> object | None:
    return None if value is None else json.loads(str(value))


def _json_list(value: object) -> list[str]:
    parsed = json.loads(str(value))
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        raise ValueError("stored lineage_refs_json is invalid")
    return parsed


def _numeric(value: object) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("stored metric value is not numeric")
    return value
