from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from yandex_analytics_reaper.thesis_anomaly import (
    AnomalyCandidateV1,
    FreshAnomalyQueuePayload,
    FreshAnomalyQueueReport,
    ThesisAnomalyQueue,
    build_fresh_anomaly_queue,
    validate_fresh_anomaly_queue,
)
from yandex_analytics_reaper.thesis_intelligence import (
    ExperimentArtifactBinding,
    ThesisAnomalyPolicy,
    ThesisDeclaration,
    ThesisIntelligenceError,
    ThesisSemanticDeclaration,
    ThesisSuiteContext,
    ThesisSuiteDeclaration,
    canonical_model_hash,
)
from yandex_analytics_reaper.thesis_traction import (
    LongitudinalRatingDeltaV1,
    ThesisFieldCoverage,
    ThesisTractionFeaturesPayload,
    ThesisTractionFeaturesReport,
    ThesisTractionRow,
    ThesisTractionSet,
)

_NOW = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)


def _suite(policy: ThesisAnomalyPolicy | None) -> ThesisSuiteDeclaration:
    return ThesisSuiteDeclaration(
        suite_id="anomaly-suite",
        suite_version=1,
        context=ThesisSuiteContext(
            pages=3,
            session_profile="clean_anonymous",
            lang="ru",
            device="desktop",
            platform="desktop_other",
        ),
        anomaly_policy=policy,
        theses=(
            ThesisDeclaration(
                thesis_id="objects",
                thesis_version=1,
                label="destruction x objects",
                queries=("break objects",),
                semantic=ThesisSemanticDeclaration(
                    theme_terms=("object",),
                    mechanic_terms=("break",),
                ),
            ),
        ),
    )


def _binding() -> ExperimentArtifactBinding:
    return ExperimentArtifactBinding(
        role="current",
        artifact_sha256="a" * 64,
        artifact_manifest_sha256="b" * 64,
        experiment_id="anomaly-suite",
        run_id="run-current",
        manifest_sha256="c" * 64,
        snapshot_id="snapshot:current",
        snapshot_content_hash="d" * 64,
        snapshot_created_at=_NOW,
        market_export_content_hash="e" * 64,
        market_features_content_hash="f" * 64,
    )


def _bucket(age_days: float) -> str:
    if age_days < 7:
        return "lt_7_days"
    if age_days < 31:
        return "7_30_days"
    if age_days < 91:
        return "31_90_days"
    if age_days < 181:
        return "91_180_days"
    if age_days < 366:
        return "181_365_days"
    return "over_365_days"


def _longitudinal(
    rating_count: int | None,
    *,
    status: str = "no_prior_observation",
    velocity: float | None = None,
) -> LongitudinalRatingDeltaV1:
    if rating_count is None:
        return LongitudinalRatingDeltaV1(status="current_missing")
    current_at = _NOW - timedelta(minutes=1)
    if status == "no_prior_observation":
        return LongitudinalRatingDeltaV1(
            status="no_prior_observation",
            current_observation_id=f"current:{rating_count}",
            current_observed_at=current_at,
            current_rating_count=rating_count,
        )
    if status == "interval_too_short":
        previous_at = current_at - timedelta(hours=6)
        return LongitudinalRatingDeltaV1(
            status="interval_too_short",
            prior_artifact_sha256="1" * 64,
            previous_observation_id="prior:short",
            previous_observed_at=previous_at,
            previous_rating_count=rating_count - 1,
            current_observation_id=f"current:{rating_count}",
            current_observed_at=current_at,
            current_rating_count=rating_count,
            delta_interval_days=0.25,
            rating_count_delta=1,
        )
    if velocity is None:
        raise AssertionError("observed longitudinal fixture requires velocity")
    previous_at = current_at - timedelta(days=2)
    delta = int(velocity * 2)
    previous = rating_count - delta
    return LongitudinalRatingDeltaV1(
        status="negative_revision" if delta < 0 else "observed",
        prior_artifact_sha256="2" * 64,
        previous_observation_id="prior:observed",
        previous_observed_at=previous_at,
        previous_rating_count=previous,
        current_observation_id=f"current:{rating_count}",
        current_observed_at=current_at,
        current_rating_count=rating_count,
        delta_interval_days=2.0,
        rating_count_delta=delta,
        observed_rating_delta_per_day=velocity,
    )


