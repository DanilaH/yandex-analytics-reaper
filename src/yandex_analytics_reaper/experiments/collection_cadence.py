from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from enum import StrEnum
from math import floor
from statistics import median
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SPEC_VERSION = "collection-cadence-v1"
ANALYZER_VERSION = "1"
CANDIDATE_INTERVAL_DAYS = (1, 2, 3, 7)
MIN_REFERENCE_DAYS = 28
MIN_LISTING_SERIES = 20
STATE_MEDIAN_MATCH_MIN = 0.90
STATE_P25_MATCH_MIN = 0.80
RANK_MEDIAN_JACCARD_MIN = 0.80
RANK_P25_JACCARD_MIN = 0.65
RANK_MEDIAN_OVERLAP_MIN = 0.75
RANK_P25_OVERLAP_MIN = 0.60
RANK_PERSISTENCE = 0.90
RANKING_DEPTHS = (1, 3, 5, 10)


class CadenceCapability(StrEnum):
    CATALOGUE_METADATA = "catalogue_metadata"
    GAME_PAGE = "game_page"
    RECOMMENDATION_FEED = "recommendation_feed"
    SEARCH = "search"


class CadenceStateSignal(StrEnum):
    YANDEX_GAMES_RATING = "yandex_games_rating"
    RATING_COUNT = "rating_count"
    MEDIA_MANIFEST = "media_manifest"
    GAME_PAGE_UPDATE = "game_page_update"


