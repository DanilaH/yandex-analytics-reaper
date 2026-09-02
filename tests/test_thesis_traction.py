from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

import pytest

from yandex_analytics_reaper.analyst import (
    AnalystComparableMembership,
    AnalystComparableSetBinding,
    AnalystEvidenceReference,
    AnalystListingRow,
    AnalystMarketExportPayload,
    AnalystMarketExportReport,
    AnalystResolvedValue,
    AnalystRichMetadataBinding,
    AnalystSearchExposure,
    AnalystSnapshotPayload,
    AnalystSnapshotReport,
)
from yandex_analytics_reaper.domain import ProbeContext
from yandex_analytics_reaper.thesis_intelligence import (
    ExperimentArtifactBinding,
    ThesisDeclaration,
    ThesisIntelligenceError,
    ThesisSemanticDeclaration,
    ThesisSuiteContext,
    ThesisSuiteDeclaration,
)
from yandex_analytics_reaper.thesis_traction import (
    BoundExperimentEvidence,
    ThesisTractionFeaturesReport,
    _age_bucket,
    _lifetime_pace,
    build_traction_features,
    validate_traction_features,
)

_NOW = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)
_IDS = tuple(f"yandex_games:{value}" for value in range(1, 5))
_SET_A = "traction-suite--alpha"
_SET_B = "traction-suite--beta"


def _suite() -> ThesisSuiteDeclaration:
    semantic = ThesisSemanticDeclaration(
        theme_terms=("object",),
        mechanic_terms=("break",),
    )
    return ThesisSuiteDeclaration(
        suite_id="traction-suite",
        suite_version=1,
        context=ThesisSuiteContext(
            pages=3,
            session_profile="clean_anonymous",
            lang="ru",
            device="desktop",
            platform="desktop_other",
        ),
        theses=(
            ThesisDeclaration(
                thesis_id="alpha",
                thesis_version=1,
                label="alpha",
                queries=("alpha query",),
                semantic=semantic,
            ),
            ThesisDeclaration(
                thesis_id="beta",
                thesis_version=2,
                label="beta",
                queries=("beta query",),
                semantic=semantic,
            ),
        ),
    )


def _evidence(
    listing_id: str,
    field: str,
    *,
    observed_at: datetime,
    observation_id: str | None = None,
) -> AnalystEvidenceReference:
    suffix = listing_id.rsplit(":", 1)[-1]
    stamp = observed_at.isoformat().replace("+00:00", "Z")
    return AnalystEvidenceReference(
        observation_id=observation_id or f"obs:{suffix}:{field}",
        observed_at=stamp,
        retrieved_at=stamp,
        raw_snapshot_ids=("raw:rich",),
        source_field_paths=(f"$.games[{suffix}].{field}",),
        normalizer_name="YandexGameNormalizer",
        normalizer_version="4",
    )


def _observed(
    value: object,
    listing_id: str,
    field: str,
    *,
    observed_at: datetime,
    observation_id: str | None = None,
) -> AnalystResolvedValue:
    return AnalystResolvedValue(
        value=value,
        evidence=_evidence(
            listing_id,
            field,
            observed_at=observed_at,
            observation_id=observation_id,
        ),
    )


def _missing() -> AnalystResolvedValue:
    return AnalystResolvedValue(missing_reason="not_observed")


def _listing(
    listing_id: str,
    *,
    set_ids: tuple[str, ...],
    first_published_at: datetime | None,
    rating_count: int | float | None,
    rating_observed_at: datetime,
    rating_observation_id: str | None = None,
) -> AnalystListingRow:
    external = listing_id.rsplit(":", 1)[-1]
    publication = (
        _missing()
        if first_published_at is None
        else _observed(
            first_published_at.isoformat().replace("+00:00", "Z"),
            listing_id,
            "firstPublished",
            observed_at=rating_observed_at,
        )
    )
    rating = (
        _missing()
        if rating_count is None
        else _observed(
            rating_count,
            listing_id,
            "ratingCount",
            observed_at=rating_observed_at,
            observation_id=rating_observation_id,
        )
    )
    return AnalystListingRow(
        platform_listing_id=listing_id,
        platform="yandex_games",
        external_app_id=external,
        canonical_url=f"https://yandex.ru/games/app/{external}",
        comparable_set_ids=set_ids,
        title=_observed(
            f"Game {external}",
            listing_id,
            "title",
            observed_at=rating_observed_at,
        ),
        developer_id=_missing(),
        developer_name=_missing(),
        first_published_at=publication,
        app_version=_missing(),
        published_at=_missing(),
        languages=_missing(),
        supported_platforms=_missing(),
        orientation=_missing(),
        cloud_save=_missing(),
        leaderboards=_missing(),
        purchases_enabled=_missing(),
        has_products=_missing(),
        rewarded_ads=_missing(),
        fullscreen_ads=_missing(),
        sticky_ads=_missing(),
        yandex_games_rating=_missing(),
        player_rating=_missing(),
        rating_count=rating,
    )


