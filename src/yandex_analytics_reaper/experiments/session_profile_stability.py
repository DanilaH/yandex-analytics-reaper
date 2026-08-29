from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC
from enum import StrEnum
from math import floor
from statistics import median
from typing import Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, model_validator

from yandex_analytics_reaper.domain import (
    ProbeKind,
    ProbePage,
    ProbeRunStatus,
    SessionProfile,
)
from yandex_analytics_reaper.sources.yandex.parsers import YandexFeedParser
from yandex_analytics_reaper.sources.yandex.probes import probe_page_from_yandex
from yandex_analytics_reaper.storage import FilesystemRawSnapshotStore, SQLiteProbeRunStore

SPEC_VERSION = "session-profile-stability-v1"
ANALYZER_VERSION = "1"
PARSER_VERSION = "2"
SOURCE_ID = "yandex_public"
REQUEST_KEY = "catalogue.feed"
CANDIDATE_DEPTHS = (1, 3, 5, 10)
PAGE_SIZE = 20
MAX_BLOCK_SPAN_MINUTES = 10.0
MIN_ELIGIBLE_BLOCKS = 6
MIN_SAMPLE_SPAN_HOURS = 4.0
MIN_DISTINCT_HOUR_BUCKETS = 3
MIN_BLOCKS_PER_ORDER = 2
MIN_BASELINE_SIMILARITY = 0.50
MEDIAN_PROFILE_GAP_MAX = 0.10
P75_PROFILE_GAP_MAX = 0.15
RANK_PERSISTENCE = 0.90
_STABLE_FEED_PARAMS: dict[str, object] = {
    "games_count": PAGE_SIZE,
    "with_promos": "false",
    "lang": "ru",
    "device-type": "desktop",
    "platform": "desktop_other",
}
_PAGINATION_PARAM_KEYS = {"page_id", "rtx-reqid"}


class SessionProfileBlockOrder(StrEnum):
    CLEAN_OUTER = "C-P-P-C"
    PERSISTENT_OUTER = "P-C-C-P"


class SessionProfileDepthClassification(StrEnum):
    STABLE = "stable"
    MATERIAL_DIFFERENCE = "material_difference"
    INCONCLUSIVE = "inconclusive"


class SessionProfileRunObservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    started_at: AwareDatetime
    session_profile: SessionProfile
    session_instance_id: str | None
    organic_rankings: dict[int, tuple[int, ...]]

    @model_validator(mode="after")
    def validate_run_observation(self) -> Self:
        if self.session_profile is SessionProfile.CLEAN_ANONYMOUS:
            if self.session_instance_id is not None:
                raise ValueError("clean session-profile observation cannot carry session_instance_id")
        elif self.session_profile is SessionProfile.PERSISTENT_ANONYMOUS:
            if not _is_session_instance_id(self.session_instance_id):
                raise ValueError(
                    "persistent session-profile observation requires a valid session_instance_id"
                )
        else:
            raise ValueError("session-profile trial supports only clean/persistent anonymous")

        if set(self.organic_rankings) != set(CANDIDATE_DEPTHS):
            raise ValueError("session-profile run must contain rankings for 1/3/5/10 pages")
        full = self.organic_rankings[10]
        if not full:
            raise ValueError("session-profile run requires at least one organic game")
        for depth in CANDIDATE_DEPTHS:
            ranked = self.organic_rankings[depth]
            if len(ranked) != len(set(ranked)):
                raise ValueError("organic feed rankings must contain unique app IDs")
            if tuple(full[: len(ranked)]) != ranked:
                raise ValueError("shallower session-profile rankings must be prefixes of depth 10")
        return self


class SessionProfileBlockObservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_ids: tuple[str, str, str, str]
    started_at: AwareDatetime
    order: SessionProfileBlockOrder
    persistent_session_instance_id: str
    clean_runs: tuple[SessionProfileRunObservation, SessionProfileRunObservation]
    persistent_runs: tuple[SessionProfileRunObservation, SessionProfileRunObservation]

    @model_validator(mode="after")
    def validate_block_observation(self) -> Self:
        if not _is_session_instance_id(self.persistent_session_instance_id):
            raise ValueError("session-profile block requires a valid persistent session instance")

        clean = self.clean_runs
        persistent = self.persistent_runs
        if any(run.session_profile is not SessionProfile.CLEAN_ANONYMOUS for run in clean):
            raise ValueError("clean_runs must contain only clean_anonymous observations")
        if any(
            run.session_profile is not SessionProfile.PERSISTENT_ANONYMOUS
            for run in persistent
        ):
            raise ValueError(
                "persistent_runs must contain only persistent_anonymous observations"
            )
        if any(
            run.session_instance_id != self.persistent_session_instance_id
            for run in persistent
        ):
            raise ValueError(
                "persistent_runs must share the block persistent_session_instance_id"
            )

        all_runs = (clean[0], clean[1], persistent[0], persistent[1])
        if len({run.run_id for run in all_runs}) != 4:
            raise ValueError("session-profile block observations must have unique run IDs")
        starts = [run.started_at.astimezone(UTC) for run in all_runs]
        if len(set(starts)) != 4:
            raise ValueError("session-profile block run starts must be distinct")
        span_minutes = (max(starts) - min(starts)).total_seconds() / 60.0
        if span_minutes > MAX_BLOCK_SPAN_MINUTES:
            raise ValueError(
                f"session-profile block span={span_minutes:.2f}m exceeds "
                f"{MAX_BLOCK_SPAN_MINUTES:.2f}m"
            )

        chronological = tuple(sorted(all_runs, key=lambda run: run.started_at))
        chronological_ids = (
            chronological[0].run_id,
            chronological[1].run_id,
            chronological[2].run_id,
            chronological[3].run_id,
        )
        if self.run_ids != chronological_ids:
            raise ValueError("session-profile block run_ids must be chronological")
        if self.started_at != chronological[0].started_at:
            raise ValueError("session-profile block started_at must equal its earliest run start")

        profile_sequence = tuple(run.session_profile for run in chronological)
        expected_order = _block_order(profile_sequence)
        if self.order is not expected_order:
            raise ValueError("session-profile block order does not match chronological profiles")
        return self


