from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC
from itertools import combinations
from math import floor
from statistics import median
from typing import Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, model_validator

from yandex_analytics_reaper.domain import ProbeKind, ProbeRunStatus, SessionProfile
from yandex_analytics_reaper.sources.yandex.parsers import YandexFeedParser
from yandex_analytics_reaper.sources.yandex.probes import probe_page_from_yandex
from yandex_analytics_reaper.storage import FilesystemRawSnapshotStore, SQLiteProbeRunStore

SPEC_VERSION = "feed-depth-v1"
ANALYZER_VERSION = "1"
PARSER_VERSION = "2"
CANDIDATE_DEPTHS = (1, 3, 5, 10)
PAGE_SIZE = 20
MIN_ELIGIBLE_TRIALS = 8
MIN_SAMPLE_SPAN_HOURS = 4.0
MIN_DISTINCT_HOUR_BUCKETS = 3
MEDIAN_COVERAGE_MIN = 0.90
P25_COVERAGE_MIN = 0.85
MEDIAN_MARGINAL_GAIN_MAX = 0.10
RANK_STABILITY_TOLERANCE = 0.03
RANK_PERSISTENCE = 0.90


class FeedDepthTrialObservation(BaseModel):
    """Replay-derived organic rankings for one eligible up-to-10-page feed run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    started_at: AwareDatetime
    organic_rankings: dict[int, tuple[int, ...]]

    @model_validator(mode="after")
    def validate_rankings(self) -> Self:
        if set(self.organic_rankings) != set(CANDIDATE_DEPTHS):
            raise ValueError("feed-depth trial must contain rankings for 1/3/5/10 pages")
        full = self.organic_rankings[10]
        if not full:
            raise ValueError("feed-depth trial requires at least one organic game")
        for depth in CANDIDATE_DEPTHS:
            ranked = self.organic_rankings[depth]
            if len(ranked) != len(set(ranked)):
                raise ValueError("organic feed rankings must contain unique app IDs")
            if tuple(full[: len(ranked)]) != ranked:
                raise ValueError("shallower feed-depth rankings must be prefixes of depth 10")
        return self


class RejectedFeedDepthTrial(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    reason: str


class FeedDepthMetrics(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    depth: int
    median_unique_games: float | None
    median_coverage_vs_10: float | None
    p25_coverage_vs_10: float | None
    median_marginal_gain_to_next: float | None
    median_pairwise_jaccard: float | None
    median_pairwise_ranked_overlap: float | None


class FeedDepthDecisionPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    minimum_eligible_trials: int = MIN_ELIGIBLE_TRIALS
    minimum_sample_span_hours: float = MIN_SAMPLE_SPAN_HOURS
    minimum_distinct_hour_buckets: int = MIN_DISTINCT_HOUR_BUCKETS
    median_coverage_min: float = MEDIAN_COVERAGE_MIN
    p25_coverage_min: float = P25_COVERAGE_MIN
    median_marginal_gain_max: float = MEDIAN_MARGINAL_GAIN_MAX
    rank_stability_tolerance: float = RANK_STABILITY_TOLERANCE
    rank_persistence: float = RANK_PERSISTENCE


class FeedDepthReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: str = SPEC_VERSION
    analyzer_version: str = ANALYZER_VERSION
    parser_version: str = PARSER_VERSION
    candidate_depths: tuple[int, ...] = CANDIDATE_DEPTHS
    page_size: int = PAGE_SIZE
    submitted_run_ids: tuple[str, ...]
    eligible_run_ids: tuple[str, ...]
    eligible_trial_count: int
    rejected_trials: tuple[RejectedFeedDepthTrial, ...]
    sample_span_hours: float
    hour_buckets_utc: tuple[str, ...]
    distinct_hour_buckets: int
    sample_sufficient: bool
    decision_policy: FeedDepthDecisionPolicy
    metrics: tuple[FeedDepthMetrics, ...]
    recommended_depth: int | None
    decision_reasons: tuple[str, ...]


class FeedDepthEligibilityError(ValueError):
    """A submitted probe run cannot be used as a feed-depth-v1 trial."""


class FeedDepthExperiment:
    """Replay stored feed runs and evaluate the frozen feed-depth-v1 policy."""

    def __init__(
        self,
        *,
        raw_store: FilesystemRawSnapshotStore,
        probe_store: SQLiteProbeRunStore,
    ) -> None:
        self.raw_store = raw_store
        self.probe_store = probe_store

    def load_trial(self, run_id: str) -> FeedDepthTrialObservation:
        record = self.probe_store.get_run(run_id)
        if record is None:
            raise FeedDepthEligibilityError(f"probe run does not exist: {run_id}")

        run = record.run
        context = record.context
        if run.kind is not ProbeKind.RECOMMENDATION_FEED:
            raise FeedDepthEligibilityError("feed-depth trial must be a recommendation-feed run")
        if run.status is not ProbeRunStatus.COMPLETED:
            raise FeedDepthEligibilityError("feed-depth trial must have completed status")
        if run.requested_page_limit != 10:
            raise FeedDepthEligibilityError("feed-depth trial must request exactly 10 pages")

        page_count = len(record.pages)
        expected_indexes = tuple(range(page_count))
        actual_indexes = tuple(page.page_index for page in record.pages)
        if not 1 <= page_count <= 10 or actual_indexes != expected_indexes:
            raise FeedDepthEligibilityError(
                "feed-depth trial must contain a contiguous page prefix from 0 with at most 10 pages"
            )
        if page_count < 10 and record.pages[-1].has_next_page:
            raise FeedDepthEligibilityError(
                "feed-depth trial stopped before page 10 without source exhaustion"
            )

        if context.session_profile is not SessionProfile.CLEAN_ANONYMOUS:
            raise FeedDepthEligibilityError("feed-depth-v1 requires clean_anonymous session profile")
        if context.cookie_state_hash is not None or context.profile_age_days != 0:
            raise FeedDepthEligibilityError("feed-depth-v1 requires fresh clean-anonymous provenance")
        if context.language != "ru":
            raise FeedDepthEligibilityError("feed-depth-v1 requires language=ru")
        if context.device_type != "desktop":
            raise FeedDepthEligibilityError("feed-depth-v1 requires device_type=desktop")
        if context.platform != "desktop_other":
            raise FeedDepthEligibilityError("feed-depth-v1 requires platform=desktop_other")

        parser = YandexFeedParser()
        if parser.version != PARSER_VERSION:
            raise FeedDepthEligibilityError(
                f"feed-depth-v1 requires YandexFeedParser@{PARSER_VERSION}; "
                f"current parser is @{parser.version}"
            )

        ranked: list[int] = []
        seen: set[int] = set()
        rankings: dict[int, tuple[int, ...]] = {}

        for page in record.pages:
            try:
                metadata = self.raw_store.get_metadata(run.source_id, page.raw_snapshot_id)
                body = self.raw_store.get_body(run.source_id, page.raw_snapshot_id)
            except (OSError, ValueError) as exc:
                raise FeedDepthEligibilityError(
                    f"raw replay failed for probe page {page.page_index}: {exc}"
                ) from exc

            if metadata.request_key != "catalogue.feed":
                raise FeedDepthEligibilityError("feed-depth raw page is not a catalogue.feed response")
            if not 200 <= metadata.http_status < 300:
                raise FeedDepthEligibilityError(
                    "feed-depth raw page does not have a successful HTTP status"
                )
            if _feed_page_size(metadata.request_context) != PAGE_SIZE:
                raise FeedDepthEligibilityError(
                    f"feed-depth-v1 requires games_count={PAGE_SIZE} on every raw page"
                )

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
                raise FeedDepthEligibilityError(
                    f"feed-depth raw page cannot be replayed consistently: {exc}"
                ) from exc
            if replayed_page != page:
                raise FeedDepthEligibilityError(
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
            raise FeedDepthEligibilityError("feed-depth trial requires at least one organic game")
        for depth in CANDIDATE_DEPTHS:
            if depth not in rankings:
                rankings[depth] = final_ranking

        return FeedDepthTrialObservation(
            run_id=run.id,
            started_at=run.started_at,
            organic_rankings=rankings,
        )

    def analyze(self, run_ids: Sequence[str]) -> FeedDepthReport:
        submitted = tuple(run_id.strip() for run_id in run_ids)
        if any(not run_id for run_id in submitted):
            raise ValueError("feed-depth run IDs cannot be blank")
        if len(set(submitted)) != len(submitted):
            raise ValueError("feed-depth run IDs must be unique")

        eligible: list[FeedDepthTrialObservation] = []
        rejected: list[RejectedFeedDepthTrial] = []
        for run_id in submitted:
            try:
                eligible.append(self.load_trial(run_id))
            except FeedDepthEligibilityError as exc:
                rejected.append(RejectedFeedDepthTrial(run_id=run_id, reason=str(exc)))

        return evaluate_feed_depth_trials(
            eligible,
            submitted_run_ids=submitted,
            rejected_trials=tuple(rejected),
        )


def evaluate_feed_depth_trials(
    trials: Sequence[FeedDepthTrialObservation],
    *,
    submitted_run_ids: Sequence[str] | None = None,
    rejected_trials: Sequence[RejectedFeedDepthTrial] = (),
) -> FeedDepthReport:
    """Evaluate already replayed eligible trials using the frozen v1 policy."""

    eligible = tuple(trials)
    eligible_ids = tuple(trial.run_id for trial in eligible)
    rejected = tuple(rejected_trials)
    rejected_ids = tuple(trial.run_id for trial in rejected)
    if len(set(eligible_ids)) != len(eligible_ids):
        raise ValueError("eligible feed-depth trial IDs must be unique")
    if len(set(rejected_ids)) != len(rejected_ids):
        raise ValueError("rejected feed-depth trial IDs must be unique")
    if set(eligible_ids) & set(rejected_ids):
        raise ValueError("feed-depth trial cannot be both eligible and rejected")

    if submitted_run_ids is None:
        if rejected:
            raise ValueError("rejected feed-depth trials require explicit submitted_run_ids")
        submitted = eligible_ids
    else:
        submitted = tuple(submitted_run_ids)
        if len(set(submitted)) != len(submitted):
            raise ValueError("submitted feed-depth run IDs must be unique")
        if set(submitted) != set(eligible_ids) | set(rejected_ids):
            raise ValueError(
                "submitted feed-depth IDs must exactly match eligible and rejected trial IDs"
            )

    metrics = tuple(_metrics_for_depth(eligible, depth) for depth in CANDIDATE_DEPTHS)
    span_hours = _sample_span_hours(eligible)
    hour_buckets = _hour_buckets_utc(eligible)
    sufficiency_reasons = _sufficiency_reasons(eligible, span_hours, len(hour_buckets))
    sample_sufficient = not sufficiency_reasons

    if not sample_sufficient:
        recommendation = None
        decision_reasons = tuple(sufficiency_reasons)
    else:
        recommendation, decision_reasons = _recommend_depth(metrics)

    return FeedDepthReport(
        submitted_run_ids=submitted,
        eligible_run_ids=eligible_ids,
        eligible_trial_count=len(eligible),
        rejected_trials=rejected,
        sample_span_hours=span_hours,
        hour_buckets_utc=hour_buckets,
        distinct_hour_buckets=len(hour_buckets),
        sample_sufficient=sample_sufficient,
        decision_policy=FeedDepthDecisionPolicy(),
        metrics=metrics,
        recommended_depth=recommendation,
        decision_reasons=decision_reasons,
    )


def _metrics_for_depth(
    trials: Sequence[FeedDepthTrialObservation],
    depth: int,
) -> FeedDepthMetrics:
    if not trials:
        return FeedDepthMetrics(
            depth=depth,
            median_unique_games=None,
            median_coverage_vs_10=None,
            p25_coverage_vs_10=None,
            median_marginal_gain_to_next=None,
            median_pairwise_jaccard=None,
            median_pairwise_ranked_overlap=None,
        )

    unique_counts = [len(trial.organic_rankings[depth]) for trial in trials]
    coverages = [
        len(trial.organic_rankings[depth]) / len(trial.organic_rankings[10])
        for trial in trials
    ]
    next_depth = _next_depth(depth)
    marginal_gains: list[float] = []
    if next_depth is not None:
        for trial in trials:
            current_count = len(trial.organic_rankings[depth])
            next_count = len(trial.organic_rankings[next_depth])
            gain = 0.0 if next_count == 0 else (next_count - current_count) / next_count
            marginal_gains.append(gain)

    jaccards: list[float] = []
    ranked_overlaps: list[float] = []
    for first, second in combinations(trials, 2):
        first_ranked = first.organic_rankings[depth]
        second_ranked = second.organic_rankings[depth]
        jaccards.append(_jaccard(first_ranked, second_ranked))
        ranked_overlaps.append(
            _ranked_prefix_overlap(
                first_ranked,
                second_ranked,
                persistence=RANK_PERSISTENCE,
            )
        )

    return FeedDepthMetrics(
        depth=depth,
        median_unique_games=float(median(unique_counts)),
        median_coverage_vs_10=float(median(coverages)),
        p25_coverage_vs_10=_percentile(coverages, 0.25),
        median_marginal_gain_to_next=(
            None if not marginal_gains else float(median(marginal_gains))
        ),
        median_pairwise_jaccard=(None if not jaccards else float(median(jaccards))),
        median_pairwise_ranked_overlap=(
            None if not ranked_overlaps else float(median(ranked_overlaps))
        ),
    )


def _recommend_depth(metrics: Sequence[FeedDepthMetrics]) -> tuple[int, tuple[str, ...]]:
    by_depth = {metric.depth: metric for metric in metrics}
    full_rank = by_depth[10].median_pairwise_ranked_overlap
    if full_rank is None:
        raise RuntimeError("sufficient feed-depth sample is missing pairwise rank stability")

    failures: list[str] = []
    for depth in (1, 3, 5):
        metric = by_depth[depth]
        coverage = _required_metric(metric.median_coverage_vs_10, depth, "median coverage")
        p25 = _required_metric(metric.p25_coverage_vs_10, depth, "p25 coverage")
        marginal = _required_metric(
            metric.median_marginal_gain_to_next,
            depth,
            "median marginal gain",
        )
        rank = _required_metric(
            metric.median_pairwise_ranked_overlap,
            depth,
            "rank stability",
        )

        checks = (
            coverage >= MEDIAN_COVERAGE_MIN,
            p25 >= P25_COVERAGE_MIN,
            marginal <= MEDIAN_MARGINAL_GAIN_MAX,
            rank >= full_rank - RANK_STABILITY_TOLERANCE,
        )
        if all(checks):
            return (
                depth,
                (
                    f"depth {depth} is the smallest candidate satisfying feed-depth-v1",
                    f"median coverage={coverage:.4f} >= {MEDIAN_COVERAGE_MIN:.2f}",
                    f"p25 coverage={p25:.4f} >= {P25_COVERAGE_MIN:.2f}",
                    (
                        f"median marginal gain={marginal:.4f} "
                        f"<= {MEDIAN_MARGINAL_GAIN_MAX:.2f}"
                    ),
                    (
                        f"rank stability={rank:.4f} within "
                        f"{RANK_STABILITY_TOLERANCE:.2f} of depth 10 ({full_rank:.4f})"
                    ),
                ),
            )
        failures.append(
            f"depth {depth} failed: coverage={coverage:.4f}, p25={p25:.4f}, "
            f"marginal={marginal:.4f}, rank={rank:.4f}, full_rank={full_rank:.4f}"
        )

    return (
        10,
        tuple(failures)
        + ("no shallower candidate passed every predeclared threshold; use depth 10",),
    )


def _sufficiency_reasons(
    trials: Sequence[FeedDepthTrialObservation],
    span_hours: float,
    hour_buckets: int,
) -> list[str]:
    reasons: list[str] = []
    if len(trials) < MIN_ELIGIBLE_TRIALS:
        reasons.append(f"eligible trials={len(trials)} < required {MIN_ELIGIBLE_TRIALS}")
    if span_hours < MIN_SAMPLE_SPAN_HOURS:
        reasons.append(
            f"sample span={span_hours:.2f}h < required {MIN_SAMPLE_SPAN_HOURS:.2f}h"
        )
    if hour_buckets < MIN_DISTINCT_HOUR_BUCKETS:
        reasons.append(
            f"distinct UTC hour buckets={hour_buckets} < required {MIN_DISTINCT_HOUR_BUCKETS}"
        )
    return reasons


def _sample_span_hours(trials: Sequence[FeedDepthTrialObservation]) -> float:
    if len(trials) < 2:
        return 0.0
    starts = [trial.started_at.astimezone(UTC) for trial in trials]
    return (max(starts) - min(starts)).total_seconds() / 3600.0


def _hour_buckets_utc(trials: Sequence[FeedDepthTrialObservation]) -> tuple[str, ...]:
    buckets = {
        trial.started_at.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
        for trial in trials
    }
    return tuple(
        value.isoformat().replace("+00:00", "Z")
        for value in sorted(buckets)
    )


def _feed_page_size(request_context: dict[str, object]) -> int | None:
    params = request_context.get("params")
    if not isinstance(params, dict):
        return None
    value = params.get("games_count")
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _next_depth(depth: int) -> int | None:
    try:
        index = CANDIDATE_DEPTHS.index(depth)
    except ValueError as exc:
        raise ValueError(f"unsupported feed depth: {depth}") from exc
    if index + 1 >= len(CANDIDATE_DEPTHS):
        return None
    return CANDIDATE_DEPTHS[index + 1]


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


def _required_metric(value: float | None, depth: int, name: str) -> float:
    if value is None:
        raise RuntimeError(f"sufficient sample missing {name} for depth {depth}")
    return value