def _snapshot(
    *,
    snapshot_id: str,
    created_at: datetime,
    set_members: tuple[tuple[str, tuple[str, ...]], ...],
    content_hash: str,
) -> AnalystSnapshotReport:
    comparables = tuple(
        AnalystComparableSetBinding(
            set_id=set_id,
            version=1,
            query_family_id=set_id.rsplit("--", 1)[-1],
            query_family_version=1,
            construction_method="yandex_search_union_v1",
            context_id="ctx:test",
            requested_page_limit=3,
            observed_from=created_at - timedelta(minutes=10),
            observed_to=created_at - timedelta(minutes=5),
            search_run_ids=(f"probe:{index}",),
            member_listing_ids=members,
        )
        for index, (set_id, members) in enumerate(set_members)
    )
    all_ids = tuple(dict.fromkeys(item for _, members in set_members for item in members))
    rich = AnalystRichMetadataBinding(
        source_id="yandex_public",
        request_key="catalogue.get_games",
        raw_snapshot_id="raw:rich",
        retrieved_at=created_at - timedelta(minutes=2),
        content_hash="1" * 64,
        parser_name="YandexGetGamesParser",
        parser_version="2",
        parsed_listing_ids=all_ids,
        relevant_listing_ids=all_ids,
    )
    payload = AnalystSnapshotPayload(
        spec_version="analyst-snapshot-v1",
        snapshot_id=snapshot_id,
        created_at=created_at,
        collection_parameters_status="provisional_uncalibrated",
        effective_context=ProbeContext(profile_age_days=0),
        search_page_limit=3,
        comparable_sets=comparables,
        feed_runs=(),
        rich_metadata=(rich,),
    )
    return AnalystSnapshotReport(
        **payload.model_dump(mode="python"),
        content_hash=content_hash,
    )


def _export(
    snapshot: AnalystSnapshotReport,
    listings: tuple[AnalystListingRow, ...],
    *,
    content_hash: str,
) -> AnalystMarketExportReport:
    first_set = snapshot.comparable_sets[0]
    first_id = first_set.member_listing_ids[0]
    membership = AnalystComparableMembership(
        set_id=first_set.set_id,
        set_version=1,
        member_ordinal=0,
        platform_listing_id=first_id,
        query_family_id=first_set.query_family_id,
        query_family_version=1,
        source_queries=("query",),
        probe_run_ids=(first_set.search_run_ids[0],),
        raw_snapshot_ids=("raw:search",),
        source_object_paths=("$.feed[0].items[0]",),
    )
    exposure = AnalystSearchExposure(
        set_id=first_set.set_id,
        set_version=1,
        platform_listing_id=first_id,
        query_text="query",
        probe_run_id=first_set.search_run_ids[0],
        page_index=0,
        raw_snapshot_id="raw:search",
        source_object_path="$.feed[0].items[0]",
        exposure_kind="organic_search",
    )
    payload = AnalystMarketExportPayload(
        spec_version="analyst-market-export-v1",
        snapshot_id=snapshot.snapshot_id,
        snapshot_content_hash=snapshot.content_hash,
        collection_parameters_status="provisional_uncalibrated",
        effective_context=snapshot.effective_context.model_dump(mode="json"),
        search_page_limit=3,
        rich_metadata_raw_snapshot_ids=("raw:rich",),
        listings=listings,
        comparable_memberships=(membership,),
        update_observations=(),
        search_supply=(),
        search_exposures=(exposure,),
        feed_exposures=(),
    )
    return AnalystMarketExportReport(
        **payload.model_dump(mode="python"),
        content_hash=content_hash,
    )


