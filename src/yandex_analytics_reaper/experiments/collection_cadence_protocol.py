from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from math import isfinite
from pathlib import Path
from typing import Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError, model_validator

from yandex_analytics_reaper.domain import GameMetricName
from yandex_analytics_reaper.storage import (
    FilesystemRawSnapshotStore,
    PersistedListingMedia,
    PersistedListingUpdate,
    PersistedMetricObservation,
    SQLiteLineageStore,
    SQLiteListingHistoryStore,
    SQLiteMetricStore,
    SQLiteQueryFamilyStore,
)

from .collection_cadence import (
    ANALYZER_VERSION,
    MIN_LISTING_SERIES,
    MIN_REFERENCE_DAYS,
    SPEC_VERSION,
    CadenceCapability,
    CadenceStateSignal,
    CollectionCadenceReport,
    StateReferencePoint,
    StateSeriesObservation,
)
from .collection_cadence_evidence import (
    CadenceCheckpointInput,
    CollectionCadenceEvidenceError,
    CollectionCadenceExperiment as _EvidenceExperiment,
    CollectionCadenceManifest as _EvidenceManifest,
    RejectedCadenceSeries,
    _latest_media,
    _latest_metric,
    _latest_update,
)

_FREEZE_GUARD = timedelta(hours=2)