class StateReferencePoint(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    reference_date: date
    value: str

    @field_validator("value")
    @classmethod
    def require_value(cls, value: str) -> str:
        if not value:
            raise ValueError("state reference value cannot be blank")
        return value


class RankingReferencePoint(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    reference_date: date
    ranking: tuple[str, ...] = Field(min_length=1)

    @field_validator("ranking")
    @classmethod
    def validate_ranking(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("cadence ranking must contain unique listing IDs")
        if any(not item for item in value):
            raise ValueError("cadence ranking listing IDs cannot be blank")
        return value


class StateSeriesObservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    series_id: str
    capability: CadenceCapability
    signal: CadenceStateSignal
    points: tuple[StateReferencePoint, ...] = Field(min_length=MIN_REFERENCE_DAYS)

    @field_validator("series_id")
    @classmethod
    def require_series_id(cls, value: str) -> str:
        return _require_exact_non_blank(value, "series_id")

    @model_validator(mode="after")
    def validate_series(self) -> Self:
        _validate_signal_capability(self.signal, self.capability)
        _validate_reference_dates(tuple(point.reference_date for point in self.points))
        return self


class RankingSeriesObservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    series_id: str
    capability: CadenceCapability
    depth: int
    query_text: str | None = None
    points: tuple[RankingReferencePoint, ...] = Field(min_length=MIN_REFERENCE_DAYS)

    @field_validator("series_id")
    @classmethod
    def require_series_id(cls, value: str) -> str:
        return _require_exact_non_blank(value, "series_id")

    @model_validator(mode="after")
    def validate_series(self) -> Self:
        if self.capability not in {
            CadenceCapability.RECOMMENDATION_FEED,
            CadenceCapability.SEARCH,
        }:
            raise ValueError("ranking cadence series must be feed or search")
        if self.depth not in RANKING_DEPTHS:
            raise ValueError("ranking cadence depth must be 1, 3, 5, or 10")
        if (
            self.capability is CadenceCapability.RECOMMENDATION_FEED
            and self.query_text is not None
        ):
            raise ValueError("feed cadence series cannot carry query_text")
        if self.capability is CadenceCapability.SEARCH and self.query_text is None:
            raise ValueError("search cadence series requires query_text")
        if self.query_text is not None:
            _require_exact_non_blank(self.query_text, "query_text")
        _validate_reference_dates(tuple(point.reference_date for point in self.points))
        return self


class StateCandidateMetrics(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    interval_days: int
    series_count: int
    median_reference_match_ratio: float | None
    p25_reference_match_ratio: float | None
    minimum_reference_match_ratio: float | None
    passes: bool


class StateSignalReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    capability: CadenceCapability
    signal: CadenceStateSignal
    series_count: int
    minimum_series_required: int
    sample_sufficient: bool
    metrics: tuple[StateCandidateMetrics, ...]
    recommended_interval_days: int | None
    diagnostic_only: bool = False


class StateCapabilityReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    capability: CadenceCapability
    participating_signals: tuple[CadenceStateSignal, ...]
    sample_sufficient: bool
    recommended_interval_days: int | None
    decision_reasons: tuple[str, ...]


class RankingCandidateMetrics(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    interval_days: int
    series_count: int
    median_series_median_jaccard: float | None
    p25_series_median_jaccard: float | None
    median_series_median_ranked_overlap: float | None
    p25_series_median_ranked_overlap: float | None
    passes: bool


class RankingCadenceReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    capability: CadenceCapability
    depth: int
    series_count: int
    sample_sufficient: bool
    metrics: tuple[RankingCandidateMetrics, ...]
    recommended_interval_days: int | None


class CollectionCadenceDecisionPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_interval_days: tuple[int, ...] = CANDIDATE_INTERVAL_DAYS
    minimum_reference_days: int = MIN_REFERENCE_DAYS
    minimum_listing_series: int = MIN_LISTING_SERIES
    state_median_match_min: float = STATE_MEDIAN_MATCH_MIN
    state_p25_match_min: float = STATE_P25_MATCH_MIN
    rank_median_jaccard_min: float = RANK_MEDIAN_JACCARD_MIN
    rank_p25_jaccard_min: float = RANK_P25_JACCARD_MIN
    rank_median_overlap_min: float = RANK_MEDIAN_OVERLAP_MIN
    rank_p25_overlap_min: float = RANK_P25_OVERLAP_MIN
    rank_persistence: float = RANK_PERSISTENCE


class CollectionCadenceReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: str = SPEC_VERSION
    analyzer_version: str = ANALYZER_VERSION
    reference_dates: tuple[date, ...]
    decision_policy: CollectionCadenceDecisionPolicy
    state_signal_reports: tuple[StateSignalReport, ...]
    state_capability_reports: tuple[StateCapabilityReport, ...]
    ranking_reports: tuple[RankingCadenceReport, ...]


def evaluate_collection_cadence(
    *,
    state_series: Sequence[StateSeriesObservation],
    ranking_series: Sequence[RankingSeriesObservation],
) -> CollectionCadenceReport:
    """Evaluate slower cadence candidates against one explicit daily reference window."""

    _validate_unique_series_ids(state_series, ranking_series)
    reference_dates = _shared_reference_dates(state_series, ranking_series)

    signal_reports = tuple(
        _evaluate_state_signal(signal, state_series) for signal in CadenceStateSignal
    )
    capability_reports = (
        _evaluate_state_capability(CadenceCapability.CATALOGUE_METADATA, signal_reports),
        _evaluate_state_capability(CadenceCapability.GAME_PAGE, signal_reports),
    )
    ranking_reports = tuple(
        _evaluate_ranking_group(capability, depth, ranking_series)
        for capability in (
            CadenceCapability.RECOMMENDATION_FEED,
            CadenceCapability.SEARCH,
        )
        for depth in RANKING_DEPTHS
    )

    _assert_daily_identity(signal_reports, ranking_reports)
    return CollectionCadenceReport(
        reference_dates=reference_dates,
        decision_policy=CollectionCadenceDecisionPolicy(),
        state_signal_reports=signal_reports,
        state_capability_reports=capability_reports,
        ranking_reports=ranking_reports,
    )


def _evaluate_state_signal(
    signal: CadenceStateSignal,
    all_series: Sequence[StateSeriesObservation],
) -> StateSignalReport:
    series = [item for item in all_series if item.signal is signal]
    capability = _signal_capability(signal)
    minimum_required = MIN_LISTING_SERIES
    diagnostic_only = (
        signal is CadenceStateSignal.MEDIA_MANIFEST and len(series) < minimum_required
    )
    sample_sufficient = len(series) >= minimum_required

    metrics: list[StateCandidateMetrics] = []
    for interval in CANDIDATE_INTERVAL_DAYS:
        ratios = [_state_match_ratio(item, interval) for item in series]
        median_ratio = _median_or_none(ratios)
        p25_ratio = _percentile(ratios, 0.25)
        minimum_ratio = min(ratios) if ratios else None
        passes = bool(
            sample_sufficient
            and median_ratio is not None
            and p25_ratio is not None
            and median_ratio >= STATE_MEDIAN_MATCH_MIN
            and p25_ratio >= STATE_P25_MATCH_MIN
        )
        metrics.append(
            StateCandidateMetrics(
                interval_days=interval,
                series_count=len(series),
                median_reference_match_ratio=median_ratio,
                p25_reference_match_ratio=p25_ratio,
                minimum_reference_match_ratio=minimum_ratio,
                passes=passes,
            )
        )

    recommended = _slowest_passing_state(metrics) if sample_sufficient else None
    return StateSignalReport(
        capability=capability,
        signal=signal,
        series_count=len(series),
        minimum_series_required=minimum_required,
        sample_sufficient=sample_sufficient,
        metrics=tuple(metrics),
        recommended_interval_days=recommended,
        diagnostic_only=diagnostic_only,
    )


def _evaluate_state_capability(
    capability: CadenceCapability,
    signal_reports: Sequence[StateSignalReport],
) -> StateCapabilityReport:
    reports = {report.signal: report for report in signal_reports}
    required: tuple[CadenceStateSignal, ...]
    participating: tuple[CadenceStateSignal, ...]
    if capability is CadenceCapability.CATALOGUE_METADATA:
        required = (
            CadenceStateSignal.YANDEX_GAMES_RATING,
            CadenceStateSignal.RATING_COUNT,
        )
        media = reports[CadenceStateSignal.MEDIA_MANIFEST]
        participating = required + (
            (CadenceStateSignal.MEDIA_MANIFEST,) if media.sample_sufficient else ()
        )
    elif capability is CadenceCapability.GAME_PAGE:
        required = (CadenceStateSignal.GAME_PAGE_UPDATE,)
        participating = required
    else:
        raise ValueError("state cadence capability must be catalogue_metadata or game_page")

    missing = [signal for signal in required if not reports[signal].sample_sufficient]
    if missing:
        return StateCapabilityReport(
            capability=capability,
            participating_signals=participating,
            sample_sufficient=False,
            recommended_interval_days=None,
            decision_reasons=tuple(
                f"{signal.value} series={reports[signal].series_count} "
                f"< required {reports[signal].minimum_series_required}"
                for signal in missing
            ),
        )

    recommended: int | None = None
    reasons: list[str] = []
    for interval in reversed(CANDIDATE_INTERVAL_DAYS):
        passing = all(
            _state_metric_for_interval(reports[signal], interval).passes
            for signal in participating
        )
        if passing:
            recommended = interval
            reasons.append(
                f"slowest passing interval is {interval} days across participating signals"
            )
            break
    if recommended is None:
        reasons.append("no candidate interval passed every participating state signal")

    if capability is CadenceCapability.CATALOGUE_METADATA:
        media_report = reports[CadenceStateSignal.MEDIA_MANIFEST]
        if not media_report.sample_sufficient:
            reasons.append(
                "media_manifest has fewer than 20 complete series and remains diagnostic-only"
            )

    return StateCapabilityReport(
        capability=capability,
        participating_signals=participating,
        sample_sufficient=True,
        recommended_interval_days=recommended,
        decision_reasons=tuple(reasons),
    )


def _evaluate_ranking_group(
    capability: CadenceCapability,
    depth: int,
    all_series: Sequence[RankingSeriesObservation],
) -> RankingCadenceReport:
    series = [
        item
        for item in all_series
        if item.capability is capability and item.depth == depth
    ]
    if capability is CadenceCapability.RECOMMENDATION_FEED:
        sample_sufficient = len(series) == 1
    elif capability is CadenceCapability.SEARCH:
        sample_sufficient = len(series) >= 1
    else:
        raise ValueError("ranking cadence capability must be feed or search")

    metrics: list[RankingCandidateMetrics] = []
    for interval in CANDIDATE_INTERVAL_DAYS:
        series_median_jaccard: list[float] = []
        series_median_overlap: list[float] = []
        for item in series:
            jaccard_values, overlap_values = _ranking_similarities(item, interval)
            series_median_jaccard.append(float(median(jaccard_values)))
            series_median_overlap.append(float(median(overlap_values)))

        median_jaccard = _median_or_none(series_median_jaccard)
        p25_jaccard = _percentile(series_median_jaccard, 0.25)
        median_overlap = _median_or_none(series_median_overlap)
        p25_overlap = _percentile(series_median_overlap, 0.25)
        passes = bool(
            sample_sufficient
            and median_jaccard is not None
            and p25_jaccard is not None
            and median_overlap is not None
            and p25_overlap is not None
            and median_jaccard >= RANK_MEDIAN_JACCARD_MIN
            and p25_jaccard >= RANK_P25_JACCARD_MIN
            and median_overlap >= RANK_MEDIAN_OVERLAP_MIN
            and p25_overlap >= RANK_P25_OVERLAP_MIN
        )
        metrics.append(
            RankingCandidateMetrics(
                interval_days=interval,
                series_count=len(series),
                median_series_median_jaccard=median_jaccard,
                p25_series_median_jaccard=p25_jaccard,
                median_series_median_ranked_overlap=median_overlap,
                p25_series_median_ranked_overlap=p25_overlap,
                passes=passes,
            )
        )

    recommended = _slowest_passing_ranking(metrics) if sample_sufficient else None
    return RankingCadenceReport(
        capability=capability,
        depth=depth,
        series_count=len(series),
        sample_sufficient=sample_sufficient,
        metrics=tuple(metrics),
        recommended_interval_days=recommended,
    )


def _state_match_ratio(series: StateSeriesObservation, interval: int) -> float:
    matches = 0
    for index, point in enumerate(series.points):
        retained_index = (index // interval) * interval
        if series.points[retained_index].value == point.value:
            matches += 1
    return matches / len(series.points)


def _ranking_similarities(
    series: RankingSeriesObservation,
    interval: int,
) -> tuple[list[float], list[float]]:
    jaccard_values: list[float] = []
    overlap_values: list[float] = []
    for index, point in enumerate(series.points):
        retained_index = (index // interval) * interval
        retained = series.points[retained_index].ranking
        jaccard_values.append(_jaccard(retained, point.ranking))
        overlap_values.append(
            _ranked_prefix_overlap(
                retained,
                point.ranking,
                persistence=RANK_PERSISTENCE,
            )
        )
    return jaccard_values, overlap_values


def _state_metric_for_interval(
    report: StateSignalReport,
    interval: int,
) -> StateCandidateMetrics:
    for metric in report.metrics:
        if metric.interval_days == interval:
            return metric
    raise RuntimeError(f"state cadence metric is missing interval {interval}")


def _slowest_passing_state(metrics: Sequence[StateCandidateMetrics]) -> int | None:
    passing = [metric.interval_days for metric in metrics if metric.passes]
    return max(passing) if passing else None


def _slowest_passing_ranking(metrics: Sequence[RankingCandidateMetrics]) -> int | None:
    passing = [metric.interval_days for metric in metrics if metric.passes]
    return max(passing) if passing else None


def _assert_daily_identity(
    state_reports: Sequence[StateSignalReport],
    ranking_reports: Sequence[RankingCadenceReport],
) -> None:
    for report in state_reports:
        if report.series_count == 0:
            continue
        metric = _state_metric_for_interval(report, 1)
        if (
            metric.median_reference_match_ratio != 1.0
            or metric.p25_reference_match_ratio != 1.0
            or metric.minimum_reference_match_ratio != 1.0
        ):
            raise RuntimeError("daily state cadence must be identity against its reference")
    for report in ranking_reports:
        if report.series_count == 0:
            continue
        metric = next(item for item in report.metrics if item.interval_days == 1)
        if (
            metric.median_series_median_jaccard != 1.0
            or metric.p25_series_median_jaccard != 1.0
            or metric.median_series_median_ranked_overlap != 1.0
            or metric.p25_series_median_ranked_overlap != 1.0
        ):
            raise RuntimeError("daily ranking cadence must be identity against its reference")


def _shared_reference_dates(
    state_series: Sequence[StateSeriesObservation],
    ranking_series: Sequence[RankingSeriesObservation],
) -> tuple[date, ...]:
    all_dates = [
        tuple(point.reference_date for point in series.points)
        for series in (*state_series, *ranking_series)
    ]
    if not all_dates:
        raise ValueError("collection cadence evaluation requires at least one series")
    expected = all_dates[0]
    if any(dates != expected for dates in all_dates[1:]):
        raise ValueError("all cadence series must use the same daily reference dates")
    return expected


def _validate_unique_series_ids(
    state_series: Sequence[StateSeriesObservation],
    ranking_series: Sequence[RankingSeriesObservation],
) -> None:
    series_ids = [series.series_id for series in (*state_series, *ranking_series)]
    if len(series_ids) != len(set(series_ids)):
        raise ValueError("collection cadence series IDs must be globally unique")


def _validate_signal_capability(
    signal: CadenceStateSignal,
    capability: CadenceCapability,
) -> None:
    expected = _signal_capability(signal)
    if capability is not expected:
        raise ValueError(
            f"state signal {signal.value} belongs to capability {expected.value}"
        )


def _signal_capability(signal: CadenceStateSignal) -> CadenceCapability:
    if signal in {
        CadenceStateSignal.YANDEX_GAMES_RATING,
        CadenceStateSignal.RATING_COUNT,
        CadenceStateSignal.MEDIA_MANIFEST,
    }:
        return CadenceCapability.CATALOGUE_METADATA
    return CadenceCapability.GAME_PAGE


def _validate_reference_dates(values: Sequence[date]) -> None:
    if len(values) < MIN_REFERENCE_DAYS:
        raise ValueError(
            f"cadence reference requires at least {MIN_REFERENCE_DAYS} daily checkpoints"
        )
    if len(values) != len(set(values)):
        raise ValueError("cadence reference dates must be unique")
    if tuple(values) != tuple(sorted(values)):
        raise ValueError("cadence reference dates must be strictly increasing")
    for previous, current in zip(values, values[1:], strict=False):
        if (current - previous).days != 1:
            raise ValueError("cadence reference dates must be consecutive UTC dates")


def _jaccard(first: Sequence[str], second: Sequence[str]) -> float:
    first_set = set(first)
    second_set = set(second)
    union = first_set | second_set
    if not union:
        return 1.0
    return len(first_set & second_set) / len(union)


def _ranked_prefix_overlap(
    first: Sequence[str],
    second: Sequence[str],
    *,
    persistence: float,
) -> float:
    if not 0.0 < persistence < 1.0:
        raise ValueError("rank persistence must be between 0 and 1")
    depth_limit = max(len(first), len(second))
    if depth_limit == 0:
        return 1.0

    first_seen: set[str] = set()
    second_seen: set[str] = set()
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


def _median_or_none(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return float(median(values))


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


def _require_exact_non_blank(value: str, field: str) -> str:
    if not value:
        raise ValueError(f"{field} cannot be blank")
    if value != value.strip():
        raise ValueError(f"{field} must already be trimmed")
    return value