def _binding(
    *,
    role: Literal["current", "prior"],
    snapshot: AnalystSnapshotReport,
    market_export: AnalystMarketExportReport,
    artifact_hash: str,
    experiment_id: str = "traction-suite",
    run_id: str = "run-current",
) -> ExperimentArtifactBinding:
    return ExperimentArtifactBinding(
        role=role,
        artifact_sha256=artifact_hash,
        artifact_manifest_sha256="2" * 64,
        experiment_id=experiment_id,
        run_id=run_id,
        manifest_sha256="3" * 64,
        snapshot_id=snapshot.snapshot_id,
        snapshot_content_hash=snapshot.content_hash,
        snapshot_created_at=snapshot.created_at,
        market_export_content_hash=market_export.content_hash,
        market_features_content_hash="4" * 64,
    )


def _current_evidence(
    *,
    rating_counts: tuple[int | float | None, ...] = (50, 25, 100, 10),
) -> BoundExperimentEvidence:
    snapshot = _snapshot(
        snapshot_id="snapshot:current",
        created_at=_NOW,
        set_members=(
            (_SET_A, (_IDS[0], _IDS[1], _IDS[2])),
            (_SET_B, (_IDS[1], _IDS[3])),
        ),
        content_hash="a" * 64,
    )
    publications = (
        _NOW - timedelta(days=5),
        _NOW - timedelta(days=5),
        _NOW - timedelta(hours=12),
        None,
    )
    listings = tuple(
        _listing(
            listing_id,
            set_ids=(
                (_SET_A, _SET_B)
                if listing_id == _IDS[1]
                else ((_SET_A,) if listing_id in {_IDS[0], _IDS[2]} else (_SET_B,))
            ),
            first_published_at=published,
            rating_count=rating_count,
            rating_observed_at=_NOW - timedelta(minutes=2),
        )
        for listing_id, published, rating_count in zip(
            _IDS,
            publications,
            rating_counts,
            strict=True,
        )
    )
    market_export = _export(snapshot, listings, content_hash="b" * 64)
    return BoundExperimentEvidence(
        binding=_binding(
            role="current",
            snapshot=snapshot,
            market_export=market_export,
            artifact_hash="c" * 64,
        ),
        snapshot=snapshot,
        market_export=market_export,
    )


def _prior_evidence(
    *,
    artifact_hash: str,
    snapshot_time: datetime,
    rating_count: int,
    rating_observed_at: datetime,
    observation_id: str,
    run_id: str,
) -> BoundExperimentEvidence:
    snapshot = _snapshot(
        snapshot_id=f"snapshot:{run_id}",
        created_at=snapshot_time,
        set_members=(("prior-set", (_IDS[0],)),),
        content_hash=artifact_hash[0] * 64,
    )
    listing = _listing(
        _IDS[0],
        set_ids=("prior-set",),
        first_published_at=_NOW - timedelta(days=5),
        rating_count=rating_count,
        rating_observed_at=rating_observed_at,
        rating_observation_id=observation_id,
    )
    market_export = _export(snapshot, (listing,), content_hash=artifact_hash[1] * 64)
    return BoundExperimentEvidence(
        binding=_binding(
            role="prior",
            snapshot=snapshot,
            market_export=market_export,
            artifact_hash=artifact_hash,
            experiment_id=f"prior-{run_id}",
            run_id=run_id,
        ),
        snapshot=snapshot,
        market_export=market_export,
    )


def test_age_bucket_boundaries_are_frozen() -> None:
    assert _age_bucket(0.0) == "lt_7_days"
    assert _age_bucket(6.999) == "lt_7_days"
    assert _age_bucket(7.0) == "7_30_days"
    assert _age_bucket(30.999) == "7_30_days"
    assert _age_bucket(31.0) == "31_90_days"
    assert _age_bucket(90.999) == "31_90_days"
    assert _age_bucket(91.0) == "91_180_days"
    assert _age_bucket(180.999) == "91_180_days"
    assert _age_bucket(181.0) == "181_365_days"
    assert _age_bucket(365.999) == "181_365_days"
    assert _age_bucket(366.0) == "over_365_days"
    assert _age_bucket(None) is None
    with pytest.raises(ThesisIntelligenceError):
        _age_bucket(-0.01)


