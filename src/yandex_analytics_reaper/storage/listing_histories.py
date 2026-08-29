from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, Self, TypeAlias

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from yandex_analytics_reaper.domain import (
    ListingMediaObservation,
    ListingStatus,
    ListingStatusObservation,
    ListingStatusReason,
    ListingUpdateObservation,
)
from yandex_analytics_reaper.evidence import EvidenceEnvelope, FieldLineage

from .lineage import persist_lineage_in_connection
from .sqlite import SQLiteDatabase

HistoryObservation: TypeAlias = (
    ListingUpdateObservation | ListingStatusObservation | ListingMediaObservation
)

_HISTORY_TABLE_TYPES = {
    "listing_update_observations": "listing_update",
    "listing_status_observations": "listing_status",
    "listing_media_observations": "listing_media",
}
_HISTORY_ORDER = {
    "listing_update": 0,
    "listing_status": 1,
    "listing_media": 2,
}


class ListingHistoryObservationWrite(BaseModel):
    """One platform-neutral history observation plus its exact raw field lineage."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    observation: HistoryObservation
    lineage: tuple[FieldLineage, ...] = Field(min_length=1)


class ListingHistoryWrite(BaseModel):
    """Atomic history batch plus shared evidence and normalizer provenance."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    observations: tuple[ListingHistoryObservationWrite, ...] = Field(min_length=1)
    evidence: EvidenceEnvelope
    normalizer_name: str
    normalizer_version: str

    @model_validator(mode="after")
    def validate_contract(self) -> Self:
        _require_exact_non_blank(self.evidence.source_id, "evidence.source_id")
        _require_exact_non_blank(self.normalizer_name, "normalizer_name")
        _require_exact_non_blank(self.normalizer_version, "normalizer_version")
        _require_aware(self.evidence.observed_at, "evidence.observed_at")
        if self.evidence.retrieved_at is None:
            raise ValueError("persisted listing-history evidence requires retrieved_at")
        _require_aware(self.evidence.retrieved_at, "evidence.retrieved_at")
        if self.evidence.observed_at > self.evidence.retrieved_at:
            raise ValueError("observed_at cannot be later than retrieved_at")
        if self.evidence.available_at is not None:
            _require_aware(self.evidence.available_at, "evidence.available_at")
            if self.evidence.observed_at > self.evidence.available_at:
                raise ValueError("observed_at cannot be later than available_at")
            if self.evidence.available_at > self.evidence.retrieved_at:
                raise ValueError("available_at cannot be later than retrieved_at")
        if self.evidence.period_start is not None or self.evidence.period_end is not None:
            raise ValueError("listing-history evidence does not accept metric periods")

        listing_ids: set[str] = set()
        observation_types: set[str] = set()
        for item in self.observations:
            observation = item.observation
            listing_ids.add(observation.platform_listing_id)
            observation_type = _observation_type(observation)
            if observation_type in observation_types:
                raise ValueError("listing-history batch cannot repeat one observation type")
            observation_types.add(observation_type)
            if observation.observed_at != self.evidence.observed_at:
                raise ValueError("history observations and evidence observed_at must match")
            for lineage in item.lineage:
                if lineage.transformation_version != self.normalizer_version:
                    raise ValueError(
                        "history lineage transformation_version must match normalizer_version"
                    )
                if not lineage.transformation_name.startswith(f"{self.normalizer_name}."):
                    raise ValueError(
                        "history lineage transformation_name must match normalizer_name"
                    )
        if len(listing_ids) != 1:
            raise ValueError("one listing-history write must target exactly one listing")
        return self


class PersistedListingUpdate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    observation_id: str
    observation: ListingUpdateObservation
    evidence: EvidenceEnvelope
    normalizer_name: str
    normalizer_version: str


class PersistedListingStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    observation_id: str
    observation: ListingStatusObservation
    evidence: EvidenceEnvelope
    normalizer_name: str
    normalizer_version: str