def _row(
    listing_id: str,
    *,
    age_days: float,
    rating_count: int | None,
    pace_status: str = "observed",
    percentile: float | None = 0.75,
    longitudinal_status: str = "no_prior_observation",
    velocity: float | None = None,
) -> ThesisTractionRow:
    first_published = _NOW - timedelta(days=age_days)
    if pace_status == "observed":
        if rating_count is None or age_days < 1:
            raise AssertionError("observed pace fixture requires rating and age >= 1")
        pace = rating_count / age_days
    elif pace_status == "too_young":
        pace = None
        percentile = None
    elif pace_status == "missing_rating_count":
        rating_count = None
        pace = None
        percentile = None
    else:
        raise AssertionError(f"unsupported pace fixture state: {pace_status}")

    observed_at = _NOW - timedelta(minutes=1)
    longitudinal = _longitudinal(
        rating_count,
        status=longitudinal_status,
        velocity=velocity,
    )
    return ThesisTractionRow(
        platform_listing_id=listing_id,
        external_app_id=listing_id.rsplit(":", 1)[-1],
        canonical_url=f"https://yandex.ru/games/app/{listing_id.rsplit(':', 1)[-1]}",
        title=f"Game {listing_id}",
        first_published_at=first_published,
        first_published_observation_id=f"published:{listing_id}",
        listing_age_days=age_days,
        age_bucket=_bucket(age_days),
        rating_count=rating_count,
        rating_count_observation_id=(
            None if rating_count is None else f"current:{rating_count}"
        ),
        rating_count_observed_at=None if rating_count is None else observed_at,
        lifetime_ratings_per_day=pace,
        lifetime_pace_status=pace_status,
        suite_age_bucket_member_count=6,
        suite_age_bucket_pace_observed_count=3,
        suite_age_bucket_pace_coverage_ratio=0.5,
        suite_age_bucket_percentile=percentile,
        longitudinal=longitudinal,
    )


def _traction(
    suite: ThesisSuiteDeclaration,
    rows: tuple[ThesisTractionRow, ...],
) -> ThesisTractionFeaturesReport:
    observed = sum(row.rating_count is not None for row in rows)
    traction_set = ThesisTractionSet(
        thesis_id="objects",
        thesis_version=1,
        comparable_set_id="anomaly-suite--objects",
        comparable_set_version=1,
        rating_count_coverage=ThesisFieldCoverage(
            member_count=len(rows),
            observed_count=observed,
            missing_count=len(rows) - observed,
            coverage_ratio=observed / len(rows),
        ),
        rows=rows,
    )
    payload = ThesisTractionFeaturesPayload(
        suite_id=suite.suite_id,
        suite_version=suite.suite_version,
        suite_content_hash=canonical_model_hash(suite),
        reference_time=_NOW,
        current_experiment=_binding(),
        prior_experiments=(),
        theses=(traction_set,),
    )
    return ThesisTractionFeaturesReport(
        **payload.model_dump(mode="python"),
        content_hash=canonical_model_hash(payload),
    )


def test_null_policy_disables_anomaly_evaluation_completely() -> None:
    suite = _suite(None)
    traction = _traction(
        suite,
        (_row("yandex_games:1", age_days=10, rating_count=100),),
    )

    report = build_fresh_anomaly_queue(suite, traction)

    assert validate_fresh_anomaly_queue(report) == report
    assert report.status == "disabled"
    assert report.policy is None
    assert report.theses[0].status == "disabled"
    assert report.theses[0].evaluations == ()
    assert report.theses[0].candidates == ()


def test_configured_gates_emit_pass_fail_unknown_and_not_configured() -> None:
    policy = ThesisAnomalyPolicy(
        max_age_days=180,
        min_rating_count=50,
        min_lifetime_ratings_per_day=5.0,
        min_age_bucket_percentile=0.5,
    )
    suite = _suite(policy)
    rows = (
        _row("yandex_games:1", age_days=10, rating_count=100, percentile=0.75),
        _row("yandex_games:2", age_days=200, rating_count=100, percentile=0.75),
        _row(
            "yandex_games:3",
            age_days=10,
            rating_count=None,
            pace_status="missing_rating_count",
        ),
    )

    report = build_fresh_anomaly_queue(suite, _traction(suite, rows))
    first, second, third = report.theses[0].evaluations

    assert first.max_age_days_status == "pass"
    assert first.min_rating_count_status == "pass"
    assert first.min_lifetime_ratings_per_day_status == "pass"
    assert first.min_age_bucket_percentile_status == "pass"
    assert first.min_observed_rating_delta_per_day_status == "not_configured"
    assert first.is_anomaly_candidate is True

    assert second.max_age_days_status == "fail"
    assert second.is_anomaly_candidate is False

    assert third.max_age_days_status == "pass"
    assert third.min_rating_count_status == "unknown"
    assert third.min_lifetime_ratings_per_day_status == "unknown"
    assert third.min_age_bucket_percentile_status == "unknown"
    assert third.is_anomaly_candidate is False
    assert [item.platform_listing_id for item in report.theses[0].candidates] == [
        "yandex_games:1"
    ]


def test_longitudinal_gate_uses_negative_values_and_marks_missing_history_unknown() -> None:
    suite = _suite(ThesisAnomalyPolicy(min_observed_rating_delta_per_day=1.0))
    rows = (
        _row(
            "yandex_games:1",
            age_days=10,
            rating_count=100,
            longitudinal_status="observed",
            velocity=2.0,
        ),
        _row(
            "yandex_games:2",
            age_days=10,
            rating_count=100,
            longitudinal_status="negative_revision",
            velocity=-1.0,
        ),
        _row("yandex_games:3", age_days=10, rating_count=100),
        _row(
            "yandex_games:4",
            age_days=10,
            rating_count=100,
            longitudinal_status="interval_too_short",
        ),
    )

    report = build_fresh_anomaly_queue(suite, _traction(suite, rows))
    statuses = [
        item.min_observed_rating_delta_per_day_status
        for item in report.theses[0].evaluations
    ]
    assert statuses == ["pass", "fail", "unknown", "unknown"]
    assert [item.platform_listing_id for item in report.theses[0].candidates] == [
        "yandex_games:1"
    ]