def test_lifetime_pace_never_floors_the_denominator() -> None:
    assert _lifetime_pace(None, 10) == (None, "missing_first_published")
    assert _lifetime_pace(0.5, 10) == (None, "too_young")
    assert _lifetime_pace(10.0, None) == (None, "missing_rating_count")
    assert _lifetime_pace(10.0, 50) == (5.0, "observed")


def test_suite_cohort_deduplicates_cross_thesis_members_and_preserves_order() -> None:
    report = build_traction_features(_suite(), current=_current_evidence())

    assert validate_traction_features(report) == report
    assert [item.thesis_id for item in report.theses] == ["alpha", "beta"]
    coverage = report.theses[0].rating_count_coverage
    assert coverage.member_count == 3
    assert coverage.observed_count == 3
    assert coverage.missing_count == 0
    assert coverage.coverage_ratio == pytest.approx(1.0)
    assert [row.platform_listing_id for row in report.theses[0].rows] == list(_IDS[:3])
    assert [row.platform_listing_id for row in report.theses[1].rows] == [_IDS[1], _IDS[3]]

    first, second, third = report.theses[0].rows
    assert first.listing_age_days == pytest.approx(5.0)
    assert first.age_bucket == "lt_7_days"
    assert first.lifetime_ratings_per_day == pytest.approx(10.0)
    assert first.suite_age_bucket_member_count == 3
    assert first.suite_age_bucket_pace_observed_count == 2
    assert first.suite_age_bucket_pace_coverage_ratio == pytest.approx(2 / 3)
    assert first.suite_age_bucket_percentile == pytest.approx(1.0)

    assert second.suite_age_bucket_member_count == 3
    assert second.suite_age_bucket_percentile == pytest.approx(0.5)
    assert report.theses[1].rows[0].suite_age_bucket_percentile == pytest.approx(0.5)

    assert third.lifetime_pace_status == "too_young"
    assert third.lifetime_ratings_per_day is None
    assert third.suite_age_bucket_percentile is None

    missing_age = report.theses[1].rows[1]
    assert missing_age.lifetime_pace_status == "missing_first_published"
    assert missing_age.age_bucket is None
    assert missing_age.suite_age_bucket_member_count is None

    assert all(
        row.longitudinal.status == "no_prior_observation"
        for thesis in report.theses
        for row in thesis.rows
        if row.rating_count is not None
    )


def test_latest_eligible_prior_observation_drives_delta_and_history_order_is_canonical() -> None:
    older = _prior_evidence(
        artifact_hash="d" * 64,
        snapshot_time=_NOW - timedelta(days=5),
        rating_count=10,
        rating_observed_at=_NOW - timedelta(days=4),
        observation_id="obs:older",
        run_id="older",
    )
    newer = _prior_evidence(
        artifact_hash="e" * 64,
        snapshot_time=_NOW - timedelta(days=3),
        rating_count=30,
        rating_observed_at=_NOW - timedelta(days=2),
        observation_id="obs:newer",
        run_id="newer",
    )

    report = build_traction_features(
        _suite(),
        current=_current_evidence(),
        priors=(newer, older),
    )

    delta = report.theses[0].rows[0].longitudinal
    assert [item.artifact_sha256 for item in report.prior_experiments] == [
        older.binding.artifact_sha256,
        newer.binding.artifact_sha256,
    ]
    assert delta.status == "observed"
    assert delta.prior_artifact_sha256 == newer.binding.artifact_sha256
    assert delta.previous_rating_count == 30
    assert delta.current_rating_count == 50
    expected_interval = (
        (_NOW - timedelta(minutes=2)) - (_NOW - timedelta(days=2))
    ).total_seconds() / 86_400
    assert delta.delta_interval_days == pytest.approx(expected_interval)
    assert delta.rating_count_delta == 20
    assert delta.observed_rating_delta_per_day == pytest.approx(20 / expected_interval)


