from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from yandex_analytics_reaper.domain import ListingStateObservation
from yandex_analytics_reaper.evidence import EvidenceEnvelope, FieldLineage

from .lineage import persist_lineage_in_connection
from .sqlite import SQLiteDatabase


class ListingStateWrite(BaseModel):
    """One normalized listing-state observation plus exact evidence and field lineage."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    observation: ListingStateObservation
    evidence: EvidenceEnvelope
    normalizer_name: str
    normalizer_version: str
    lineage: tuple[FieldLineage, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_contract(self) -> Self:
        _require_aware(self.observation.observed_at, "observation.observed_at")
        _require_aware(self.evidence.observed_at, "evidence.observed_at")
        if self.observation.observed_at != self.evidence.observed_at:
            raise ValueError("listing state and evidence observed_at must match")
        if self.evidence.retrieved_at is None:
            raise ValueError("persisted listing-state evidence requires retrieved_at")
        _require_aware(self.evidence.retrieved_at, "evidence.retrieved_at")
        if self.evidence.observed_at > self.evidence.retrieved_at:
            raise ValueError("observed_at cannot be later than retrieved_at")
        if self.evidence.available_at is not None:
            _require_aware(self.evidence.available_at, "evidence.available_at")
            if self.evidence.available_at < self.evidence.observed_at:
                raise ValueError("available_at cannot be earlier than observed_at")
            if self.evidence.available_at > self.evidence.retrieved_at:
                raise ValueError("available_at cannot be later than retrieved_at")
        if self.evidence.period_start is not None or self.evidence.period_end is not None:
            raise ValueError("listing-state evidence does not accept metric periods")
        if not self.normalizer_name.strip() or not self.normalizer_version.strip():
            raise ValueError("normalizer name/version cannot be blank")
        if any(
            item.transformation_version != self.normalizer_version
            for item in self.lineage
        ):
            raise ValueError("listing-state lineage version must match normalizer version")
        if any(
            not item.transformation_name.startswith(f"{self.normalizer_name}.")
            for item in self.lineage
        ):
            raise ValueError("listing-state lineage name must match normalizer name")
        if not any(
            item.target_field_path == "listing_state_observations.platform_listing_id"
            for item in self.lineage
        ):
            raise ValueError("listing-state lineage must bind platform_listing_id")
        return self


class PersistedListingState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    observation_id: str
    observation: ListingStateObservation
    evidence: EvidenceEnvelope
    normalizer_name: str
    normalizer_version: str
    lineage: tuple[FieldLineage, ...] = Field(min_length=1)


class ListingStateStore(Protocol):
    def persist(self, write: ListingStateWrite) -> str: ...

    def state_history(
        self,
        listing_id: str,
        *,
        as_of: AwareDatetime | None = None,
    ) -> tuple[PersistedListingState, ...]: ...

    def states_for_raw_snapshots(
        self,
        raw_snapshot_ids: Sequence[str],
        *,
        listing_ids: Sequence[str] | None = None,
    ) -> tuple[PersistedListingState, ...]: ...


class SQLiteListingStateStore:
    """Append-only listing-state observations with exact raw field lineage."""

    def __init__(self, path: Path) -> None:
        self.database = SQLiteDatabase(path)

    @property
    def path(self) -> Path:
        return self.database.path

    def persist(self, write: ListingStateWrite) -> str:
        write = ListingStateWrite.model_validate(write.model_dump(mode="python"))
        observation_id = _observation_id(write)
        with self.database.connect() as connection:
            listing = connection.execute(
                "SELECT id FROM platform_listings WHERE id = ?",
                (write.observation.platform_listing_id,),
            ).fetchone()
            if listing is None:
                raise ValueError(
                    f"listing {write.observation.platform_listing_id} "
                    "must be persisted before listing state"
                )
            self._persist_rows(connection, observation_id, write)
            persist_lineage_in_connection(connection, observation_id, write.lineage)
            stored = self._load_one(connection, observation_id)
            if stored is None:
                raise RuntimeError("listing-state observation was not persisted")
            if stored != _persisted_from_write(observation_id, write):
                raise ValueError(f"conflicting listing-state observation {observation_id}")
        return observation_id

    def state_history(
        self,
        listing_id: str,
        *,
        as_of: AwareDatetime | None = None,
    ) -> tuple[PersistedListingState, ...]:
        query = _SELECT + " WHERE s.platform_listing_id = ?"
        params: list[object] = [listing_id]
        if as_of is not None:
            _require_aware(as_of, "as_of")
            query += " AND n.observed_at <= ?"
            params.append(_timestamp(as_of))
        query += " ORDER BY n.observed_at, n.retrieved_at, n.id"
        with self.database.connect() as connection:
            rows = connection.execute(query, params).fetchall()
            return tuple(self._row_to_persisted(connection, row) for row in rows)

    def states_for_raw_snapshots(
        self,
        raw_snapshot_ids: Sequence[str],
        *,
        listing_ids: Sequence[str] | None = None,
    ) -> tuple[PersistedListingState, ...]:
        raw_ids = _unique_non_blank(raw_snapshot_ids, "raw_snapshot_ids")
        if not raw_ids:
            return ()
        placeholders = ", ".join("?" for _ in raw_ids)
        query = (
            _SELECT
            + " WHERE EXISTS ("
            + "SELECT 1 FROM observation_lineage AS l "
            + "WHERE l.normalized_observation_id = n.id "
            + f"AND l.raw_snapshot_id IN ({placeholders})"
            + ")"
        )
        params: list[object] = list(raw_ids)
        if listing_ids is not None:
            listing_values = _unique_non_blank(listing_ids, "listing_ids")
            if not listing_values:
                return ()
            listing_placeholders = ", ".join("?" for _ in listing_values)
            query += f" AND s.platform_listing_id IN ({listing_placeholders})"
            params.extend(listing_values)
        query += " ORDER BY n.observed_at, n.retrieved_at, n.id"
        with self.database.connect() as connection:
            rows = connection.execute(query, params).fetchall()
            return tuple(self._row_to_persisted(connection, row) for row in rows)

    @staticmethod
    def _persist_rows(
        connection: sqlite3.Connection,
        observation_id: str,
        write: ListingStateWrite,
    ) -> None:
        evidence = write.evidence
        state = write.observation
        connection.execute(
            """
            INSERT OR IGNORE INTO normalized_observations (
                id, source_id, observation_type, observed_at, available_at,
                retrieved_at, normalizer_name, normalizer_version
            ) VALUES (?, ?, 'listing_state', ?, ?, ?, ?, ?)
            """,
            (
                observation_id,
                evidence.source_id,
                _timestamp(evidence.observed_at),
                _optional_timestamp(evidence.available_at),
                _timestamp_required(evidence.retrieved_at),
                write.normalizer_name,
                write.normalizer_version,
            ),
        )
        connection.execute(
            """
            INSERT OR IGNORE INTO listing_state_observations (
                observation_id, platform_listing_id, title, developer_id, developer_name,
                app_version, published_at, languages_json, supported_platforms_json,
                orientation, cloud_save, leaderboards, purchases_enabled, has_products,
                rewarded_ads, fullscreen_ads, sticky_ads, provenance, measurement_kind,
                semantic_confidence, coverage_status, historical_availability,
                revision_status, uncertainty_json, lineage_refs_json
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                observation_id,
                state.platform_listing_id,
                state.title,
                state.developer_id,
                state.developer_name,
                state.app_version,
                _optional_timestamp(state.published_at),
                _json_tuple(state.languages),
                _json_tuple(state.supported_platforms),
                state.orientation,
                _optional_bool(state.cloud_save),
                _optional_bool(state.leaderboards),
                _optional_bool(state.purchases_enabled),
                _optional_bool(state.has_products),
                _optional_bool(state.rewarded_ads),
                _optional_bool(state.fullscreen_ads),
                _optional_bool(state.sticky_ads),
                evidence.provenance.value,
                evidence.measurement_kind.value,
                evidence.semantic_confidence.value,
                evidence.coverage_status.value,
                evidence.historical_availability.value,
                evidence.revision_status.value,
                _json_or_none(evidence.uncertainty),
                _lineage_refs_json(evidence),
            ),
        )

    def _load_one(
        self,
        connection: sqlite3.Connection,
        observation_id: str,
    ) -> PersistedListingState | None:
        row = connection.execute(_SELECT + " WHERE n.id = ?", (observation_id,)).fetchone()
        return None if row is None else self._row_to_persisted(connection, row)

    @staticmethod
    def _row_to_persisted(
        connection: sqlite3.Connection,
        row: sqlite3.Row,
    ) -> PersistedListingState:
        if str(row["observation_type"]) != "listing_state":
            raise RuntimeError("stored listing-state observation_type is invalid")
        lineage_rows = connection.execute(
            """
            SELECT raw_snapshot_id, source_field_path, target_field_path,
                   transformation_name, transformation_version
            FROM observation_lineage
            WHERE normalized_observation_id = ?
            ORDER BY raw_snapshot_id, source_field_path, target_field_path
            """,
            (str(row["id"]),),
        ).fetchall()
        lineage = tuple(
            FieldLineage(
                raw_snapshot_id=str(item["raw_snapshot_id"]),
                source_field_path=str(item["source_field_path"]),
                target_field_path=str(item["target_field_path"]),
                transformation_name=str(item["transformation_name"]),
                transformation_version=str(item["transformation_version"]),
            )
            for item in lineage_rows
        )
        if not lineage:
            raise RuntimeError("stored listing-state observation is missing field lineage")
        return PersistedListingState(
            observation_id=str(row["id"]),
            observation=ListingStateObservation(
                platform_listing_id=str(row["platform_listing_id"]),
                observed_at=_parse_timestamp(str(row["observed_at"])),
                title=_optional_str(row["title"]),
                developer_id=_optional_str(row["developer_id"]),
                developer_name=_optional_str(row["developer_name"]),
                app_version=_optional_str(row["app_version"]),
                published_at=_parse_optional_timestamp(row["published_at"]),
                languages=_parse_json_tuple(row["languages_json"]),
                supported_platforms=_parse_json_tuple(row["supported_platforms_json"]),
                orientation=_optional_str(row["orientation"]),
                cloud_save=_parse_optional_bool(row["cloud_save"]),
                leaderboards=_parse_optional_bool(row["leaderboards"]),
                purchases_enabled=_parse_optional_bool(row["purchases_enabled"]),
                has_products=_parse_optional_bool(row["has_products"]),
                rewarded_ads=_parse_optional_bool(row["rewarded_ads"]),
                fullscreen_ads=_parse_optional_bool(row["fullscreen_ads"]),
                sticky_ads=_parse_optional_bool(row["sticky_ads"]),
            ),
            evidence=EvidenceEnvelope.model_validate(
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
                    "uncertainty": _parse_json(row["uncertainty_json"]),
                    "lineage_refs": tuple(_parse_json_list(row["lineage_refs_json"])),
                }
            ),
            normalizer_name=str(row["normalizer_name"]),
            normalizer_version=str(row["normalizer_version"]),
            lineage=lineage,
        )


