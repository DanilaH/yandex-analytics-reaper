from __future__ import annotations

from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from yandex_analytics_reaper.experiments.collection_cadence import (
    CadenceCapability,
    CadenceStateSignal,
    RankingReferencePoint,
    RankingSeriesObservation,
    StateReferencePoint,
    StateSeriesObservation,
    evaluate_collection_cadence,
)


def _dates(count: int = 28) -> tuple[date, ...]:
    start = date(2026, 8, 1)
    return tuple(start + timedelta(days=index) for index in range(count))


def _state_series(
    *,
    prefix: str,
    signal: CadenceStateSignal,
    capability: CadenceCapability,
    values: tuple[str, ...],
    count: int = 20,
) -> tuple[StateSeriesObservation, ...]:
    dates = _dates(len(values))
    return tuple(
        StateSeriesObservation(
            series_id=f"{prefix}:{index}",
            capability=capability,
            signal=signal,
            points=tuple(
                StateReferencePoint(reference_date=day, value=value)
                for day, value in zip(dates, values, strict=True)
            ),
        )
        for index in range(count)
    )


def _ranking_series(
    *,
    series_id: str,
    capability: CadenceCapability,
    depth: int,
    rankings: tuple[tuple[str, ...], ...],
    query_text: str | None = None,
) -> RankingSeriesObservation:
    return RankingSeriesObservation(
        series_id=series_id,
        capability=capability,
        depth=depth,
        query_text=query_text,
        points=tuple(
            RankingReferencePoint(reference_date=day, ranking=ranking)
            for day, ranking in zip(_dates(len(rankings)), rankings, strict=True)
        ),
    )


def test_constant_state_series_recommend_weekly() -> None:
    values = ("stable",) * 28
    states = (
        *_state_series(
            prefix="rating",
            signal=CadenceStateSignal.YANDEX_GAMES_RATING,
            capability=CadenceCapability.CATALOGUE_METADATA,
            values=values,
        ),
        *_state_series(
            prefix="count",
            signal=CadenceStateSignal.RATING_COUNT,
            capability=CadenceCapability.CATALOGUE_METADATA,
            values=values,
        ),
        *_state_series(
            prefix="update",
            signal=CadenceStateSignal.GAME_PAGE_UPDATE,
            capability=CadenceCapability.GAME_PAGE,
            values=values,
        ),
    )

    report = evaluate_collection_cadence(state_series=states, ranking_series=())

    catalogue, game_page = report.state_capability_reports
    assert catalogue.recommended_interval_days == 7
    assert game_page.recommended_interval_days == 7
    media = next(
        item
        for item in report.state_signal_reports
        if item.signal is CadenceStateSignal.MEDIA_MANIFEST
    )
    assert media.diagnostic_only is True
    assert media.sample_sufficient is False


def test_daily_changing_required_metric_forces_daily_catalogue_cadence() -> None:
    stable = ("stable",) * 28
    changing = tuple(str(index) for index in range(28))
    states = (
        *_state_series(
            prefix="rating",
            signal=CadenceStateSignal.YANDEX_GAMES_RATING,
            capability=CadenceCapability.CATALOGUE_METADATA,
            values=stable,
        ),
        *_state_series(
            prefix="count",
            signal=CadenceStateSignal.RATING_COUNT,
            capability=CadenceCapability.CATALOGUE_METADATA,
            values=changing,
        ),
    )

    report = evaluate_collection_cadence(state_series=states, ranking_series=())

    catalogue = report.state_capability_reports[0]
    assert catalogue.recommended_interval_days == 1
    count_report = next(
        item
        for item in report.state_signal_reports
        if item.signal is CadenceStateSignal.RATING_COUNT
    )
    assert count_report.recommended_interval_days == 1
    daily = next(item for item in count_report.metrics if item.interval_days == 1)
    every_other = next(item for item in count_report.metrics if item.interval_days == 2)
    assert daily.median_reference_match_ratio == 1.0
    assert every_other.median_reference_match_ratio == 0.5


def test_alternating_feed_ranking_forces_daily_at_that_depth() -> None:
    first = ("yandex_games:1", "yandex_games:2", "yandex_games:3")
    second = ("yandex_games:4", "yandex_games:5", "yandex_games:6")
    rankings = tuple(first if index % 2 == 0 else second for index in range(28))
    feed = _ranking_series(
        series_id="feed:depth1",
        capability=CadenceCapability.RECOMMENDATION_FEED,
        depth=1,
        rankings=rankings,
    )

    report = evaluate_collection_cadence(state_series=(), ranking_series=(feed,))

    depth1 = next(
        item
        for item in report.ranking_reports
        if item.capability is CadenceCapability.RECOMMENDATION_FEED and item.depth == 1
    )
    assert depth1.sample_sufficient is True
    assert depth1.recommended_interval_days == 1
    every_other = next(item for item in depth1.metrics if item.interval_days == 2)
    assert every_other.passes is False


def test_stable_search_family_recommends_weekly() -> None:
    rankings = (("yandex_games:1", "yandex_games:2"),) * 28
    search = (
        _ranking_series(
            series_id="search:merge:depth3",
            capability=CadenceCapability.SEARCH,
            depth=3,
            query_text="merge",
            rankings=rankings,
        ),
        _ranking_series(
            series_id="search:слияние:depth3",
            capability=CadenceCapability.SEARCH,
            depth=3,
            query_text="слияние",
            rankings=rankings,
        ),
    )

    report = evaluate_collection_cadence(state_series=(), ranking_series=search)

    depth3 = next(
        item
        for item in report.ranking_reports
        if item.capability is CadenceCapability.SEARCH and item.depth == 3
    )
    assert depth3.sample_sufficient is True
    assert depth3.series_count == 2
    assert depth3.recommended_interval_days == 7


def test_insufficient_listing_series_produces_no_state_recommendation() -> None:
    stable = ("stable",) * 28
    states = _state_series(
        prefix="rating",
        signal=CadenceStateSignal.YANDEX_GAMES_RATING,
        capability=CadenceCapability.CATALOGUE_METADATA,
        values=stable,
        count=19,
    )

    report = evaluate_collection_cadence(state_series=states, ranking_series=())

    catalogue = report.state_capability_reports[0]
    assert catalogue.sample_sufficient is False
    assert catalogue.recommended_interval_days is None


def test_reference_dates_must_be_consecutive_and_shared() -> None:
    dates = list(_dates())
    dates[10] += timedelta(days=1)

    with pytest.raises(ValidationError, match="unique|consecutive"):
        StateSeriesObservation(
            series_id="broken",
            capability=CadenceCapability.GAME_PAGE,
            signal=CadenceStateSignal.GAME_PAGE_UPDATE,
            points=tuple(
                StateReferencePoint(reference_date=day, value="stable")
                for day in dates
            ),
        )

    first = _state_series(
        prefix="rating",
        signal=CadenceStateSignal.YANDEX_GAMES_RATING,
        capability=CadenceCapability.CATALOGUE_METADATA,
        values=("stable",) * 28,
        count=1,
    )[0]
    shifted_points = tuple(
        StateReferencePoint(
            reference_date=point.reference_date + timedelta(days=1),
            value=point.value,
        )
        for point in first.points
    )
    shifted = StateSeriesObservation(
        series_id="shifted",
        capability=CadenceCapability.CATALOGUE_METADATA,
        signal=CadenceStateSignal.RATING_COUNT,
        points=shifted_points,
    )

    with pytest.raises(ValueError, match="same daily reference dates"):
        evaluate_collection_cadence(
            state_series=(first, shifted),
            ranking_series=(),
        )
