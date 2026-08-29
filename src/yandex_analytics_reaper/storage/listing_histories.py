from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, model_validator

from yandex_analytics_reaper.domain import (
    ListingMediaObservation,
    ListingStatus,
    ListingStatusObservation,
    ListingStatusReason,
    ListingUpdateObservation,
)
from yandex_analytics_reaper.evidence import EvidenceEnvelope
from yandex_analytics_reaper.normalizers import (
    NormalizedListingHistories,
    NormalizedListingMedia,
    NormalizedListingStatus,
    NormalizedListingUpdate,
)

from .lineage import persist_lineage_in_connection
from .sqlite import SQLiteDatabase


class ListingHistoryWrite(BaseModel):
    """One normalized history bundle plus shared evidence/provenance metadata."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    histories: NormalizedListingHistories
    evidence: EvidenceEnvelope
    normalizer_name: str
    normalizer_version: str

    @model_validator(mode="after")
    def validate_contract(self) -> Self:
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
        if not self.normalizer_name.strip() or not self.normalizer_version.strip():
            raise ValueError("normalizer name/version cannot be blank")

        observations = _history_observations(self.histories)
        if any(
            item.observation.observed_at != self.evidence.observed_at
            for item in observations
        ):
            raise ValueError("history observations and evidence observed_at must match")
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
        with self.database.connect() as connection:
            listing_ids = {
                item.observation.platform_listing_id
                for item in _history_observations(write.histories)
            }
            if len(listing_ids) != 1:
                raise ValueError("one listing-history write must target exactly one listing")
            listing_id = next(iter(listing_ids))
            listing = connection.execute(
                "SELECT id FROM platform_listings WHERE id = ?",
                (listing_id,),
            ).fetchone()
            if listing is None:
                raise ValueError(f"listing {listing_id} must be persisted before histories")

            persisted_ids: list[str] = []
            if write.histories.update is not None:
                persisted_ids.append(
                    self._persist_update(connection, write, write.histories.update)
                )
            if write.histories.status is not None:
                persisted_ids.append(
                    self._persist_status(connection, write, write.histories.status)
                )
            if write.histories.media is not None:
                persisted_ids.append(
                    self._persist_media(connection, write, write.histories.media)
                )
            return tuple(persisted_ids)

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
        if typed_table not in {
            "listing_update_observations",
            "listing_status_observations",
            "listing_media_observations",
        }:
            raise ValueError("unsupported listing history table")
        query = f"""
            SELECT
                n.id,
                n.source_id,
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
                h.lineage_refs_json,
                t.*
            FROM normalized_observations AS n
            JOIN listing_history_evidence AS h ON h.observation_id = n.id
            JOIN {typed_table} AS t ON t.observation_id = n.id
            WHERE t.platform_listing_id = ?
        """
        params: list[object] = [listing_id]
        if as_of is not None:
            _require_aware(as_of, "as_of")
            query += " AND n.observed_at <= ?"
            params.append(_timestamp(as_of))
        query += " ORDER BY n.observed_at, n.retrieved_at, n.id"
        with self.database.connect() as connection:
            return connection.execute(query, params).fetchall()

    def _persist_update(
        self,
        connection: sqlite3.Connection,
        write: ListingHistoryWrite,
        item: NormalizedListingUpdate,
    ) -> str:
        observation = item.observation
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
        persist_lineage_in_connection(connection, observation_id, item.lineage)
        return observation_id

    def _persist_status(
        self,
        connection: sqlite3.Connection,
        write: ListingHistoryWrite,
        item: NormalizedListingStatus,
    ) -> str:
        observation = item.observation
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
        persist_lineage_in_connection(connection, observation_id, item.lineage)
        return observation_id

    def _persist_media(
        self,
        connection: sqlite3.Connection,
        write: ListingHistoryWrite,
        item: NormalizedListingMedia,
    ) -> str:
        observation = item.observation
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
        persist_lineage_in_connection(connection, observation_id, item.lineage)
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


def _history_observations(
    histories: NormalizedListingHistories,
) -> tuple[NormalizedListingUpdate | NormalizedListingStatus | NormalizedListingMedia, ...]:
    items: list[NormalizedListingUpdate | NormalizedListingStatus | NormalizedListingMedia] = []
    if histories.update is not None:
        items.append(histories.update)
    if histories.status is not None:
        items.append(histories.status)
    if histories.media is not None:
        items.append(histories.media)
    return tuple(items)


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