def test_negative_revision_and_short_interval_are_preserved() -> None:
    negative = _prior_evidence(
        artifact_hash="f" * 64,
        snapshot_time=_NOW - timedelta(days=2),
        rating_count=80,
        rating_observed_at=_NOW - timedelta(days=1, minutes=2),
        observation_id="obs:negative",
        run_id="negative",
    )
    negative_report = build_traction_features(
        _suite(),
        current=_current_evidence(),
        priors=(negative,),
    )
    negative_delta = negative_report.theses[0].rows[0].longitudinal
    assert negative_delta.status == "negative_revision"
    assert negative_delta.rating_count_delta == -30
    assert negative_delta.observed_rating_delta_per_day == pytest.approx(-30.0)

    short = _prior_evidence(
        artifact_hash="9" * 64,
        snapshot_time=_NOW - timedelta(hours=5),
        rating_count=40,
        rating_observed_at=_NOW - timedelta(hours=6),
        observation_id="obs:short",
        run_id="short",
    )
    short_report = build_traction_features(
        _suite(),
        current=_current_evidence(),
        priors=(short,),
    )
    short_delta = short_report.theses[0].rows[0].longitudinal
    assert short_delta.status == "interval_too_short"
    assert short_delta.rating_count_delta == 10
    assert short_delta.observed_rating_delta_per_day is None


def test_equal_timestamp_prior_conflict_fails_closed() -> None:
    observed_at = _NOW - timedelta(days=2)
    left = _prior_evidence(
        artifact_hash="5" * 64,
        snapshot_time=_NOW - timedelta(days=3),
        rating_count=20,
        rating_observed_at=observed_at,
        observation_id="obs:left",
        run_id="left",
    )
    right = _prior_evidence(
        artifact_hash="6" * 64,
        snapshot_time=_NOW - timedelta(days=3),
        rating_count=21,
        rating_observed_at=observed_at,
        observation_id="obs:right",
        run_id="right",
    )
    with pytest.raises(ThesisIntelligenceError, match="conflicting prior rating_count"):
        build_traction_features(
            _suite(),
            current=_current_evidence(),
            priors=(left, right),
        )


def test_equal_timestamp_equal_value_uses_stable_artifact_observation_tiebreak() -> None:
    observed_at = _NOW - timedelta(days=2)
    left = _prior_evidence(
        artifact_hash="7" * 64,
        snapshot_time=_NOW - timedelta(days=3),
        rating_count=20,
        rating_observed_at=observed_at,
        observation_id="obs:z",
        run_id="left-equal",
    )
    right = _prior_evidence(
        artifact_hash="8" * 64,
        snapshot_time=_NOW - timedelta(days=3),
        rating_count=20,
        rating_observed_at=observed_at,
        observation_id="obs:a",
        run_id="right-equal",
    )
    report = build_traction_features(
        _suite(),
        current=_current_evidence(),
        priors=(right, left),
    )
    delta = report.theses[0].rows[0].longitudinal
    assert delta.prior_artifact_sha256 == left.binding.artifact_sha256
    assert delta.previous_observation_id == "obs:z"


def test_future_or_equal_prior_observations_are_ineligible() -> None:
    current_observed = _NOW - timedelta(minutes=2)
    prior = _prior_evidence(
        artifact_hash="0" * 64,
        snapshot_time=_NOW - timedelta(minutes=1),
        rating_count=999,
        rating_observed_at=current_observed,
        observation_id="obs:equal",
        run_id="equal",
    )
    report = build_traction_features(
        _suite(),
        current=_current_evidence(),
        priors=(prior,),
    )
    assert report.theses[0].rows[0].longitudinal.status == "no_prior_observation"


def test_missing_current_rating_never_becomes_zero_velocity() -> None:
    report = build_traction_features(
        _suite(),
        current=_current_evidence(rating_counts=(None, 25, 100, 10)),
    )
    coverage = report.theses[0].rating_count_coverage
    assert coverage.observed_count == 2
    assert coverage.missing_count == 1
    assert coverage.coverage_ratio == pytest.approx(2 / 3)
    row = report.theses[0].rows[0]
    assert row.rating_count is None
    assert row.lifetime_pace_status == "missing_rating_count"
    assert row.longitudinal.status == "current_missing"
    assert row.longitudinal.observed_rating_delta_per_day is None


def test_non_integral_rating_count_fails_closed() -> None:
    with pytest.raises(ThesisIntelligenceError, match="finite non-negative integer"):
        build_traction_features(
            _suite(),
            current=_current_evidence(rating_counts=(10.5, 25, 100, 10)),
        )


def test_report_hash_tampering_is_rejected() -> None:
    report = build_traction_features(_suite(), current=_current_evidence())
    tampered = ThesisTractionFeaturesReport.model_validate(
        {**report.model_dump(mode="python"), "content_hash": "f" * 64}
    )
    with pytest.raises(ThesisIntelligenceError, match="content_hash mismatch"):
        validate_traction_features(tampered)
