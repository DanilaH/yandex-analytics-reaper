from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from math import isfinite
from pathlib import Path
from typing import Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from yandex_analytics_reaper.domain import GameMetricName
from yandex_analytics_reaper.storage import (
    FilesystemRawSnapshotStore,
    PersistedListingMedia,
    PersistedListingUpdate,
    PersistedMetricObservation,
    SQLiteCollectionCadencePlanStore,
    SQLiteIdentityStore,
    SQLiteLineageStore,
    SQLiteListingHistoryStore,
    SQLiteMetricStore,
    SQLiteQueryFamilyStore,
    StoredCollectionCadencePlan,
)

from .collection_cadence import (
    ANALYZER_VERSION,
    MIN_LISTING_SERIES,
    MIN_REFERENCE_DAYS,
    SPEC_VERSION,
    CadenceStateSignal,
    CollectionCadenceReport,
    StateReferencePoint,
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

_SOURCE_ID = "yandex_public"
_FREEZE_GUARD = timedelta(hours=2)
_MIN_DAILY_SPACING = timedelta(hours=22)
_MAX_DAILY_SPACING = timedelta(hours=26)
_MAX_CLOCK_BAND_SECONDS = 2 * 60 * 60
_DAY_SECONDS = 24 * 60 * 60


class CollectionCadencePlanDeclaration(BaseModel):
    """Cohort and checkpoint schedule that must be frozen before collection begins."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: str = SPEC_VERSION
    plan_id: str
    listing_ids: tuple[str, ...] = Field(min_length=MIN_LISTING_SERIES)
    query_family_id: str
    query_family_version: int = Field(ge=1)
    checkpoint_at: tuple[AwareDatetime, ...] = Field(min_length=MIN_REFERENCE_DAYS)

    @field_validator("plan_id", "query_family_id")
    @classmethod
    def validate_ids(cls, value: str) -> str:
        return _require_exact_non_blank(value, "cadence plan identifier")

    @field_validator("listing_ids")
    @classmethod
    def validate_listing_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(_listing_id(item) for item in value)
        if len(normalized) != len(set(normalized)):
            raise ValueError("cadence listing cohort must contain unique listing IDs")
        return normalized

    @model_validator(mode="after")
    def validate_plan(self) -> Self:
        if self.spec_version != SPEC_VERSION:
            raise ValueError(f"cadence plan must use spec_version={SPEC_VERSION}")
        _validate_checkpoint_schedule(self.checkpoint_at)
        return self


class CollectionCadenceManifest(BaseModel):
    """Post-collection run bindings against one already frozen cadence plan."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: str = SPEC_VERSION
    plan_id: str
    checkpoints: tuple[CadenceCheckpointInput, ...] = Field(min_length=MIN_REFERENCE_DAYS)

    @field_validator("plan_id")
    @classmethod
    def validate_plan_id(cls, value: str) -> str:
        return _require_exact_non_blank(value, "plan_id")

    @model_validator(mode="after")
    def validate_manifest(self) -> Self:
        if self.spec_version != SPEC_VERSION:
            raise ValueError(f"cadence manifest must use spec_version={SPEC_VERSION}")
        run_ids = [
            run_id
            for checkpoint in self.checkpoints
            for run_id in (checkpoint.feed_run_id, *checkpoint.search_run_ids)
        ]
        if len(run_ids) != len(set(run_ids)):
            raise ValueError("cadence manifest cannot reuse a probe run across checkpoints")
        return self

    def evidence_manifest(self, plan: StoredCollectionCadencePlan) -> _EvidenceManifest:
        submitted_times = tuple(item.checkpoint_at for item in self.checkpoints)
        if tuple(_utc(value) for value in submitted_times) != tuple(
            _utc(value) for value in plan.checkpoint_at
        ):
            raise CollectionCadenceEvidenceError(
                "cadence evidence checkpoint schedule differs from the frozen plan"
            )
        return _EvidenceManifest(
            listing_ids=plan.listing_ids,
            query_family_id=plan.query_family_id,
            query_family_version=plan.query_family_version,
            checkpoints=self.checkpoints,
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
    plan_id: str
    plan_hash: str
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


class CollectionCadencePlanFreezer:
    """Freeze a calibration cohort/window before any eligible checkpoint can begin."""

    def __init__(self, database_path: Path) -> None:
        self.identity_store = SQLiteIdentityStore(database_path)
        self.query_family_store = SQLiteQueryFamilyStore(database_path)
        self.plan_store = SQLiteCollectionCadencePlanStore(database_path)

    def freeze(
        self,
        declaration: CollectionCadencePlanDeclaration,
    ) -> StoredCollectionCadencePlan:
        current_time = self.plan_store.current_time()
        latest_freeze_at = _utc(declaration.checkpoint_at[0]) - _FREEZE_GUARD
        if current_time > latest_freeze_at:
            raise CollectionCadenceEvidenceError(
                "collection cadence plan must be frozen at least two hours before "
                "the first checkpoint"
            )
        family = self.query_family_store.get(
            declaration.query_family_id,
            declaration.query_family_version,
        )
        if family is None:
            raise CollectionCadenceEvidenceError(
                "cadence query-family version does not exist in operational storage"
            )
        if family.source_id != _SOURCE_ID:
            raise CollectionCadenceEvidenceError(
                f"cadence query family must use source_id={_SOURCE_ID}"
            )
        if family.created_at.astimezone(UTC) > current_time:
            raise CollectionCadenceEvidenceError(
                "cadence query-family version cannot be dated after plan freeze time"
            )
        for listing_id in declaration.listing_ids:
            listing = self.identity_store.get_listing(listing_id)
            if listing is None:
                raise CollectionCadenceEvidenceError(
                    f"cadence listing cohort member does not exist: {listing_id}"
                )
            if listing.first_seen_at is None:
                raise CollectionCadenceEvidenceError(
                    f"cadence listing cohort member has no first_seen_at: {listing_id}"
                )
            if listing.first_seen_at.astimezone(UTC) > current_time:
                raise CollectionCadenceEvidenceError(
                    f"cadence listing cohort member is dated after plan freeze: {listing_id}"
                )
        try:
            return self.plan_store.freeze(
                plan_id=declaration.plan_id,
                spec_version=declaration.spec_version,
                query_family_id=declaration.query_family_id,
                query_family_version=declaration.query_family_version,
                listing_ids=declaration.listing_ids,
                checkpoint_at=declaration.checkpoint_at,
                latest_freeze_at=latest_freeze_at,
            )
        except ValueError as exc:
            raise CollectionCadenceEvidenceError(str(exc)) from exc


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
    """Audit explicit run bindings against one immutable predeclared cadence plan."""

    def __init__(
        self,
        *,
        raw_store: FilesystemRawSnapshotStore,
        database_path: Path,
    ) -> None:
        self.identity_store = SQLiteIdentityStore(database_path)
        self.metric_store = SQLiteMetricStore(database_path)
        self.history_store = SQLiteListingHistoryStore(database_path)
        self.lineage_store = SQLiteLineageStore(database_path)
        self.query_family_store = SQLiteQueryFamilyStore(database_path)
        self.plan_store = SQLiteCollectionCadencePlanStore(database_path)
        self.evidence_experiment = _AuditedEvidenceExperiment(
            raw_store=raw_store,
            database_path=database_path,
        )

    def analyze(
        self,
        manifest: CollectionCadenceManifest,
    ) -> CollectionCadenceExperimentReport:
        plan = self.plan_store.get(manifest.plan_id)
        if plan is None:
            raise CollectionCadenceEvidenceError(
                f"collection cadence plan does not exist: {manifest.plan_id}"
            )
        declaration = _validate_stored_plan(plan)
        frozen_at = plan.frozen_at.astimezone(UTC)
        if frozen_at > _utc(declaration.checkpoint_at[0]) - _FREEZE_GUARD:
            raise CollectionCadenceEvidenceError(
                "stored collection cadence plan was frozen too late"
            )

        family = self.query_family_store.get(
            plan.query_family_id,
            plan.query_family_version,
        )
        if family is None:
            raise CollectionCadenceEvidenceError(
                "cadence query-family version does not exist in operational storage"
            )
        if family.created_at.astimezone(UTC) > frozen_at:
            raise CollectionCadenceEvidenceError(
                "cadence query-family version was created after the frozen plan"
            )
        for listing_id in plan.listing_ids:
            listing = self.identity_store.get_listing(listing_id)
            if listing is None:
                raise CollectionCadenceEvidenceError(
                    f"cadence listing cohort member does not exist: {listing_id}"
                )
            if listing.first_seen_at is None:
                raise CollectionCadenceEvidenceError(
                    f"cadence listing cohort member has no first_seen_at: {listing_id}"
                )
            if listing.first_seen_at.astimezone(UTC) > frozen_at:
                raise CollectionCadenceEvidenceError(
                    f"cadence listing cohort member was first seen after plan freeze: {listing_id}"
                )

        evidence_manifest = manifest.evidence_manifest(plan)
        try:
            evidence_report = self.evidence_experiment.analyze(evidence_manifest)
        except RuntimeError as exc:
            raise CollectionCadenceEvidenceError(
                f"cadence operational evidence is invalid: {exc}"
            ) from exc

        state_evidence = self._state_evidence(
            plan.listing_ids,
            manifest.checkpoints,
            set(evidence_report.eligible_state_series_ids),
        )
        return CollectionCadenceExperimentReport(
            plan_id=plan.plan_id,
            plan_hash=plan.content_hash,
            manifest_id=_manifest_id(manifest),
            frozen_at=plan.frozen_at,
            listing_ids=plan.listing_ids,
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
        listing_ids: Sequence[str],
        checkpoints: Sequence[CadenceCheckpointInput],
        eligible_series_ids: set[str],
    ) -> tuple[CadenceStateSeriesEvidence, ...]:
        evidence: list[CadenceStateSeriesEvidence] = []
        for listing_id in listing_ids:
            for signal in CadenceStateSignal:
                series_id = f"state:{listing_id}:{signal.value}"
                if series_id not in eligible_series_ids:
                    continue
                points = self._state_evidence_points(
                    listing_id,
                    signal,
                    checkpoints,
                )
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
        checkpoints: Sequence[CadenceCheckpointInput],
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
        for checkpoint in checkpoints:
            observation_id: str | None = None
            if metric_history is not None:
                metric_observation = _latest_metric(
                    metric_history,
                    checkpoint.checkpoint_at,
                )
                if metric_observation is not None:
                    observation_id = metric_observation.observation_id
            elif media_history is not None:
                media_observation = _latest_media(
                    media_history,
                    checkpoint.checkpoint_at,
                )
                if media_observation is not None:
                    observation_id = media_observation.observation_id
            elif update_history is not None:
                update_observation = _latest_update(
                    update_history,
                    checkpoint.checkpoint_at,
                )
                if update_observation is not None:
                    observation_id = update_observation.observation_id
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


def _validate_stored_plan(
    plan: StoredCollectionCadencePlan,
) -> CollectionCadencePlanDeclaration:
    if plan.spec_version != SPEC_VERSION:
        raise CollectionCadenceEvidenceError(
            f"stored cadence plan must use spec_version={SPEC_VERSION}"
        )
    try:
        return CollectionCadencePlanDeclaration(
            spec_version=plan.spec_version,
            plan_id=plan.plan_id,
            listing_ids=plan.listing_ids,
            query_family_id=plan.query_family_id,
            query_family_version=plan.query_family_version,
            checkpoint_at=plan.checkpoint_at,
        )
    except ValidationError as exc:
        raise CollectionCadenceEvidenceError(
            f"stored collection cadence plan is invalid: {exc}"
        ) from exc


def _validate_checkpoint_schedule(values: Sequence[datetime]) -> None:
    utc_times = tuple(_utc(value) for value in values)
    if any(
        current <= previous
        for previous, current in zip(utc_times, utc_times[1:], strict=False)
    ):
        raise ValueError("cadence checkpoints must be strictly increasing")
    dates = tuple(item.date() for item in utc_times)
    if len(dates) != len(set(dates)):
        raise ValueError("cadence plan must contain one checkpoint per UTC date")
    for previous, current in zip(dates, dates[1:], strict=False):
        if (current - previous).days != 1:
            raise ValueError("cadence checkpoint UTC dates must be consecutive")
    for previous, current in zip(utc_times, utc_times[1:], strict=False):
        spacing = current - previous
        if not _MIN_DAILY_SPACING <= spacing <= _MAX_DAILY_SPACING:
            raise ValueError("cadence checkpoints must be spaced 22 to 26 hours apart")
    clock_seconds = tuple(
        item.hour * 3600 + item.minute * 60 + item.second for item in utc_times
    )
    if _circular_clock_span_seconds(clock_seconds) > _MAX_CLOCK_BAND_SECONDS:
        raise ValueError("cadence checkpoint UTC clock times must fit one two-hour band")


def _circular_clock_span_seconds(values: Sequence[int]) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    if len(ordered) == 1:
        return 0
    gaps = [
        current - previous
        for previous, current in zip(ordered, ordered[1:], strict=False)
    ]
    gaps.append(_DAY_SECONDS - ordered[-1] + ordered[0])
    return _DAY_SECONDS - max(gaps)


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


def _listing_id(value: str) -> str:
    normalized = _require_exact_non_blank(value, "listing_id")
    prefix = "yandex_games:"
    if not normalized.startswith(prefix):
        raise ValueError("cadence listing IDs must use yandex_games:<appID>")
    suffix = normalized.removeprefix(prefix)
    if not suffix.isdigit():
        raise ValueError("cadence listing ID appID must be numeric")
    return normalized


def _require_exact_non_blank(value: str, field: str) -> str:
    if not value:
        raise ValueError(f"{field} cannot be blank")
    if value != value.strip():
        raise ValueError(f"{field} must already be trimmed")
    return value


def _checkpoint_label(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _optional_timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("cadence timestamps must be timezone-aware")
    return value.astimezone(UTC)
