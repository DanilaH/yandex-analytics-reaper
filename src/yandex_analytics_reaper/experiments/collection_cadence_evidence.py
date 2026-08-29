from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from math import isfinite
from pathlib import Path
from typing import Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from yandex_analytics_reaper.domain import (
    GameMetricName,
    ProbeContext,
    ProbeKind,
    ProbePage,
    ProbeRunStatus,
    QueryFamilyVersion,
    SessionProfile,
)
from yandex_analytics_reaper.evidence import MeasurementKind, Provenance
from yandex_analytics_reaper.normalizers import (
    YandexGameNormalizer,
    YandexListingHistoryNormalizer,
)
from yandex_analytics_reaper.sources.yandex.parsers import YandexFeedParser
from yandex_analytics_reaper.sources.yandex.probes import probe_page_from_yandex
from yandex_analytics_reaper.storage import (
    FilesystemRawSnapshotStore,
    PersistedListingMedia,
    PersistedListingUpdate,
    PersistedMetricObservation,
    ProbeRunRecord,
    SQLiteLineageStore,
    SQLiteListingHistoryStore,
    SQLiteMetricStore,
    SQLiteProbeRunStore,
    SQLiteQueryFamilyStore,
)

from .collection_cadence import (
    ANALYZER_VERSION,
    MIN_LISTING_SERIES,
    MIN_REFERENCE_DAYS,
    RANKING_DEPTHS,
    SPEC_VERSION,
    CadenceCapability,
    CadenceStateSignal,
    CollectionCadenceReport,
    RankingReferencePoint,
    RankingSeriesObservation,
    StateReferencePoint,
    StateSeriesObservation,
    evaluate_collection_cadence,
)
from .feed_depth import FeedDepthEligibilityError, FeedDepthExperiment

_SOURCE_ID = "yandex_public"
_METRIC_NORMALIZER_NAME = "YandexGameNormalizer"
_METRIC_NORMALIZER_VERSION = "2"
_HISTORY_NORMALIZER_NAME = "YandexListingHistoryNormalizer"
_HISTORY_NORMALIZER_VERSION = "1"
_SEARCH_REQUEST_KEY = "catalogue.search"
_SEARCH_PARSER_VERSION = "2"
_SEARCH_PAGE_LIMIT = 10
_MAX_CHECKPOINT_AGE_SECONDS = 2 * 60 * 60
_DAY_SECONDS = 24 * 60 * 60
_PAGINATION_KEYS = {"page_id", "rtx-reqid"}


class CadenceCheckpointInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    checkpoint_at: AwareDatetime
    feed_run_id: str
    search_run_ids: tuple[str, ...] = Field(min_length=1)

    @field_validator("feed_run_id")
    @classmethod
    def validate_feed_run_id(cls, value: str) -> str:
        return _require_exact_non_blank(value, "feed_run_id")

    @field_validator("search_run_ids")
    @classmethod
    def validate_search_run_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(_require_exact_non_blank(item, "search_run_id") for item in value)
        if len(normalized) != len(set(normalized)):
            raise ValueError("search run IDs must be unique within a checkpoint")
        return normalized


class CollectionCadenceManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: str = SPEC_VERSION
    listing_ids: tuple[str, ...] = Field(min_length=MIN_LISTING_SERIES)
    query_family_id: str
    query_family_version: int = Field(ge=1)
    checkpoints: tuple[CadenceCheckpointInput, ...] = Field(min_length=MIN_REFERENCE_DAYS)

    @field_validator("listing_ids")
    @classmethod
    def validate_listing_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(_listing_id(item) for item in value)
        if len(normalized) != len(set(normalized)):
            raise ValueError("cadence listing cohort must contain unique listing IDs")
        return normalized

    @field_validator("query_family_id")
    @classmethod
    def validate_family_id(cls, value: str) -> str:
        return _require_exact_non_blank(value, "query_family_id")

    @model_validator(mode="after")
    def validate_manifest(self) -> Self:
        if self.spec_version != SPEC_VERSION:
            raise ValueError(f"cadence manifest must use spec_version={SPEC_VERSION}")
        checkpoints = self.checkpoints
        utc_times = [item.checkpoint_at.astimezone(UTC) for item in checkpoints]
        if any(
            current <= previous
            for previous, current in zip(utc_times, utc_times[1:], strict=False)
        ):
            raise ValueError("cadence checkpoints must be strictly increasing")
        dates = [item.date() for item in utc_times]
        if len(dates) != len(set(dates)):
            raise ValueError("cadence manifest must contain one checkpoint per UTC date")
        for previous, current in zip(dates, dates[1:], strict=False):
            if (current - previous).days != 1:
                raise ValueError("cadence checkpoint UTC dates must be consecutive")
        clock_seconds = [
            item.hour * 3600 + item.minute * 60 + item.second
            for item in utc_times
        ]
        if _circular_clock_span_seconds(clock_seconds) > _MAX_CHECKPOINT_AGE_SECONDS:
            raise ValueError("cadence checkpoint UTC clock times must fit one two-hour band")

        feed_ids = [item.feed_run_id for item in checkpoints]
        search_ids = [run_id for item in checkpoints for run_id in item.search_run_ids]
        all_run_ids = feed_ids + search_ids
        if len(all_run_ids) != len(set(all_run_ids)):
            raise ValueError("cadence manifest cannot reuse a probe run across checkpoints")
        return self