class PersistedListingMedia(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    observation_id: str
    observation: ListingMediaObservation
    evidence: EvidenceEnvelope
    normalizer_name: str
    normalizer_version: str


class ListingHistoryStore(Protocol):
    def persist(self, write: ListingHistoryWrite) -> tuple[str, ...]: ...

    def update_history(
        self,
        listing_id: str,
        *,
        as_of: AwareDatetime | None = None,
    ) -> tuple[PersistedListingUpdate, ...]: ...

    def status_history(
        self,
        listing_id: str,
        *,
        as_of: AwareDatetime | None = None,
    ) -> tuple[PersistedListingStatus, ...]: ...

    def media_history(
        self,
        listing_id: str,
        *,
        as_of: AwareDatetime | None = None,
    ) -> tuple[PersistedListingMedia, ...]: ...


class SQLiteListingHistoryStore:
    """Append-only typed listing histories with transactional evidence + lineage."""

    def __init__(self, path: Path) -> None:
        self.database = SQLiteDatabase(path)

    @property
    def path(self) -> Path:
        return self.database.path

    def persist(self, write: ListingHistoryWrite) -> tuple[str, ...]:
        write = ListingHistoryWrite.model_validate(write.model_dump(mode="python"))
        ordered = sorted(
            write.observations,
            key=lambda item: _HISTORY_ORDER[_observation_type(item.observation)],
        )
        listing_id = ordered[0].observation.platform_listing_id

        with self.database.connect() as connection:
            listing = connection.execute(
                "SELECT id FROM platform_listings WHERE id = ?",
                (listing_id,),
            ).fetchone()
            if listing is None:
                raise ValueError(f"listing {listing_id} must be persisted before histories")
            return tuple(
                self._persist_item(connection, write, item)
                for item in ordered
            )

    def update_history(
        self,
        listing_id: str,
        *,
        as_of: AwareDatetime | None = None,
    ) -> tuple[PersistedListingUpdate, ...]:
        rows = self._history_rows("listing_update_observations", listing_id, as_of)
        return tuple(_row_to_update(row) for row in rows)

    def status_history(
        self,
        listing_id: str,
        *,
        as_of: AwareDatetime | None = None,
    ) -> tuple[PersistedListingStatus, ...]:
        rows = self._history_rows("listing_status_observations", listing_id, as_of)
        return tuple(_row_to_status(row) for row in rows)

    def media_history(
        self,
        listing_id: str,
        *,
        as_of: AwareDatetime | None = None,
    ) -> tuple[PersistedListingMedia, ...]:
        rows = self._history_rows("listing_media_observations", listing_id, as_of)
        return tuple(_row_to_media(row) for row in rows)

    def _history_rows(
        self,
        typed_table: str,
        listing_id: str,
        as_of: AwareDatetime | None,
    ) -> list[sqlite3.Row]:
        expected_type = _HISTORY_TABLE_TYPES.get(typed_table)
        if expected_type is None:
            raise ValueError("unsupported listing history table")
        query = f"""
            SELECT
                n.id,
                n.source_id,
                n.observation_type,
                n.observed_at,
                n.available_at,
                n.retrieved_at,
                n.normalizer_name,
                n.normalizer_version,
                h.observation_id AS evidence_observation_id,
                h.provenance,
                h.measurement_kind,
                h.semantic_confidence,
                h.coverage_status,
                h.historical_availability,
                h.revision_status,
                h.uncertainty_json,
                h.lineage_refs_json,
                t.*
            FROM {typed_table} AS t
            JOIN normalized_observations AS n ON n.id = t.observation_id
            LEFT JOIN listing_history_evidence AS h ON h.observation_id = n.id
            WHERE t.platform_listing_id = ?
        """
        params: list[object] = [listing_id]
        if as_of is not None:
            _require_aware(as_of, "as_of")
            query += " AND n.observed_at <= ?"
            params.append(_timestamp(as_of))
        query += " ORDER BY n.observed_at, n.retrieved_at, n.id"

        rows: list[sqlite3.Row] = []
        with self.database.connect() as connection:
            raw_rows = connection.execute(query, params).fetchall()
            for raw_row in raw_rows:
                if not isinstance(raw_row, sqlite3.Row):
                    raise RuntimeError("listing history query did not return sqlite rows")
                if str(raw_row["observation_type"]) != expected_type:
                    raise RuntimeError("stored listing history observation_type is invalid")
                if raw_row["evidence_observation_id"] is None:
                    raise RuntimeError("stored listing history is missing evidence")
                lineage_rows = connection.execute(
                    """
                    SELECT transformation_name, transformation_version
                    FROM observation_lineage
                    WHERE normalized_observation_id = ?
                    """,
                    (str(raw_row["id"]),),
                ).fetchall()
                if not lineage_rows:
                    raise RuntimeError("stored listing history is missing field lineage")
                normalizer_name = str(raw_row["normalizer_name"])
                normalizer_version = str(raw_row["normalizer_version"])
                if any(
                    str(lineage["transformation_version"]) != normalizer_version
                    or not str(lineage["transformation_name"]).startswith(
                        f"{normalizer_name}."
                    )
                    for lineage in lineage_rows
                ):
                    raise RuntimeError("stored listing history lineage provenance is invalid")
                rows.append(raw_row)
        return rows

    def _persist_item(
        self,
        connection: sqlite3.Connection,
        write: ListingHistoryWrite,
        item: ListingHistoryObservationWrite,
    ) -> str:
        observation = item.observation
        if isinstance(observation, ListingUpdateObservation):
            return self._persist_update(connection, write, observation, item.lineage)
        if isinstance(observation, ListingStatusObservation):
            return self._persist_status(connection, write, observation, item.lineage)
        if isinstance(observation, ListingMediaObservation):
            return self._persist_media(connection, write, observation, item.lineage)
        raise TypeError("unsupported listing history observation")

    def _persist_update(
        self,
        connection: sqlite3.Connection,
        write: ListingHistoryWrite,
        observation: ListingUpdateObservation,
        lineage: tuple[FieldLineage, ...],
    ) -> str:
        observation_id = _observation_id(
            write,
            "listing_update",
            observation.platform_listing_id,
        )
        self._persist_envelope(connection, write, observation_id, "listing_update")
        connection.execute(
            """
            INSERT OR IGNORE INTO listing_update_observations (
                observation_id,
                platform_listing_id,
                app_version,
                source_published_at
            ) VALUES (?, ?, ?, ?)
            """,
            (
                observation_id,
                observation.platform_listing_id,
                observation.app_version,
                _optional_timestamp(observation.source_published_at),
            ),
        )
        row = connection.execute(
            """
            SELECT platform_listing_id, app_version, source_published_at
            FROM listing_update_observations
            WHERE observation_id = ?
            """,
            (observation_id,),
        ).fetchone()
        expected = {
            "platform_listing_id": observation.platform_listing_id,
            "app_version": observation.app_version,
            "source_published_at": _optional_timestamp(observation.source_published_at),
        }
        if row is None or _typed_row(row) != expected:
            raise ValueError(f"conflicting listing update observation {observation_id}")
        persist_lineage_in_connection(connection, observation_id, lineage)
        return observation_id

    def _persist_status(
        self,
        connection: sqlite3.Connection,
        write: ListingHistoryWrite,
        observation: ListingStatusObservation,
        lineage: tuple[FieldLineage, ...],
    ) -> str:
        observation_id = _observation_id(
            write,
            "listing_status",
            observation.platform_listing_id,
        )
        self._persist_envelope(connection, write, observation_id, "listing_status")
        connection.execute(
            """
            INSERT OR IGNORE INTO listing_status_observations (
                observation_id,
                platform_listing_id,
                status,
                status_reason
            ) VALUES (?, ?, ?, ?)
            """,
            (
                observation_id,
                observation.platform_listing_id,
                observation.status.value,
                observation.reason.value,
            ),
        )
        row = connection.execute(
            """
            SELECT platform_listing_id, status, status_reason
            FROM listing_status_observations
            WHERE observation_id = ?
            """,
            (observation_id,),
        ).fetchone()
        expected = {
            "platform_listing_id": observation.platform_listing_id,
            "status": observation.status.value,
            "status_reason": observation.reason.value,
        }
        if row is None or _typed_row(row) != expected:
            raise ValueError(f"conflicting listing status observation {observation_id}")
        persist_lineage_in_connection(connection, observation_id, lineage)
        return observation_id

    def _persist_media(
        self,
        connection: sqlite3.Connection,
        write: ListingHistoryWrite,
        observation: ListingMediaObservation,
        lineage: tuple[FieldLineage, ...],
    ) -> str:
        observation_id = _observation_id(
            write,
            "listing_media",
            observation.platform_listing_id,
        )
        self._persist_envelope(connection, write, observation_id, "listing_media")
        connection.execute(
            """
            INSERT OR IGNORE INTO listing_media_observations (
                observation_id,
                platform_listing_id,
                manifest_hash
            ) VALUES (?, ?, ?)
            """,
            (
                observation_id,
                observation.platform_listing_id,
                observation.manifest_hash,
            ),
        )
        row = connection.execute(
            """
            SELECT platform_listing_id, manifest_hash
            FROM listing_media_observations
            WHERE observation_id = ?
            """,
            (observation_id,),
        ).fetchone()
        expected = {
            "platform_listing_id": observation.platform_listing_id,
            "manifest_hash": observation.manifest_hash,
        }
        if row is None or _typed_row(row) != expected:
            raise ValueError(f"conflicting listing media observation {observation_id}")
        persist_lineage_in_connection(connection, observation_id, lineage)
        return observation_id

    @staticmethod
    def _persist_envelope(
        connection: sqlite3.Connection,
        write: ListingHistoryWrite,
        observation_id: str,
        observation_type: str,
    ) -> None:
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
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                observation_id,
                write.evidence.source_id,
                observation_type,
                _timestamp(write.evidence.observed_at),
                _optional_timestamp(write.evidence.available_at),
                _timestamp_required(write.evidence.retrieved_at),
                write.normalizer_name,
                write.normalizer_version,
            ),
        )
        connection.execute(
            """
            INSERT OR IGNORE INTO listing_history_evidence (
                observation_id,
                provenance,
                measurement_kind,
                semantic_confidence,
                coverage_status,
                historical_availability,
                revision_status,
                uncertainty_json,
                lineage_refs_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                observation_id,
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
                n.source_id,
                n.observation_type,
                n.observed_at,
                n.available_at,
                n.retrieved_at,
                n.normalizer_name,
                n.normalizer_version,
                h.provenance,
                h.measurement_kind,
                h.semantic_confidence,
                h.coverage_status,
                h.historical_availability,
                h.revision_status,
                h.uncertainty_json,
                h.lineage_refs_json
            FROM normalized_observations AS n
            JOIN listing_history_evidence AS h ON h.observation_id = n.id
            WHERE n.id = ?
            """,
            (observation_id,),
        ).fetchone()
        expected = _envelope_row(write, observation_type)
        if row is None or _canonical_envelope_row(row) != expected:
            raise ValueError(f"conflicting listing-history envelope {observation_id}")