def test_candidate_order_is_frozen_and_handles_unavailable_sort_facts() -> None:
    suite = _suite(ThesisAnomalyPolicy(max_age_days=180))
    rows = (
        _row("yandex_games:1", age_days=5, rating_count=100),
        _row("yandex_games:2", age_days=10, rating_count=100),
        _row("yandex_games:3", age_days=5, rating_count=50),
        _row(
            "yandex_games:4",
            age_days=0.5,
            rating_count=100,
            pace_status="too_young",
        ),
        _row(
            "yandex_games:5",
            age_days=0.25,
            rating_count=100,
            pace_status="too_young",
        ),
        _row(
            "yandex_games:6",
            age_days=5,
            rating_count=None,
            pace_status="missing_rating_count",
        ),
    )

    report = build_fresh_anomaly_queue(suite, _traction(suite, rows))

    assert [item.platform_listing_id for item in report.theses[0].candidates] == [
        "yandex_games:1",  # pace 20
        "yandex_games:2",  # pace 10, rating 100
        "yandex_games:3",  # pace 10, rating 50
        "yandex_games:5",  # pace unavailable, rating 100, younger
        "yandex_games:4",  # pace unavailable, rating 100, older
        "yandex_games:6",  # pace + rating unavailable
    ]


def test_reversed_candidate_queue_is_rejected_without_needing_traction_input() -> None:
    evaluations = (
        {
            "platform_listing_id": "yandex_games:1",
            "max_age_days_status": "pass",
            "min_rating_count_status": "not_configured",
            "min_lifetime_ratings_per_day_status": "not_configured",
            "min_age_bucket_percentile_status": "not_configured",
            "min_observed_rating_delta_per_day_status": "not_configured",
            "is_anomaly_candidate": True,
        },
        {
            "platform_listing_id": "yandex_games:2",
            "max_age_days_status": "pass",
            "min_rating_count_status": "not_configured",
            "min_lifetime_ratings_per_day_status": "not_configured",
            "min_age_bucket_percentile_status": "not_configured",
            "min_observed_rating_delta_per_day_status": "not_configured",
            "is_anomaly_candidate": True,
        },
    )
    with pytest.raises(ValidationError, match="frozen v1 queue ordering"):
        ThesisAnomalyQueue.model_validate(
            {
                "thesis_id": "objects",
                "thesis_version": 1,
                "status": "enabled",
                "evaluations": evaluations,
                "candidates": (
                    AnomalyCandidateV1(
                        platform_listing_id="yandex_games:2",
                        lifetime_ratings_per_day=5.0,
                        rating_count=50,
                        listing_age_days=10,
                    ),
                    AnomalyCandidateV1(
                        platform_listing_id="yandex_games:1",
                        lifetime_ratings_per_day=10.0,
                        rating_count=100,
                        listing_age_days=10,
                    ),
                ),
            }
        )


def test_traction_from_a_different_suite_revision_fails_closed() -> None:
    source_suite = _suite(ThesisAnomalyPolicy(max_age_days=180))
    traction = _traction(
        source_suite,
        (_row("yandex_games:1", age_days=10, rating_count=100),),
    )
    other_suite = _suite(ThesisAnomalyPolicy(max_age_days=90))

    with pytest.raises(ThesisIntelligenceError, match="does not bind"):
        build_fresh_anomaly_queue(other_suite, traction)


def test_anomaly_report_hash_tampering_is_rejected() -> None:
    suite = _suite(ThesisAnomalyPolicy(max_age_days=180))
    report = build_fresh_anomaly_queue(
        suite,
        _traction(suite, (_row("yandex_games:1", age_days=10, rating_count=100),)),
    )
    tampered = FreshAnomalyQueueReport.model_validate(
        {**report.model_dump(mode="python"), "content_hash": "0" * 64}
    )

    with pytest.raises(ThesisIntelligenceError, match="content_hash mismatch"):
        validate_fresh_anomaly_queue(tampered)


def test_report_model_cannot_claim_disabled_with_a_policy() -> None:
    suite = _suite(ThesisAnomalyPolicy(max_age_days=180))
    traction = _traction(
        suite,
        (_row("yandex_games:1", age_days=10, rating_count=100),),
    )
    report = build_fresh_anomaly_queue(suite, traction)
    payload = FreshAnomalyQueuePayload.model_validate(
        report.model_dump(exclude={"content_hash"})
    )
    with pytest.raises(ValidationError, match="status does not match policy"):
        FreshAnomalyQueuePayload.model_validate(
            {**payload.model_dump(mode="python"), "status": "disabled"}
        )