class CollectionCadenceManifest(BaseModel):
    """Predeclared cadence cohort plus exact daily probe-run bindings."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: str = SPEC_VERSION
    frozen_at: AwareDatetime
    listing_ids: tuple[str, ...] = Field(min_length=MIN_LISTING_SERIES)
    query_family_id: str
    query_family_version: int = Field(ge=1)
    checkpoints: tuple[CadenceCheckpointInput, ...] = Field(min_length=MIN_REFERENCE_DAYS)

    @model_validator(mode="after")
    def validate_manifest(self) -> Self:
        _EvidenceManifest.model_validate(
            self.model_dump(mode="python", exclude={"frozen_at"})
        )
        first_checkpoint = self.checkpoints[0].checkpoint_at.astimezone(UTC)
        if self.frozen_at.astimezone(UTC) > first_checkpoint - _FREEZE_GUARD:
            raise ValueError(
                "cadence manifest frozen_at must be no later than two hours before "
                "the first checkpoint"
            )
        return self

    def evidence_manifest(self) -> _EvidenceManifest:
        return _EvidenceManifest.model_validate(
            self.model_dump(mode="python", exclude={"frozen_at"})
        )


class CadenceStateEvidencePoint(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    reference_date: date
    observation_id: str
    raw_snapshot_ids: tuple[str, ...] = Field(min_length=1)


class CadenceStateSeriesEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    series_id: str
    points: tuple[CadenceStateEvidencePoint, ...] = Field(min_length=MIN_REFERENCE_DAYS)


class CollectionCadenceExperimentReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: str = SPEC_VERSION
    analyzer_version: str = ANALYZER_VERSION
    manifest_id: str
    frozen_at: AwareDatetime
    listing_ids: tuple[str, ...]
    query_family_id: str
    query_family_version: int
    checkpoints: tuple[CadenceCheckpointInput, ...]
    eligible_state_series_ids: tuple[str, ...]
    eligible_ranking_series_ids: tuple[str, ...]
    state_evidence: tuple[CadenceStateSeriesEvidence, ...]
    rejected_series: tuple[RejectedCadenceSeries, ...]
    analysis: CollectionCadenceReport


class _AuditedEvidenceExperiment(_EvidenceExperiment):
    """Keep the frozen evidence rules while surfacing corrupt state series cleanly."""

    def _metric_points(
        self,
        listing_id: str,
        metric_name: GameMetricName,
        manifest: _EvidenceManifest,
    ) -> tuple[StateReferencePoint, ...]:
        try:
            history = self.metric_store.metric_history(listing_id, metric_name)
        except (RuntimeError, ValidationError) as exc:
            raise CollectionCadenceEvidenceError(
                f"{listing_id}/{metric_name.value} metric history is invalid: {exc}"
            ) from exc
        points: list[StateReferencePoint] = []
        for checkpoint in manifest.checkpoints:
            observation = _latest_metric(history, checkpoint.checkpoint_at)
            if observation is None:
                raise CollectionCadenceEvidenceError(
                    f"{listing_id}/{metric_name.value} has no eligible observation for "
                    f"{_checkpoint_label(checkpoint.checkpoint_at)}"
                )
            self._validate_metric_evidence(observation)
            points.append(
                StateReferencePoint(
                    reference_date=checkpoint.checkpoint_at.astimezone(UTC).date(),
                    value=_canonical_numeric(observation.metric.value),
                )
            )
        return tuple(points)

    def _media_points(
        self,
        listing_id: str,
        manifest: _EvidenceManifest,
    ) -> tuple[StateReferencePoint, ...]:
        try:
            history = self.history_store.media_history(listing_id)
        except (RuntimeError, ValidationError) as exc:
            raise CollectionCadenceEvidenceError(
                f"{listing_id}/media history is invalid: {exc}"
            ) from exc
        points: list[StateReferencePoint] = []
        for checkpoint in manifest.checkpoints:
            observation = _latest_media(history, checkpoint.checkpoint_at)
            if observation is None:
                raise CollectionCadenceEvidenceError(
                    f"{listing_id}/media has no eligible observation for "
                    f"{_checkpoint_label(checkpoint.checkpoint_at)}"
                )
            self._validate_history_evidence(observation.observation_id, observation)
            points.append(
                StateReferencePoint(
                    reference_date=checkpoint.checkpoint_at.astimezone(UTC).date(),
                    value=observation.observation.manifest_hash,
                )
            )
        return tuple(points)

    def _update_points(
        self,
        listing_id: str,
        manifest: _EvidenceManifest,
    ) -> tuple[StateReferencePoint, ...]:
        try:
            history = self.history_store.update_history(listing_id)
        except (RuntimeError, ValidationError) as exc:
            raise CollectionCadenceEvidenceError(
                f"{listing_id}/game-page update history is invalid: {exc}"
            ) from exc
        points: list[StateReferencePoint] = []
        for checkpoint in manifest.checkpoints:
            observation = _latest_update(history, checkpoint.checkpoint_at)
            if observation is None:
                raise CollectionCadenceEvidenceError(
                    f"{listing_id}/game-page update has no eligible observation for "
                    f"{_checkpoint_label(checkpoint.checkpoint_at)}"
                )
            self._validate_history_evidence(observation.observation_id, observation)
            points.append(
                StateReferencePoint(
                    reference_date=checkpoint.checkpoint_at.astimezone(UTC).date(),
                    value=json.dumps(
                        {
                            "app_version": observation.observation.app_version,
                            "source_published_at": _optional_timestamp(
                                observation.observation.source_published_at
                            ),
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                )
            )
        return tuple(points)


class CollectionCadenceExperiment:
    """Audit a frozen collection-cadence manifest against persisted raw-first evidence."""

    def __init__(
        self,
        *,
        raw_store: FilesystemRawSnapshotStore,
        database_path: Path,
    ) -> None:
        self.raw_store = raw_store
        self.database_path = database_path
        self.metric_store = SQLiteMetricStore(database_path)
        self.history_store = SQLiteListingHistoryStore(database_path)
        self.lineage_store = SQLiteLineageStore(database_path)
        self.query_family_store = SQLiteQueryFamilyStore(database_path)
        self.evidence_experiment = _AuditedEvidenceExperiment(
            raw_store=raw_store,
            database_path=database_path,
        )

    def analyze(
        self,
        manifest: CollectionCadenceManifest,
    ) -> CollectionCadenceExperimentReport:
        family = self.query_family_store.get(
            manifest.query_family_id,
            manifest.query_family_version,
        )
        if family is None:
            raise CollectionCadenceEvidenceError(
                "cadence query-family version does not exist in operational storage"
            )
        if family.created_at.astimezone(UTC) > manifest.frozen_at.astimezone(UTC):
            raise CollectionCadenceEvidenceError(
                "cadence query-family version must exist no later than manifest frozen_at"
            )

        evidence_manifest = manifest.evidence_manifest()
        try:
            evidence_report = self.evidence_experiment.analyze(evidence_manifest)
        except RuntimeError as exc:
            raise CollectionCadenceEvidenceError(
                f"cadence operational evidence is invalid: {exc}"
            ) from exc

        state_evidence = self._state_evidence(
            manifest,
            set(evidence_report.eligible_state_series_ids),
        )
        return CollectionCadenceExperimentReport(
            manifest_id=_manifest_id(manifest),
            frozen_at=manifest.frozen_at,
            listing_ids=manifest.listing_ids,
            query_family_id=evidence_report.query_family_id,
            query_family_version=evidence_report.query_family_version,
            checkpoints=manifest.checkpoints,
            eligible_state_series_ids=evidence_report.eligible_state_series_ids,
            eligible_ranking_series_ids=evidence_report.eligible_ranking_series_ids,
            state_evidence=state_evidence,
            rejected_series=evidence_report.rejected_series,
            analysis=evidence_report.analysis,
        )

    def _state_evidence(
        self,
        manifest: CollectionCadenceManifest,
        eligible_series_ids: set[str],
    ) -> tuple[CadenceStateSeriesEvidence, ...]:
        evidence: list[CadenceStateSeriesEvidence] = []
        for listing_id in manifest.listing_ids:
            for signal in CadenceStateSignal:
                series_id = f"state:{listing_id}:{signal.value}"
                if series_id not in eligible_series_ids:
                    continue
                points = self._state_evidence_points(listing_id, signal, manifest)
                evidence.append(
                    CadenceStateSeriesEvidence(series_id=series_id, points=points)
                )
        if {item.series_id for item in evidence} != eligible_series_ids:
            raise RuntimeError("cadence state evidence did not reconcile with eligible series")
        return tuple(evidence)

    def _state_evidence_points(
        self,
        listing_id: str,
        signal: CadenceStateSignal,
        manifest: CollectionCadenceManifest,
    ) -> tuple[CadenceStateEvidencePoint, ...]:
        metric_history: tuple[PersistedMetricObservation, ...] | None = None
        media_history: tuple[PersistedListingMedia, ...] | None = None
        update_history: tuple[PersistedListingUpdate, ...] | None = None
        if signal is CadenceStateSignal.YANDEX_GAMES_RATING:
            metric_history = self.metric_store.metric_history(
                listing_id,
                GameMetricName.YANDEX_GAMES_RATING,
            )
        elif signal is CadenceStateSignal.RATING_COUNT:
            metric_history = self.metric_store.metric_history(
                listing_id,
                GameMetricName.RATING_COUNT,
            )
        elif signal is CadenceStateSignal.MEDIA_MANIFEST:
            media_history = self.history_store.media_history(listing_id)
        elif signal is CadenceStateSignal.GAME_PAGE_UPDATE:
            update_history = self.history_store.update_history(listing_id)
        else:
            raise RuntimeError(f"unsupported cadence state signal: {signal.value}")

        points: list[CadenceStateEvidencePoint] = []
        for checkpoint in manifest.checkpoints:
            observation_id: str | None = None
            if metric_history is not None:
                observation = _latest_metric(metric_history, checkpoint.checkpoint_at)
                observation_id = None if observation is None else observation.observation_id
            elif media_history is not None:
                observation = _latest_media(media_history, checkpoint.checkpoint_at)
                observation_id = None if observation is None else observation.observation_id
            elif update_history is not None:
                observation = _latest_update(update_history, checkpoint.checkpoint_at)
                observation_id = None if observation is None else observation.observation_id
            if observation_id is None:
                raise RuntimeError(
                    f"eligible cadence series {listing_id}/{signal.value} lost its evidence"
                )
            lineage = self.lineage_store.for_observation(observation_id)
            raw_snapshot_ids = tuple(sorted({item.raw_snapshot_id for item in lineage}))
            if not raw_snapshot_ids:
                raise RuntimeError(
                    f"eligible cadence observation {observation_id} lost its raw lineage"
                )
            points.append(
                CadenceStateEvidencePoint(
                    reference_date=checkpoint.checkpoint_at.astimezone(UTC).date(),
                    observation_id=observation_id,
                    raw_snapshot_ids=raw_snapshot_ids,
                )
            )
        return tuple(points)


def _manifest_id(manifest: CollectionCadenceManifest) -> str:
    encoded = json.dumps(
        manifest.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "collection-cadence-manifest:" + hashlib.sha256(encoded).hexdigest()[:32]


def _canonical_numeric(value: int | float) -> str:
    if isinstance(value, float) and not isfinite(value):
        raise CollectionCadenceEvidenceError("cadence metric value must be finite")
    return json.dumps(value, allow_nan=False, separators=(",", ":"))


def _checkpoint_label(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _optional_timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