class RejectedSessionProfileBlock(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_ids: tuple[str, str, str, str]
    reason: str


class SessionProfileDepthMetrics(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    depth: int
    median_within_baseline_jaccard: float | None
    median_cross_profile_jaccard: float | None
    median_jaccard_profile_gap: float | None
    p75_jaccard_profile_gap: float | None
    median_within_baseline_ranked_overlap: float | None
    median_cross_profile_ranked_overlap: float | None
    median_ranked_overlap_profile_gap: float | None
    p75_ranked_overlap_profile_gap: float | None
    median_clean_unique_games: float | None
    median_persistent_unique_games: float | None
    classification: SessionProfileDepthClassification | None
    classification_reasons: tuple[str, ...]


class SessionProfileDecisionPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    minimum_eligible_blocks: int = MIN_ELIGIBLE_BLOCKS
    minimum_sample_span_hours: float = MIN_SAMPLE_SPAN_HOURS
    minimum_distinct_hour_buckets: int = MIN_DISTINCT_HOUR_BUCKETS
    minimum_blocks_per_order: int = MIN_BLOCKS_PER_ORDER
    maximum_block_span_minutes: float = MAX_BLOCK_SPAN_MINUTES
    minimum_baseline_similarity: float = MIN_BASELINE_SIMILARITY
    median_profile_gap_max: float = MEDIAN_PROFILE_GAP_MAX
    p75_profile_gap_max: float = P75_PROFILE_GAP_MAX
    rank_persistence: float = RANK_PERSISTENCE


class SessionProfileStabilityReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: str = SPEC_VERSION
    analyzer_version: str = ANALYZER_VERSION
    parser_version: str = PARSER_VERSION
    candidate_depths: tuple[int, ...] = CANDIDATE_DEPTHS
    page_size: int = PAGE_SIZE
    submitted_blocks: tuple[tuple[str, str, str, str], ...]
    eligible_blocks: tuple[tuple[str, str, str, str], ...]
    rejected_blocks: tuple[RejectedSessionProfileBlock, ...]
    persistent_session_instance_id: str | None
    eligible_block_count: int
    sample_span_hours: float
    hour_buckets_utc: tuple[str, ...]
    clean_outer_block_count: int
    persistent_outer_block_count: int
    sample_sufficient: bool
    decision_policy: SessionProfileDecisionPolicy
    metrics: tuple[SessionProfileDepthMetrics, ...]
    decision_reasons: tuple[str, ...]


class SessionProfileEligibilityError(ValueError):
    """A submitted run/block cannot be used by session-profile-stability-v1."""


class SessionProfileCohortError(ValueError):
    """Submitted individually valid blocks mix persistent profile instances."""


class SessionProfileStabilityExperiment:
    """Replay explicit matched feed blocks and evaluate frozen profile-effect tolerances."""

    def __init__(
        self,
        *,
        raw_store: FilesystemRawSnapshotStore,
        probe_store: SQLiteProbeRunStore,
    ) -> None:
        self.raw_store = raw_store
        self.probe_store = probe_store

    def load_run(self, run_id: str) -> SessionProfileRunObservation:
        record = self.probe_store.get_run(run_id)
        if record is None:
            raise SessionProfileEligibilityError(f"probe run does not exist: {run_id}")

        run = record.run
        context = record.context
        if run.source_id != SOURCE_ID:
            raise SessionProfileEligibilityError(
                f"session-profile-v1 requires source_id={SOURCE_ID}"
            )
        if run.request_key != REQUEST_KEY or run.kind is not ProbeKind.RECOMMENDATION_FEED:
            raise SessionProfileEligibilityError(
                "session-profile-v1 requires recommendation-feed catalogue.feed runs"
            )
        if run.status is not ProbeRunStatus.COMPLETED:
            raise SessionProfileEligibilityError("session-profile run must have completed status")
        if run.requested_page_limit != 10:
            raise SessionProfileEligibilityError(
                "session-profile run must request exactly 10 pages"
            )

        pages = record.pages
        page_count = len(pages)
        if not 1 <= page_count <= 10:
            raise SessionProfileEligibilityError(
                "session-profile run must contain between 1 and 10 pages"
            )
        if tuple(page.page_index for page in pages) != tuple(range(page_count)):
            raise SessionProfileEligibilityError(
                "session-profile run must contain a contiguous page prefix from 0"
            )
        if page_count < 10 and pages[-1].has_next_page:
            raise SessionProfileEligibilityError(
                "session-profile run stopped before page 10 without source exhaustion"
            )

        if context.language != "ru":
            raise SessionProfileEligibilityError("session-profile-v1 requires language=ru")
        if context.device_type != "desktop":
            raise SessionProfileEligibilityError("session-profile-v1 requires device_type=desktop")
        if context.platform != "desktop_other":
            raise SessionProfileEligibilityError("session-profile-v1 requires platform=desktop_other")
        if context.country_observed is not None:
            raise SessionProfileEligibilityError("session-profile-v1 requires country_observed=null")
        if context.collector_region is not None:
            raise SessionProfileEligibilityError("session-profile-v1 requires collector_region=null")

        if context.session_profile is SessionProfile.CLEAN_ANONYMOUS:
            if (
                context.session_instance_id is not None
                or context.cookie_state_hash is not None
                or context.profile_age_days != 0
            ):
                raise SessionProfileEligibilityError(
                    "clean session-profile run lacks fresh clean-anonymous provenance"
                )
        elif context.session_profile is SessionProfile.PERSISTENT_ANONYMOUS:
            fingerprint = context.cookie_state_hash
            if (
                not _is_session_instance_id(context.session_instance_id)
                or fingerprint is None
                or len(fingerprint) != 64
                or any(character not in "0123456789abcdef" for character in fingerprint)
                or context.profile_age_days is None
            ):
                raise SessionProfileEligibilityError(
                    "persistent session-profile run lacks effective persistent provenance"
                )
        else:
            raise SessionProfileEligibilityError(
                "session-profile-v1 supports only clean/persistent anonymous runs"
            )

        parser = YandexFeedParser()
        if parser.version != PARSER_VERSION:
            raise SessionProfileEligibilityError(
                f"session-profile-v1 requires YandexFeedParser@{PARSER_VERSION}; "
                f"current parser is @{parser.version}"
            )

        ranked: list[int] = []
        seen: set[int] = set()
        rankings: dict[int, tuple[int, ...]] = {}
        for page in pages:
            try:
                metadata = self.raw_store.get_metadata(run.source_id, page.raw_snapshot_id)
                body = self.raw_store.get_body(run.source_id, page.raw_snapshot_id)
            except (OSError, ValueError) as exc:
                raise SessionProfileEligibilityError(
                    f"raw replay failed for probe page {page.page_index}: {exc}"
                ) from exc

            if metadata.request_key != REQUEST_KEY:
                raise SessionProfileEligibilityError(
                    f"session-profile raw page must use request_key={REQUEST_KEY}"
                )
            if not 200 <= metadata.http_status < 300:
                raise SessionProfileEligibilityError(
                    "session-profile raw page does not have a successful HTTP status"
                )
            _validate_feed_request(metadata.request_context, page)

            try:
                parsed = parser.parse(body)
                replayed_page = probe_page_from_yandex(
                    run=run,
                    context=context,
                    metadata=metadata,
                    page_index=page.page_index,
                    page_info=parsed.page_info,
                )
            except ValueError as exc:
                raise SessionProfileEligibilityError(
                    f"session-profile raw page cannot be replayed consistently: {exc}"
                ) from exc
            if replayed_page != page:
                raise SessionProfileEligibilityError(
                    f"replayed probe page {page.page_index} does not match stored page linkage"
                )

            for game in parsed.games:
                if game.sponsored or game.app_id in seen:
                    continue
                seen.add(game.app_id)
                ranked.append(game.app_id)

            depth = page.page_index + 1
            if depth in CANDIDATE_DEPTHS:
                rankings[depth] = tuple(ranked)

        final_ranking = tuple(ranked)
        if not final_ranking:
            raise SessionProfileEligibilityError(
                "session-profile run requires at least one organic game"
            )
        for depth in CANDIDATE_DEPTHS:
            if depth not in rankings:
                rankings[depth] = final_ranking

        return SessionProfileRunObservation(
            run_id=run.id,
            started_at=run.started_at,
            session_profile=context.session_profile,
            session_instance_id=context.session_instance_id,
            organic_rankings=rankings,
        )

    def load_block(self, run_ids: Sequence[str]) -> SessionProfileBlockObservation:
        normalized = tuple(run_id.strip() for run_id in run_ids)
        if len(normalized) != 4:
            raise SessionProfileEligibilityError(
                "session-profile block requires exactly four run IDs"
            )
        if any(not run_id for run_id in normalized):
            raise SessionProfileEligibilityError("session-profile block run IDs cannot be blank")
        if len(set(normalized)) != 4:
            raise SessionProfileEligibilityError("session-profile block run IDs must be unique")

        runs = [self.load_run(run_id) for run_id in normalized]
        starts = [run.started_at.astimezone(UTC) for run in runs]
        if len(set(starts)) != 4:
            raise SessionProfileEligibilityError(
                "session-profile block run starts must be distinct for chronological ordering"
            )
        span_minutes = (max(starts) - min(starts)).total_seconds() / 60.0
        if span_minutes > MAX_BLOCK_SPAN_MINUTES:
            raise SessionProfileEligibilityError(
                f"session-profile block span={span_minutes:.2f}m exceeds "
                f"{MAX_BLOCK_SPAN_MINUTES:.2f}m"
            )

        chronological = tuple(sorted(runs, key=lambda run: run.started_at))
        clean = tuple(
            run
            for run in chronological
            if run.session_profile is SessionProfile.CLEAN_ANONYMOUS
        )
        persistent = tuple(
            run
            for run in chronological
            if run.session_profile is SessionProfile.PERSISTENT_ANONYMOUS
        )
        if len(clean) != 2 or len(persistent) != 2:
            raise SessionProfileEligibilityError(
                "session-profile block requires exactly two clean and two persistent runs"
            )

        profile_sequence = tuple(run.session_profile for run in chronological)
        try:
            order = _block_order(profile_sequence)
        except ValueError as exc:
            raise SessionProfileEligibilityError(str(exc)) from exc

        persistent_ids = {run.session_instance_id for run in persistent}
        if None in persistent_ids or len(persistent_ids) != 1:
            raise SessionProfileEligibilityError(
                "both persistent runs in a block must share one session_instance_id"
            )
        persistent_id = next(iter(persistent_ids))
        if persistent_id is None:
            raise RuntimeError("validated persistent session instance ID disappeared")

        run_ids_chronological = (
            chronological[0].run_id,
            chronological[1].run_id,
            chronological[2].run_id,
            chronological[3].run_id,
        )
        return SessionProfileBlockObservation(
            run_ids=run_ids_chronological,
            started_at=chronological[0].started_at,
            order=order,
            persistent_session_instance_id=persistent_id,
            clean_runs=(clean[0], clean[1]),
            persistent_runs=(persistent[0], persistent[1]),
        )

    def analyze(self, blocks: Sequence[Sequence[str]]) -> SessionProfileStabilityReport:
        submitted: list[tuple[str, str, str, str]] = []
        all_run_ids: list[str] = []
        for raw_block in blocks:
            normalized = tuple(run_id.strip() for run_id in raw_block)
            if len(normalized) != 4:
                raise ValueError("every submitted session-profile block must contain four run IDs")
            if any(not run_id for run_id in normalized):
                raise ValueError("submitted session-profile run IDs cannot be blank")
            block = (normalized[0], normalized[1], normalized[2], normalized[3])
            submitted.append(block)
            all_run_ids.extend(block)
        if len(set(all_run_ids)) != len(all_run_ids):
            raise ValueError("session-profile run IDs cannot be reused across submitted blocks")

        eligible: list[SessionProfileBlockObservation] = []
        rejected: list[RejectedSessionProfileBlock] = []
        for block in submitted:
            try:
                eligible.append(self.load_block(block))
            except SessionProfileEligibilityError as exc:
                rejected.append(RejectedSessionProfileBlock(run_ids=block, reason=str(exc)))

        persistent_ids = {block.persistent_session_instance_id for block in eligible}
        if len(persistent_ids) > 1:
            raise SessionProfileCohortError(
                "eligible session-profile blocks span multiple persistent session instances"
            )

        return evaluate_session_profile_blocks(
            eligible,
            submitted_blocks=tuple(submitted),
            rejected_blocks=tuple(rejected),
        )


def evaluate_session_profile_blocks(
    blocks: Sequence[SessionProfileBlockObservation],
    *,
    submitted_blocks: Sequence[tuple[str, str, str, str]] | None = None,
    rejected_blocks: Sequence[RejectedSessionProfileBlock] = (),
) -> SessionProfileStabilityReport:
    eligible = tuple(blocks)
    rejected = tuple(rejected_blocks)
    eligible_run_sets = {frozenset(block.run_ids) for block in eligible}
    rejected_run_sets = {frozenset(block.run_ids) for block in rejected}
    if len(eligible_run_sets) != len(eligible):
        raise ValueError("eligible session-profile blocks must be unique")
    if len(rejected_run_sets) != len(rejected):
        raise ValueError("rejected session-profile blocks must be unique")
    if eligible_run_sets & rejected_run_sets:
        raise ValueError("session-profile block cannot be both eligible and rejected")

    evidence_run_ids = [
        run_id
        for block in eligible
        for run_id in block.run_ids
    ] + [
        run_id
        for block in rejected
        for run_id in block.run_ids
    ]
    if len(set(evidence_run_ids)) != len(evidence_run_ids):
        raise ValueError("session-profile run IDs cannot be reused across blocks")

    persistent_ids = {block.persistent_session_instance_id for block in eligible}
    if len(persistent_ids) > 1:
        raise SessionProfileCohortError(
            "eligible session-profile blocks span multiple persistent session instances"
        )
    persistent_id = next(iter(persistent_ids)) if persistent_ids else None

    if submitted_blocks is None:
        if rejected:
            raise ValueError("rejected session-profile blocks require explicit submitted_blocks")
        submitted = tuple(block.run_ids for block in eligible)
    else:
        submitted = tuple(submitted_blocks)
        submitted_run_ids: list[str] = []
        for block in submitted:
            if len(block) != 4 or any(not run_id.strip() for run_id in block):
                raise ValueError(
                    "every submitted session-profile block must contain four non-blank run IDs"
                )
            submitted_run_ids.extend(block)
        if len(set(submitted_run_ids)) != len(submitted_run_ids):
            raise ValueError("submitted session-profile run IDs cannot be reused across blocks")
        submitted_sets = {frozenset(block) for block in submitted}
        if len(submitted_sets) != len(submitted):
            raise ValueError("submitted session-profile blocks must be unique")
        if submitted_sets != eligible_run_sets | rejected_run_sets:
            raise ValueError(
                "submitted session-profile blocks must exactly match eligible and rejected blocks"
            )

    span_hours = _sample_span_hours(eligible)
    hour_buckets = _hour_buckets_utc(eligible)
    clean_outer_count = sum(
        block.order is SessionProfileBlockOrder.CLEAN_OUTER for block in eligible
    )
    persistent_outer_count = sum(
        block.order is SessionProfileBlockOrder.PERSISTENT_OUTER for block in eligible
    )
    sufficiency_reasons = _sufficiency_reasons(
        eligible,
        span_hours,
        len(hour_buckets),
        clean_outer_count,
        persistent_outer_count,
    )
    sample_sufficient = not sufficiency_reasons
    metrics = tuple(
        _metrics_for_depth(eligible, depth, sample_sufficient=sample_sufficient)
        for depth in CANDIDATE_DEPTHS
    )

    return SessionProfileStabilityReport(
        submitted_blocks=submitted,
        eligible_blocks=tuple(block.run_ids for block in eligible),
        rejected_blocks=rejected,
        persistent_session_instance_id=persistent_id,
        eligible_block_count=len(eligible),
        sample_span_hours=span_hours,
        hour_buckets_utc=hour_buckets,
        clean_outer_block_count=clean_outer_count,
        persistent_outer_block_count=persistent_outer_count,
        sample_sufficient=sample_sufficient,
        decision_policy=SessionProfileDecisionPolicy(),
        metrics=metrics,
        decision_reasons=tuple(sufficiency_reasons),
    )


def _validate_feed_request(request_context: Mapping[str, object], page: ProbePage) -> None:
    if set(request_context) != {"probe_context", "params"}:
        raise SessionProfileEligibilityError(
            "session-profile-v1 raw request context contains undeclared top-level fields"
        )
    params = request_context.get("params")
    if not isinstance(params, Mapping):
        raise SessionProfileEligibilityError(
            "session-profile-v1 raw request is missing params metadata"
        )

    expected_keys = set(_STABLE_FEED_PARAMS)
    if page.page_index > 0:
        expected_keys |= _PAGINATION_PARAM_KEYS
    if set(params) != expected_keys:
        raise SessionProfileEligibilityError(
            "session-profile-v1 raw feed params do not match the frozen request shape"
        )
    for key, expected_value in _STABLE_FEED_PARAMS.items():
        if params.get(key) != expected_value:
            raise SessionProfileEligibilityError(
                f"session-profile-v1 raw feed param {key} does not match frozen value"
            )
    expected_page_id = None if page.page_index == 0 else page.request_page_id
    expected_rtx = None if page.page_index == 0 else page.request_rtx_reqid
    if _optional_token(params.get("page_id")) != expected_page_id:
        raise SessionProfileEligibilityError(
            "session-profile-v1 raw page_id does not match stored page linkage"
        )
    if _optional_token(params.get("rtx-reqid")) != expected_rtx:
        raise SessionProfileEligibilityError(
            "session-profile-v1 raw rtx-reqid does not match stored page linkage"
        )


def _metrics_for_depth(
    blocks: Sequence[SessionProfileBlockObservation],
    depth: int,
    *,
    sample_sufficient: bool,
) -> SessionProfileDepthMetrics:
    if not blocks:
        return SessionProfileDepthMetrics(
            depth=depth,
            median_within_baseline_jaccard=None,
            median_cross_profile_jaccard=None,
            median_jaccard_profile_gap=None,
            p75_jaccard_profile_gap=None,
            median_within_baseline_ranked_overlap=None,
            median_cross_profile_ranked_overlap=None,
            median_ranked_overlap_profile_gap=None,
            p75_ranked_overlap_profile_gap=None,
            median_clean_unique_games=None,
            median_persistent_unique_games=None,
            classification=None,
            classification_reasons=(),
        )

    baseline_jaccards: list[float] = []
    cross_jaccards: list[float] = []
    jaccard_gaps: list[float] = []
    baseline_ranked: list[float] = []
    cross_ranked: list[float] = []
    ranked_gaps: list[float] = []
    clean_counts: list[int] = []
    persistent_counts: list[int] = []

    for block in blocks:
        clean_rankings = [run.organic_rankings[depth] for run in block.clean_runs]
        persistent_rankings = [
            run.organic_rankings[depth] for run in block.persistent_runs
        ]
        clean_counts.extend(len(ranking) for ranking in clean_rankings)
        persistent_counts.extend(len(ranking) for ranking in persistent_rankings)

        within_clean_jaccard = _jaccard(clean_rankings[0], clean_rankings[1])
        within_persistent_jaccard = _jaccard(
            persistent_rankings[0], persistent_rankings[1]
        )
        baseline_jaccard = min(within_clean_jaccard, within_persistent_jaccard)
        cross_jaccard = float(
            median(
                _jaccard(clean_ranking, persistent_ranking)
                for clean_ranking in clean_rankings
                for persistent_ranking in persistent_rankings
            )
        )
        baseline_jaccards.append(baseline_jaccard)
        cross_jaccards.append(cross_jaccard)
        jaccard_gaps.append(max(0.0, baseline_jaccard - cross_jaccard))

        within_clean_ranked = _ranked_prefix_overlap(
            clean_rankings[0], clean_rankings[1], persistence=RANK_PERSISTENCE
        )
        within_persistent_ranked = _ranked_prefix_overlap(
            persistent_rankings[0],
            persistent_rankings[1],
            persistence=RANK_PERSISTENCE,
        )
        baseline_rank = min(within_clean_ranked, within_persistent_ranked)
        cross_rank = float(
            median(
                _ranked_prefix_overlap(
                    clean_ranking,
                    persistent_ranking,
                    persistence=RANK_PERSISTENCE,
                )
                for clean_ranking in clean_rankings
                for persistent_ranking in persistent_rankings
            )
        )
        baseline_ranked.append(baseline_rank)
        cross_ranked.append(cross_rank)
        ranked_gaps.append(max(0.0, baseline_rank - cross_rank))

    median_baseline_jaccard = float(median(baseline_jaccards))
    median_cross_jaccard = float(median(cross_jaccards))
    median_jaccard_gap = float(median(jaccard_gaps))
    p75_jaccard_gap = _required_percentile(jaccard_gaps, 0.75)
    median_baseline_ranked = float(median(baseline_ranked))
    median_cross_ranked = float(median(cross_ranked))
    median_ranked_gap = float(median(ranked_gaps))
    p75_ranked_gap = _required_percentile(ranked_gaps, 0.75)

    if not sample_sufficient:
        classification = None
        classification_reasons: tuple[str, ...] = ()
    elif (
        median_baseline_jaccard < MIN_BASELINE_SIMILARITY
        or median_baseline_ranked < MIN_BASELINE_SIMILARITY
    ):
        classification = SessionProfileDepthClassification.INCONCLUSIVE
        classification_reasons = (
            "same-profile repeatability is below the frozen interpretability floor",
            (
                f"median baseline Jaccard={median_baseline_jaccard:.4f}; "
                f"required >= {MIN_BASELINE_SIMILARITY:.2f}"
            ),
            (
                f"median baseline ranked overlap={median_baseline_ranked:.4f}; "
                f"required >= {MIN_BASELINE_SIMILARITY:.2f}"
            ),
        )
    elif (
        median_jaccard_gap <= MEDIAN_PROFILE_GAP_MAX
        and p75_jaccard_gap <= P75_PROFILE_GAP_MAX
        and median_ranked_gap <= MEDIAN_PROFILE_GAP_MAX
        and p75_ranked_gap <= P75_PROFILE_GAP_MAX
    ):
        classification = SessionProfileDepthClassification.STABLE
        classification_reasons = (
            "cross-profile similarity remains within every frozen gap tolerance",
            f"median Jaccard gap={median_jaccard_gap:.4f} <= {MEDIAN_PROFILE_GAP_MAX:.2f}",
            f"p75 Jaccard gap={p75_jaccard_gap:.4f} <= {P75_PROFILE_GAP_MAX:.2f}",
            f"median ranked gap={median_ranked_gap:.4f} <= {MEDIAN_PROFILE_GAP_MAX:.2f}",
            f"p75 ranked gap={p75_ranked_gap:.4f} <= {P75_PROFILE_GAP_MAX:.2f}",
        )
    else:
        classification = SessionProfileDepthClassification.MATERIAL_DIFFERENCE
        classification_reasons = (
            "at least one frozen cross-profile gap tolerance was exceeded",
            f"median Jaccard gap={median_jaccard_gap:.4f}",
            f"p75 Jaccard gap={p75_jaccard_gap:.4f}",
            f"median ranked gap={median_ranked_gap:.4f}",
            f"p75 ranked gap={p75_ranked_gap:.4f}",
        )

    return SessionProfileDepthMetrics(
        depth=depth,
        median_within_baseline_jaccard=median_baseline_jaccard,
        median_cross_profile_jaccard=median_cross_jaccard,
        median_jaccard_profile_gap=median_jaccard_gap,
        p75_jaccard_profile_gap=p75_jaccard_gap,
        median_within_baseline_ranked_overlap=median_baseline_ranked,
        median_cross_profile_ranked_overlap=median_cross_ranked,
        median_ranked_overlap_profile_gap=median_ranked_gap,
        p75_ranked_overlap_profile_gap=p75_ranked_gap,
        median_clean_unique_games=float(median(clean_counts)),
        median_persistent_unique_games=float(median(persistent_counts)),
        classification=classification,
        classification_reasons=classification_reasons,
    )


def _sufficiency_reasons(
    blocks: Sequence[SessionProfileBlockObservation],
    span_hours: float,
    hour_buckets: int,
    clean_outer_count: int,
    persistent_outer_count: int,
) -> list[str]:
    reasons: list[str] = []
    if len(blocks) < MIN_ELIGIBLE_BLOCKS:
        reasons.append(f"eligible blocks={len(blocks)} < required {MIN_ELIGIBLE_BLOCKS}")
    if span_hours < MIN_SAMPLE_SPAN_HOURS:
        reasons.append(
            f"sample span={span_hours:.2f}h < required {MIN_SAMPLE_SPAN_HOURS:.2f}h"
        )
    if hour_buckets < MIN_DISTINCT_HOUR_BUCKETS:
        reasons.append(
            f"distinct UTC hour buckets={hour_buckets} < required {MIN_DISTINCT_HOUR_BUCKETS}"
        )
    if clean_outer_count < MIN_BLOCKS_PER_ORDER:
        reasons.append(
            f"C-P-P-C blocks={clean_outer_count} < required {MIN_BLOCKS_PER_ORDER}"
        )
    if persistent_outer_count < MIN_BLOCKS_PER_ORDER:
        reasons.append(
            f"P-C-C-P blocks={persistent_outer_count} < required {MIN_BLOCKS_PER_ORDER}"
        )
    return reasons


def _sample_span_hours(blocks: Sequence[SessionProfileBlockObservation]) -> float:
    if len(blocks) < 2:
        return 0.0
    starts = [block.started_at.astimezone(UTC) for block in blocks]
    return (max(starts) - min(starts)).total_seconds() / 3600.0


def _hour_buckets_utc(
    blocks: Sequence[SessionProfileBlockObservation],
) -> tuple[str, ...]:
    buckets = {
        block.started_at.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
        for block in blocks
    }
    return tuple(value.isoformat().replace("+00:00", "Z") for value in sorted(buckets))


def _block_order(
    profiles: Sequence[SessionProfile],
) -> SessionProfileBlockOrder:
    clean_outer = (
        SessionProfile.CLEAN_ANONYMOUS,
        SessionProfile.PERSISTENT_ANONYMOUS,
        SessionProfile.PERSISTENT_ANONYMOUS,
        SessionProfile.CLEAN_ANONYMOUS,
    )
    persistent_outer = (
        SessionProfile.PERSISTENT_ANONYMOUS,
        SessionProfile.CLEAN_ANONYMOUS,
        SessionProfile.CLEAN_ANONYMOUS,
        SessionProfile.PERSISTENT_ANONYMOUS,
    )
    if tuple(profiles) == clean_outer:
        return SessionProfileBlockOrder.CLEAN_OUTER
    if tuple(profiles) == persistent_outer:
        return SessionProfileBlockOrder.PERSISTENT_OUTER
    raise ValueError("session-profile block order must be C-P-P-C or P-C-C-P")


def _is_session_instance_id(value: str | None) -> bool:
    if value is None or not value.startswith("session:"):
        return False
    suffix = value.removeprefix("session:")
    return len(suffix) == 32 and all(character in "0123456789abcdef" for character in suffix)


def _jaccard(first: Sequence[int], second: Sequence[int]) -> float:
    first_set = set(first)
    second_set = set(second)
    union = first_set | second_set
    if not union:
        return 1.0
    return len(first_set & second_set) / len(union)


def _ranked_prefix_overlap(
    first: Sequence[int],
    second: Sequence[int],
    *,
    persistence: float,
) -> float:
    if not 0.0 < persistence < 1.0:
        raise ValueError("rank persistence must be between 0 and 1")
    depth_limit = max(len(first), len(second))
    if depth_limit == 0:
        return 1.0

    first_seen: set[int] = set()
    second_seen: set[int] = set()
    score = 0.0
    final_overlap = 0.0
    for depth in range(1, depth_limit + 1):
        if depth <= len(first):
            first_seen.add(first[depth - 1])
        if depth <= len(second):
            second_seen.add(second[depth - 1])
        final_overlap = len(first_seen & second_seen) / depth
        score += (1.0 - persistence) * persistence ** (depth - 1) * final_overlap

    score += persistence**depth_limit * final_overlap
    return score


def _percentile(values: Sequence[float], quantile: float) -> float | None:
    if not values:
        return None
    if not 0.0 <= quantile <= 1.0:
        raise ValueError("quantile must be between 0 and 1")
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = floor(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _required_percentile(values: Sequence[float], quantile: float) -> float:
    result = _percentile(values, quantile)
    if result is None:
        raise RuntimeError("session-profile metrics unexpectedly lack percentile values")
    return result


def _optional_token(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise SessionProfileEligibilityError(
            "pagination token in raw session-profile metadata must be a string"
        )
    stripped = value.strip()
    return stripped or None