_SELECT = """
SELECT
    n.id, n.source_id, n.observation_type, n.observed_at, n.available_at,
    n.retrieved_at, n.normalizer_name, n.normalizer_version,
    s.platform_listing_id, s.title, s.developer_id, s.developer_name, s.app_version,
    s.published_at, s.languages_json, s.supported_platforms_json, s.orientation,
    s.cloud_save, s.leaderboards, s.purchases_enabled, s.has_products, s.rewarded_ads,
    s.fullscreen_ads, s.sticky_ads, s.provenance, s.measurement_kind,
    s.semantic_confidence, s.coverage_status, s.historical_availability,
    s.revision_status, s.uncertainty_json, s.lineage_refs_json
FROM normalized_observations AS n
JOIN listing_state_observations AS s ON s.observation_id = n.id
"""


def _observation_id(write: ListingStateWrite) -> str:
    payload = {
        "source_id": write.evidence.source_id,
        "observation_type": "listing_state",
        "platform_listing_id": write.observation.platform_listing_id,
        "observed_at": _timestamp(write.evidence.observed_at),
        "available_at": _optional_timestamp(write.evidence.available_at),
        "retrieved_at": _timestamp_required(write.evidence.retrieved_at),
        "normalizer_name": write.normalizer_name,
        "normalizer_version": write.normalizer_version,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return "state:" + hashlib.sha256(encoded).hexdigest()[:32]


def _persisted_from_write(
    observation_id: str,
    write: ListingStateWrite,
) -> PersistedListingState:
    evidence = write.evidence.model_copy(
        update={"lineage_refs": tuple(sorted(set(write.evidence.lineage_refs)))}
    )
    return PersistedListingState(
        observation_id=observation_id,
        observation=write.observation,
        evidence=evidence,
        normalizer_name=write.normalizer_name,
        normalizer_version=write.normalizer_version,
        lineage=tuple(
            sorted(
                write.lineage,
                key=lambda item: (
                    item.raw_snapshot_id,
                    item.source_field_path,
                    item.target_field_path,
                ),
            )
        ),
    )


def _unique_non_blank(values: Sequence[str], field: str) -> tuple[str, ...]:
    normalized = tuple(values)
    if any(not item or item != item.strip() for item in normalized):
        raise ValueError(f"{field} must contain non-blank already-trimmed values")
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field} must be unique")
    return normalized


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


def _optional_bool(value: bool | None) -> int | None:
    return None if value is None else int(value)


def _parse_optional_bool(value: object) -> bool | None:
    if value is None:
        return None
    integer = int(value)
    if integer not in {0, 1}:
        raise ValueError("stored listing-state boolean is invalid")
    return bool(integer)


def _json_tuple(value: tuple[str, ...] | None) -> str | None:
    return None if value is None else json.dumps(value, separators=(",", ":"))


def _parse_json_tuple(value: object) -> tuple[str, ...] | None:
    if value is None:
        return None
    parsed = json.loads(str(value))
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        raise ValueError("stored listing-state string tuple is invalid")
    return tuple(parsed)


def _json_or_none(value: BaseModel | None) -> str | None:
    if value is None:
        return None
    return json.dumps(
        value.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )


def _parse_json(value: object) -> object | None:
    return None if value is None else json.loads(str(value))


def _lineage_refs_json(evidence: EvidenceEnvelope) -> str:
    return json.dumps(sorted(set(evidence.lineage_refs)), separators=(",", ":"))


def _parse_json_list(value: object) -> list[str]:
    parsed = json.loads(str(value))
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        raise ValueError("stored lineage_refs_json is invalid")
    return parsed