class RejectedCadenceSeries(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    series_id: str
    reason: str


class CollectionCadenceExperimentReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: str = SPEC_VERSION
    analyzer_version: str = ANALYZER_VERSION
    listing_ids: tuple[str, ...]
    query_family_id: str
    query_family_version: int
    checkpoint_at: tuple[AwareDatetime, ...]
    eligible_state_series_ids: tuple[str, ...]
    eligible_ranking_series_ids: tuple[str, ...]
    rejected_series: tuple[RejectedCadenceSeries, ...]
    analysis: CollectionCadenceReport


class CollectionCadenceEvidenceError(ValueError):
    """Submitted cadence evidence cannot satisfy the frozen v1 cohort contract."""


class CollectionCadenceExperiment:
    """Build daily reference series from persisted evidence, then downsample them."""

    def __init__(
        self,
        *,
        raw_store: FilesystemRawSnapshotStore,
        database_path: Path,
    ) -> None:
        self.raw_store = raw_store
        self.metric_store = SQLiteMetricStore(database_path)
        self.history_store = SQLiteListingHistoryStore(database_path)
        self.lineage_store = SQLiteLineageStore(database_path)
        self.probe_store = SQLiteProbeRunStore(database_path)
        self.query_family_store = SQLiteQueryFamilyStore(database_path)
        self.feed_experiment = FeedDepthExperiment(
            raw_store=raw_store,
            probe_store=self.probe_store,
        )

    def analyze(
        self,
        manifest: CollectionCadenceManifest,
    ) -> CollectionCadenceExperimentReport:
        _validate_runtime_versions()
        family = self.query_family_store.get(
            manifest.query_family_id,
            manifest.query_family_version,
        )
        if family is None:
            raise CollectionCadenceEvidenceError(
                "cadence query-family version does not exist in operational storage"
            )
        _validate_query_family(family)
        for checkpoint in manifest.checkpoints:
            if len(checkpoint.search_run_ids) != len(family.members):
                raise CollectionCadenceEvidenceError(
                    "every cadence checkpoint requires exactly one search run per query-family member"
                )

        state_series, state_rejections = self._load_state_series(manifest)
        ranking_series: list[RankingSeriesObservation] = []
        ranking_rejections: list[RejectedCadenceSeries] = []

        try:
            ranking_series.extend(self._load_feed_series(manifest))
        except (CollectionCadenceEvidenceError, FeedDepthEligibilityError) as exc:
            ranking_rejections.extend(
                RejectedCadenceSeries(
                    series_id=f"ranking:feed:depth{depth}",
                    reason=str(exc),
                )
                for depth in RANKING_DEPTHS
            )

        try:
            ranking_series.extend(self._load_search_series(manifest, family))
        except CollectionCadenceEvidenceError as exc:
            ranking_rejections.extend(
                RejectedCadenceSeries(
                    series_id=f"ranking:search:{member.query_text}:depth{depth}",
                    reason=str(exc),
                )
                for member in family.members
                for depth in RANKING_DEPTHS
            )

        if not state_series and not ranking_series:
            raise CollectionCadenceEvidenceError(
                "cadence manifest produced no eligible state or ranking series"
            )
        analysis = evaluate_collection_cadence(
            state_series=state_series,
            ranking_series=ranking_series,
        )
        return CollectionCadenceExperimentReport(
            listing_ids=manifest.listing_ids,
            query_family_id=family.family_id,
            query_family_version=family.version,
            checkpoint_at=tuple(item.checkpoint_at for item in manifest.checkpoints),
            eligible_state_series_ids=tuple(item.series_id for item in state_series),
            eligible_ranking_series_ids=tuple(item.series_id for item in ranking_series),
            rejected_series=tuple((*state_rejections, *ranking_rejections)),
            analysis=analysis,
        )

    def _load_state_series(
        self,
        manifest: CollectionCadenceManifest,
    ) -> tuple[list[StateSeriesObservation], list[RejectedCadenceSeries]]:
        series: list[StateSeriesObservation] = []
        rejected: list[RejectedCadenceSeries] = []
        for listing_id in manifest.listing_ids:
            for metric_name, signal in (
                (
                    GameMetricName.YANDEX_GAMES_RATING,
                    CadenceStateSignal.YANDEX_GAMES_RATING,
                ),
                (GameMetricName.RATING_COUNT, CadenceStateSignal.RATING_COUNT),
            ):
                series_id = f"state:{listing_id}:{signal.value}"
                try:
                    points = self._metric_points(listing_id, metric_name, manifest)
                    series.append(
                        StateSeriesObservation(
                            series_id=series_id,
                            capability=CadenceCapability.CATALOGUE_METADATA,
                            signal=signal,
                            points=points,
                        )
                    )
                except CollectionCadenceEvidenceError as exc:
                    rejected.append(RejectedCadenceSeries(series_id=series_id, reason=str(exc)))

            media_series_id = f"state:{listing_id}:{CadenceStateSignal.MEDIA_MANIFEST.value}"
            try:
                media_points = self._media_points(listing_id, manifest)
                series.append(
                    StateSeriesObservation(
                        series_id=media_series_id,
                        capability=CadenceCapability.CATALOGUE_METADATA,
                        signal=CadenceStateSignal.MEDIA_MANIFEST,
                        points=media_points,
                    )
                )
            except CollectionCadenceEvidenceError as exc:
                rejected.append(
                    RejectedCadenceSeries(series_id=media_series_id, reason=str(exc))
                )

            update_series_id = f"state:{listing_id}:{CadenceStateSignal.GAME_PAGE_UPDATE.value}"
            try:
                update_points = self._update_points(listing_id, manifest)
                series.append(
                    StateSeriesObservation(
                        series_id=update_series_id,
                        capability=CadenceCapability.GAME_PAGE,
                        signal=CadenceStateSignal.GAME_PAGE_UPDATE,
                        points=update_points,
                    )
                )
            except CollectionCadenceEvidenceError as exc:
                rejected.append(
                    RejectedCadenceSeries(series_id=update_series_id, reason=str(exc))
                )
        return series, rejected

    def _metric_points(
        self,
        listing_id: str,
        metric_name: GameMetricName,
        manifest: CollectionCadenceManifest,
    ) -> tuple[StateReferencePoint, ...]:
        history = self.metric_store.metric_history(listing_id, metric_name)
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
        manifest: CollectionCadenceManifest,
    ) -> tuple[StateReferencePoint, ...]:
        history = self.history_store.media_history(listing_id)
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
        manifest: CollectionCadenceManifest,
    ) -> tuple[StateReferencePoint, ...]:
        history = self.history_store.update_history(listing_id)
        points: list[StateReferencePoint] = []
        for checkpoint in manifest.checkpoints:
            observation = _latest_update(history, checkpoint.checkpoint_at)
            if observation is None:
                raise CollectionCadenceEvidenceError(
                    f"{listing_id}/game-page update has no eligible observation for "
                    f"{_checkpoint_label(checkpoint.checkpoint_at)}"
                )
            self._validate_history_evidence(observation.observation_id, observation)
            value = json.dumps(
                {
                    "app_version": observation.observation.app_version,
                    "source_published_at": _optional_timestamp(
                        observation.observation.source_published_at
                    ),
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            points.append(
                StateReferencePoint(
                    reference_date=checkpoint.checkpoint_at.astimezone(UTC).date(),
                    value=value,
                )
            )
        return tuple(points)

    def _load_feed_series(
        self,
        manifest: CollectionCadenceManifest,
    ) -> tuple[RankingSeriesObservation, ...]:
        rankings: dict[int, list[RankingReferencePoint]] = {
            depth: [] for depth in RANKING_DEPTHS
        }
        for checkpoint in manifest.checkpoints:
            record = self.probe_store.get_run(checkpoint.feed_run_id)
            if record is None:
                raise CollectionCadenceEvidenceError(
                    f"feed probe run does not exist: {checkpoint.feed_run_id}"
                )
            if record.run.completed_at is None:
                raise CollectionCadenceEvidenceError(
                    f"feed run {record.run.id} is missing completed_at"
                )
            _validate_checkpoint_interval(
                record.run.started_at,
                record.run.completed_at,
                checkpoint.checkpoint_at,
                f"feed run {record.run.id}",
            )
            trial = self.feed_experiment.load_trial(checkpoint.feed_run_id)
            reference_date = checkpoint.checkpoint_at.astimezone(UTC).date()
            for depth in RANKING_DEPTHS:
                rankings[depth].append(
                    RankingReferencePoint(
                        reference_date=reference_date,
                        ranking=tuple(
                            f"yandex_games:{app_id}"
                            for app_id in trial.organic_rankings[depth]
                        ),
                    )
                )
        return tuple(
            RankingSeriesObservation(
                series_id=f"ranking:feed:depth{depth}",
                capability=CadenceCapability.RECOMMENDATION_FEED,
                depth=depth,
                points=tuple(rankings[depth]),
            )
            for depth in RANKING_DEPTHS
        )

    def _load_search_series(
        self,
        manifest: CollectionCadenceManifest,
        family: QueryFamilyVersion,
    ) -> tuple[RankingSeriesObservation, ...]:
        by_query: dict[str, dict[int, list[RankingReferencePoint]]] = {
            member.query_text: {depth: [] for depth in RANKING_DEPTHS}
            for member in family.members
        }
        for checkpoint in manifest.checkpoints:
            checkpoint_rankings = self._load_search_checkpoint(
                checkpoint,
                family,
            )
            reference_date = checkpoint.checkpoint_at.astimezone(UTC).date()
            for query_text, depth_rankings in checkpoint_rankings.items():
                for depth in RANKING_DEPTHS:
                    by_query[query_text][depth].append(
                        RankingReferencePoint(
                            reference_date=reference_date,
                            ranking=depth_rankings[depth],
                        )
                    )

        return tuple(
            RankingSeriesObservation(
                series_id=f"ranking:search:{query_ordinal}:depth{depth}",
                capability=CadenceCapability.SEARCH,
                depth=depth,
                query_text=member.query_text,
                points=tuple(by_query[member.query_text][depth]),
            )
            for query_ordinal, member in enumerate(family.members)
            for depth in RANKING_DEPTHS
        )

    def _load_search_checkpoint(
        self,
        checkpoint: CadenceCheckpointInput,
        family: QueryFamilyVersion,
    ) -> dict[str, dict[int, tuple[str, ...]]]:
        declared = {member.query_text for member in family.members}
        records: dict[str, ProbeRunRecord] = {}
        expected_context: ProbeContext | None = None
        for run_id in checkpoint.search_run_ids:
            record = self.probe_store.get_run(run_id)
            if record is None:
                raise CollectionCadenceEvidenceError(f"search probe run does not exist: {run_id}")
            run = record.run
            context = record.context
            if (
                run.source_id != _SOURCE_ID
                or run.request_key != _SEARCH_REQUEST_KEY
                or run.kind is not ProbeKind.SEARCH
            ):
                raise CollectionCadenceEvidenceError(
                    f"run {run.id} is not an eligible Yandex search probe"
                )
            if run.status is not ProbeRunStatus.COMPLETED or run.completed_at is None:
                raise CollectionCadenceEvidenceError(
                    f"search run {run.id} must be completed"
                )
            if run.requested_page_limit != _SEARCH_PAGE_LIMIT:
                raise CollectionCadenceEvidenceError(
                    f"search run {run.id} must request {_SEARCH_PAGE_LIMIT} pages"
                )
            query_text = run.query_text
            if query_text is None or query_text not in declared:
                raise CollectionCadenceEvidenceError(
                    f"search run {run.id} query is not in the frozen query family"
                )
            if query_text in records:
                raise CollectionCadenceEvidenceError(
                    f"multiple checkpoint runs use query_text={query_text!r}"
                )
            if context.language != family.language:
                raise CollectionCadenceEvidenceError(
                    f"search run {run.id} language does not match query family"
                )
            _validate_clean_context(context)
            _validate_checkpoint_interval(
                run.started_at,
                run.completed_at,
                checkpoint.checkpoint_at,
                f"search run {run.id}",
            )
            if expected_context is None:
                expected_context = context
            elif context != expected_context:
                raise CollectionCadenceEvidenceError(
                    "all search runs in one cadence checkpoint must share one exact ProbeContext"
                )
            _validate_completed_pages(record)
            records[query_text] = record

        missing = declared - set(records)
        if missing:
            raise CollectionCadenceEvidenceError(
                "cadence search checkpoint is missing query-family members: "
                + ", ".join(sorted(missing))
            )

        parser = YandexFeedParser()
        if parser.version != _SEARCH_PARSER_VERSION:
            raise CollectionCadenceEvidenceError(
                f"cadence search replay requires YandexFeedParser@{_SEARCH_PARSER_VERSION}"
            )

        result: dict[str, dict[int, tuple[str, ...]]] = {}
        for member in family.members:
            record = records[member.query_text]
            result[member.query_text] = self._replay_search_run(record, parser)
        return result

    def _replay_search_run(
        self,
        record: ProbeRunRecord,
        parser: YandexFeedParser,
    ) -> dict[int, tuple[str, ...]]:
        run = record.run
        ranked: list[str] = []
        seen: set[str] = set()
        rankings: dict[int, tuple[str, ...]] = {}
        for page in record.pages:
            try:
                metadata = self.raw_store.get_metadata(run.source_id, page.raw_snapshot_id)
                body = self.raw_store.get_body(run.source_id, page.raw_snapshot_id)
            except (OSError, ValueError) as exc:
                raise CollectionCadenceEvidenceError(
                    f"search raw replay failed for {run.id}[{page.page_index}]: {exc}"
                ) from exc
            if metadata.request_key != _SEARCH_REQUEST_KEY:
                raise CollectionCadenceEvidenceError(
                    f"search raw page for {run.id} has wrong request_key"
                )
            if not 200 <= metadata.http_status < 300:
                raise CollectionCadenceEvidenceError(
                    f"search raw page for {run.id} is not HTTP-successful"
                )
            _validate_search_request(
                metadata.request_context,
                record.context,
                run.query_text,
                page,
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
                raise CollectionCadenceEvidenceError(
                    f"search raw page for {run.id} cannot replay consistently: {exc}"
                ) from exc
            if replayed_page != page:
                raise CollectionCadenceEvidenceError(
                    f"replayed search page {run.id}[{page.page_index}] does not match storage"
                )
            for card in parsed.games:
                listing_id = f"yandex_games:{card.app_id}"
                if card.sponsored or listing_id in seen:
                    continue
                seen.add(listing_id)
                ranked.append(listing_id)
            depth = page.page_index + 1
            if depth in RANKING_DEPTHS:
                rankings[depth] = tuple(ranked)

        final = tuple(ranked)
        if not final:
            raise CollectionCadenceEvidenceError(
                f"search run {run.id} contains no organic result"
            )
        for depth in RANKING_DEPTHS:
            rankings.setdefault(depth, final)
        return rankings

    def _validate_metric_evidence(self, observation: PersistedMetricObservation) -> None:
        if (
            observation.evidence.source_id != _SOURCE_ID
            or observation.evidence.provenance is not Provenance.FIRST_PARTY
            or observation.evidence.measurement_kind is not MeasurementKind.OBSERVED
            or observation.normalizer_name != _METRIC_NORMALIZER_NAME
            or observation.normalizer_version != _METRIC_NORMALIZER_VERSION
        ):
            raise CollectionCadenceEvidenceError(
                f"metric observation {observation.observation_id} has incompatible provenance"
            )
        self._validate_raw_lineage(
            observation.observation_id,
            observation.normalizer_name,
            observation.normalizer_version,
            observation.evidence.retrieved_at,
        )

    def _validate_history_evidence(
        self,
        observation_id: str,
        observation: PersistedListingMedia | PersistedListingUpdate,
    ) -> None:
        if (
            observation.evidence.source_id != _SOURCE_ID
            or observation.evidence.provenance is not Provenance.FIRST_PARTY
            or observation.evidence.measurement_kind is not MeasurementKind.OBSERVED
            or observation.normalizer_name != _HISTORY_NORMALIZER_NAME
            or observation.normalizer_version != _HISTORY_NORMALIZER_VERSION
        ):
            raise CollectionCadenceEvidenceError(
                f"history observation {observation_id} has incompatible provenance"
            )
        self._validate_raw_lineage(
            observation_id,
            observation.normalizer_name,
            observation.normalizer_version,
            observation.evidence.retrieved_at,
        )

    def _validate_raw_lineage(
        self,
        observation_id: str,
        normalizer_name: str,
        normalizer_version: str,
        retrieved_at: datetime | None,
    ) -> None:
        if retrieved_at is None:
            raise CollectionCadenceEvidenceError(
                f"observation {observation_id} is missing retrieved_at"
            )
        lineage = self.lineage_store.for_observation(observation_id)
        if not lineage:
            raise CollectionCadenceEvidenceError(
                f"observation {observation_id} has no field lineage"
            )
        for item in lineage:
            if (
                item.transformation_version != normalizer_version
                or not item.transformation_name.startswith(f"{normalizer_name}.")
            ):
                raise CollectionCadenceEvidenceError(
                    f"observation {observation_id} lineage disagrees with normalizer metadata"
                )
            try:
                metadata = self.raw_store.get_metadata(_SOURCE_ID, item.raw_snapshot_id)
                self.raw_store.get_body(_SOURCE_ID, item.raw_snapshot_id)
            except (OSError, ValueError) as exc:
                raise CollectionCadenceEvidenceError(
                    f"observation {observation_id} raw lineage replay failed: {exc}"
                ) from exc
            if metadata.retrieved_at != retrieved_at:
                raise CollectionCadenceEvidenceError(
                    f"observation {observation_id} retrieved_at differs from raw snapshot"
                )


def _latest_metric(
    history: Sequence[PersistedMetricObservation],
    checkpoint_at: datetime,
) -> PersistedMetricObservation | None:
    eligible = [
        item
        for item in history
        if _is_checkpoint_fresh(
            item.metric.observed_at,
            item.evidence.retrieved_at,
            checkpoint_at,
        )
    ]
    return max(
        eligible,
        key=lambda item: (
            item.metric.observed_at,
            item.evidence.retrieved_at or item.metric.observed_at,
            item.observation_id,
        ),
        default=None,
    )


def _latest_media(
    history: Sequence[PersistedListingMedia],
    checkpoint_at: datetime,
) -> PersistedListingMedia | None:
    eligible = [
        item
        for item in history
        if _is_checkpoint_fresh(
            item.observation.observed_at,
            item.evidence.retrieved_at,
            checkpoint_at,
        )
    ]
    return max(
        eligible,
        key=lambda item: (
            item.observation.observed_at,
            item.evidence.retrieved_at or item.observation.observed_at,
            item.observation_id,
        ),
        default=None,
    )


def _latest_update(
    history: Sequence[PersistedListingUpdate],
    checkpoint_at: datetime,
) -> PersistedListingUpdate | None:
    eligible = [
        item
        for item in history
        if _is_checkpoint_fresh(
            item.observation.observed_at,
            item.evidence.retrieved_at,
            checkpoint_at,
        )
    ]
    return max(
        eligible,
        key=lambda item: (
            item.observation.observed_at,
            item.evidence.retrieved_at or item.observation.observed_at,
            item.observation_id,
        ),
        default=None,
    )


def _is_checkpoint_fresh(
    observed_at: datetime,
    retrieved_at: datetime | None,
    checkpoint_at: datetime,
) -> bool:
    if retrieved_at is None:
        return False
    checkpoint_utc = checkpoint_at.astimezone(UTC)
    observed_utc = observed_at.astimezone(UTC)
    retrieved_utc = retrieved_at.astimezone(UTC)
    if retrieved_utc > checkpoint_utc:
        return False
    age_seconds = (checkpoint_utc - observed_utc).total_seconds()
    return 0.0 <= age_seconds <= _MAX_CHECKPOINT_AGE_SECONDS


def _validate_checkpoint_interval(
    started_at: datetime,
    completed_at: datetime,
    checkpoint_at: datetime,
    label: str,
) -> None:
    checkpoint_utc = checkpoint_at.astimezone(UTC)
    if completed_at.astimezone(UTC) > checkpoint_utc:
        raise CollectionCadenceEvidenceError(
            f"{label} completed after its cadence checkpoint"
        )
    if not _is_checkpoint_fresh(started_at, started_at, checkpoint_at):
        raise CollectionCadenceEvidenceError(
            f"{label} did not start within two hours before its cadence checkpoint"
        )


def _validate_query_family(family: QueryFamilyVersion) -> None:
    if family.source_id != _SOURCE_ID:
        raise CollectionCadenceEvidenceError(
            f"cadence query family must use source_id={_SOURCE_ID}"
        )


def _validate_runtime_versions() -> None:
    if YandexGameNormalizer.version != _METRIC_NORMALIZER_VERSION:
        raise CollectionCadenceEvidenceError(
            "collection-cadence-v1 metric normalizer version no longer matches runtime"
        )
    if YandexListingHistoryNormalizer.version != _HISTORY_NORMALIZER_VERSION:
        raise CollectionCadenceEvidenceError(
            "collection-cadence-v1 history normalizer version no longer matches runtime"
        )
    if YandexFeedParser.version != _SEARCH_PARSER_VERSION:
        raise CollectionCadenceEvidenceError(
            "collection-cadence-v1 search parser version no longer matches runtime"
        )


def _validate_clean_context(context: ProbeContext) -> None:
    if (
        context.session_profile is not SessionProfile.CLEAN_ANONYMOUS
        or context.session_instance_id is not None
        or context.cookie_state_hash is not None
        or context.profile_age_days != 0
        or context.country_observed is not None
        or context.collector_region is not None
        or context.device_type != "desktop"
        or context.platform != "desktop_other"
    ):
        raise CollectionCadenceEvidenceError(
            "cadence search requires clean anonymous desktop/desktop_other context with null region"
        )


def _validate_completed_pages(record: ProbeRunRecord) -> None:
    run = record.run
    page_count = len(record.pages)
    if not 1 <= page_count <= run.requested_page_limit:
        raise CollectionCadenceEvidenceError(
            f"search run {run.id} has invalid persisted page count"
        )
    if tuple(page.page_index for page in record.pages) != tuple(range(page_count)):
        raise CollectionCadenceEvidenceError(
            f"search run {run.id} pages are not contiguous from zero"
        )
    if page_count < run.requested_page_limit and record.pages[-1].has_next_page:
        raise CollectionCadenceEvidenceError(
            f"search run {run.id} stopped before limit without source exhaustion"
        )


def _validate_search_request(
    request_context: Mapping[str, object],
    context: ProbeContext,
    query_text: str | None,
    page: ProbePage,
) -> None:
    if query_text is None:
        raise CollectionCadenceEvidenceError("search run unexpectedly lacks query_text")
    if set(request_context) != {"probe_context", "query", "params"}:
        raise CollectionCadenceEvidenceError(
            "cadence search raw request has undeclared top-level fields"
        )
    if request_context.get("probe_context") != context.model_dump(mode="json"):
        raise CollectionCadenceEvidenceError(
            "cadence search raw probe_context disagrees with stored ProbeContext"
        )
    if request_context.get("query") != query_text:
        raise CollectionCadenceEvidenceError(
            "cadence search raw query disagrees with stored run query_text"
        )
    params = request_context.get("params")
    if not isinstance(params, Mapping):
        raise CollectionCadenceEvidenceError("cadence search raw request is missing params")
    expected_keys = {"query", "lang"}
    if page.page_index > 0:
        expected_keys |= _PAGINATION_KEYS
    if set(params) != expected_keys:
        raise CollectionCadenceEvidenceError(
            "cadence search raw params do not match frozen request shape"
        )
    if params.get("query") != query_text or params.get("lang") != context.language:
        raise CollectionCadenceEvidenceError(
            "cadence search raw query/lang disagree with persisted run"
        )
    expected_page_id = None if page.page_index == 0 else page.request_page_id
    expected_rtx = None if page.page_index == 0 else page.request_rtx_reqid
    if _optional_token(params.get("page_id")) != expected_page_id:
        raise CollectionCadenceEvidenceError(
            "cadence search raw page_id disagrees with stored page linkage"
        )
    if _optional_token(params.get("rtx-reqid")) != expected_rtx:
        raise CollectionCadenceEvidenceError(
            "cadence search raw rtx-reqid disagrees with stored page linkage"
        )


def _optional_token(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise CollectionCadenceEvidenceError("search pagination token must be a string")
    stripped = value.strip()
    return stripped or None


def _canonical_numeric(value: int | float) -> str:
    numeric = float(value)
    if not isfinite(numeric):
        raise CollectionCadenceEvidenceError("cadence metric value must be finite")
    return json.dumps(numeric, allow_nan=False, separators=(",", ":"))


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