def _observation_type(observation: HistoryObservation) -> str:
    if isinstance(observation, ListingUpdateObservation):
        return "listing_update"
    if isinstance(observation, ListingStatusObservation):
        return "listing_status"
    if isinstance(observation, ListingMediaObservation):
        return "listing_media"
    raise TypeError("unsupported listing history observation")


def _observation_id(
    write: ListingHistoryWrite,
    observation_type: str,
    listing_id: str,
) -> str:
    payload = {
        "source_id": write.evidence.source_id,
        "observation_type": observation_type,
        "platform_listing_id": listing_id,
        "observed_at": _timestamp(write.evidence.observed_at),
        "available_at": _optional_timestamp(write.evidence.available_at),
        "retrieved_at": _timestamp_required(write.evidence.retrieved_at),
        "normalizer_name": write.normalizer_name,
        "normalizer_version": write.normalizer_version,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return "listing-history:" + hashlib.sha256(encoded).hexdigest()[:32]


def _envelope_row(write: ListingHistoryWrite, observation_type: str) -> dict[str, object]:
    return {
        "source_id": write.evidence.source_id,
        "observation_type": observation_type,
        "observed_at": _timestamp(write.evidence.observed_at),
        "available_at": _optional_timestamp(write.evidence.available_at),
        "retrieved_at": _timestamp_required(write.evidence.retrieved_at),
        "normalizer_name": write.normalizer_name,
        "normalizer_version": write.normalizer_version,
        "provenance": write.evidence.provenance.value,
        "measurement_kind": write.evidence.measurement_kind.value,
        "semantic_confidence": write.evidence.semantic_confidence.value,
        "coverage_status": write.evidence.coverage_status.value,
        "historical_availability": write.evidence.historical_availability.value,
        "revision_status": write.evidence.revision_status.value,
        "uncertainty_json": _uncertainty_json(write.evidence),
        "lineage_refs_json": _lineage_refs_json(write.evidence),
    }


def _canonical_envelope_row(row: sqlite3.Row) -> dict[str, object]:
    return {
        "source_id": str(row["source_id"]),
        "observation_type": str(row["observation_type"]),
        "observed_at": str(row["observed_at"]),
        "available_at": _optional_str(row["available_at"]),
        "retrieved_at": str(row["retrieved_at"]),
        "normalizer_name": str(row["normalizer_name"]),
        "normalizer_version": str(row["normalizer_version"]),
        "provenance": str(row["provenance"]),
        "measurement_kind": str(row["measurement_kind"]),
        "semantic_confidence": str(row["semantic_confidence"]),
        "coverage_status": str(row["coverage_status"]),
        "historical_availability": str(row["historical_availability"]),
        "revision_status": str(row["revision_status"]),
        "uncertainty_json": _optional_str(row["uncertainty_json"]),
        "lineage_refs_json": str(row["lineage_refs_json"]),
    }


def _typed_row(row: sqlite3.Row) -> dict[str, object]:
    return {key: row[key] for key in row.keys()}


def _evidence_from_row(row: sqlite3.Row) -> EvidenceEnvelope:
    return EvidenceEnvelope.model_validate(
        {
            "source_id": str(row["source_id"]),
            "observed_at": _parse_timestamp(str(row["observed_at"])),
            "available_at": _parse_optional_timestamp(row["available_at"]),
            "retrieved_at": _parse_timestamp(str(row["retrieved_at"])),
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


def _row_to_update(row: sqlite3.Row) -> PersistedListingUpdate:
    evidence = _evidence_from_row(row)
    return PersistedListingUpdate(
        observation_id=str(row["id"]),
        observation=ListingUpdateObservation(
            platform_listing_id=str(row["platform_listing_id"]),
            observed_at=evidence.observed_at,
            app_version=_optional_str(row["app_version"]),
            source_published_at=_parse_optional_timestamp(row["source_published_at"]),
        ),
        evidence=evidence,
        normalizer_name=str(row["normalizer_name"]),
        normalizer_version=str(row["normalizer_version"]),
    )


def _row_to_status(row: sqlite3.Row) -> PersistedListingStatus:
    evidence = _evidence_from_row(row)
    return PersistedListingStatus(
        observation_id=str(row["id"]),
        observation=ListingStatusObservation(
            platform_listing_id=str(row["platform_listing_id"]),
            observed_at=evidence.observed_at,
            status=ListingStatus(str(row["status"])),
            reason=ListingStatusReason(str(row["status_reason"])),
        ),
        evidence=evidence,
        normalizer_name=str(row["normalizer_name"]),
        normalizer_version=str(row["normalizer_version"]),
    )


def _row_to_media(row: sqlite3.Row) -> PersistedListingMedia:
    evidence = _evidence_from_row(row)
    return PersistedListingMedia(
        observation_id=str(row["id"]),
        observation=ListingMediaObservation(
            platform_listing_id=str(row["platform_listing_id"]),
            observed_at=evidence.observed_at,
            manifest_hash=str(row["manifest_hash"]),
        ),
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
    return json.dumps(sorted(set(evidence.lineage_refs)), separators=(",", ":"))


def _json_or_none(value: object) -> object | None:
    return None if value is None else json.loads(str(value))


def _json_list(value: object) -> list[str]:
    parsed = json.loads(str(value))
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        raise ValueError("stored lineage_refs_json is invalid")
    return parsed


def _require_exact_non_blank(value: str, field: str) -> None:
    if not value:
        raise ValueError(f"{field} cannot be blank")
    if value != value.strip():
        raise ValueError(f"{field} must already be trimmed")


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
