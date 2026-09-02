from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel

from yandex_analytics_reaper.analyst import (
    AnalystComparableMembership,
    AnalystComparableSetBinding,
    AnalystListingRow,
    AnalystMarketExportPayload,
    AnalystMarketExportReport,
    AnalystResolvedValue,
    AnalystRichMetadataBinding,
    AnalystSearchExposure,
    AnalystSemanticCorpus,
    AnalystSemanticDimensionResult,
    AnalystSemanticEnrichmentPayload,
    AnalystSemanticEnrichmentReport,
    AnalystSemanticEvidenceSnippet,
    AnalystSemanticListingRow,
    AnalystSemanticSourceReference,
    AnalystSnapshotPayload,
    AnalystSnapshotReport,
)
from yandex_analytics_reaper.domain import ProbeContext
from yandex_analytics_reaper.thesis_directness import (
    AnalystDirectnessReviewReport,
    DirectnessReviewDecisionV1,
    build_directness_review,
)
from yandex_analytics_reaper.thesis_intelligence import (
    ExperimentArtifactBinding,
    ThesisAnomalyPolicy,
    ThesisDeclaration,
    ThesisSemanticDeclaration,
    ThesisSuiteContext,
    ThesisSuiteDeclaration,
    canonical_model_hash,
    compile_thesis_suite,
)
from yandex_analytics_reaper.thesis_traction import (
    BoundExperimentEvidence,
    LongitudinalRatingDeltaV1,
    ThesisFieldCoverage,
    ThesisTractionFeaturesPayload,
    ThesisTractionFeaturesReport,
    ThesisTractionRow,
    ThesisTractionSet,
)

BASE = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)
HEADPHONES = ("yandex_games:1", "yandex_games:2")
DIGICAM = ("yandex_games:3", "yandex_games:4")
ALL_IDS = HEADPHONES + DIGICAM


def _hash_model(model: BaseModel) -> str:
    encoded = json.dumps(
        model.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def make_suite() -> ThesisSuiteDeclaration:
    return ThesisSuiteDeclaration(
        suite_id="comparison-suite",
        suite_version=1,
        context=ThesisSuiteContext(
            pages=2,
            session_profile="clean_anonymous",
            lang="ru",
            device="desktop",
            platform="web",
        ),
        anomaly_policy=ThesisAnomalyPolicy(min_rating_count=50),
        theses=(
            ThesisDeclaration(
                thesis_id="headphones",
                thesis_version=1,
                label="Custom Headphones",
                queries=("custom headphones", "decorate headphones"),
                semantic=ThesisSemanticDeclaration(
                    theme_terms=("headphone",),
                    mechanic_terms=("decorat",),
                ),
            ),
            ThesisDeclaration(
                thesis_id="digicam",
                thesis_version=1,
                label="Custom Digicam",
                queries=("custom digicam", "decorate camera"),
                semantic=ThesisSemanticDeclaration(
                    theme_terms=("camera",),
                    mechanic_terms=("decorat",),
                ),
            ),
        ),
    )


def _comparable(
    suite: ThesisSuiteDeclaration,
    thesis_id: str,
    member_ids: tuple[str, ...],
) -> AnalystComparableSetBinding:
    return AnalystComparableSetBinding(
        set_id=f"{suite.suite_id}--{thesis_id}",
        version=1,
        query_family_id=thesis_id,
        query_family_version=1,
        construction_method="yandex_search_union_v1",
        context_id="ctx:comparison",
        requested_page_limit=2,
        observed_from=BASE - timedelta(minutes=10),
        observed_to=BASE - timedelta(minutes=5),
        search_run_ids=(f"run:{thesis_id}:1", f"run:{thesis_id}:2"),
        member_listing_ids=member_ids,
    )


def make_snapshot(suite: ThesisSuiteDeclaration) -> AnalystSnapshotReport:
    rich = AnalystRichMetadataBinding(
        source_id="yandex_public",
        request_key="catalogue.get_games",
        raw_snapshot_id="raw:rich",
        retrieved_at=BASE - timedelta(minutes=2),
        content_hash="a" * 64,
        parser_name="YandexGetGamesParser",
        parser_version="2",
        parsed_listing_ids=ALL_IDS,
        relevant_listing_ids=ALL_IDS,
    )
    payload = AnalystSnapshotPayload(
        spec_version="analyst-snapshot-v1",
        snapshot_id="snapshot:comparison",
        created_at=BASE,
        collection_parameters_status="provisional_uncalibrated",
        effective_context=ProbeContext(),
        search_page_limit=2,
        comparable_sets=(
            _comparable(suite, "headphones", HEADPHONES),
            _comparable(suite, "digicam", DIGICAM),
        ),
        feed_runs=(),
        rich_metadata=(rich,),
    )
    return AnalystSnapshotReport(
        **payload.model_dump(mode="python"),
        content_hash=_hash_model(payload),
    )


def _missing() -> AnalystResolvedValue:
    return AnalystResolvedValue(missing_reason="not_observed")


def _listing(listing_id: str, set_id: str) -> AnalystListingRow:
    external = listing_id.rsplit(":", 1)[-1]
    missing = _missing
    return AnalystListingRow(
        platform_listing_id=listing_id,
        platform="yandex_games",
        external_app_id=external,
        canonical_url=f"https://yandex.ru/games/app/{external}",
        comparable_set_ids=(set_id,),
        title=missing(), developer_id=missing(), developer_name=missing(),
        first_published_at=missing(), app_version=missing(), published_at=missing(),
        languages=missing(), supported_platforms=missing(), orientation=missing(),
        cloud_save=missing(), leaderboards=missing(), purchases_enabled=missing(),
        has_products=missing(), rewarded_ads=missing(), fullscreen_ads=missing(),
        sticky_ads=missing(), yandex_games_rating=missing(), player_rating=missing(),
        rating_count=missing(),
    )


def _membership(
    suite: ThesisSuiteDeclaration,
    thesis_id: str,
    index: int,
    listing_id: str,
    source_queries: tuple[str, ...],
) -> AnalystComparableMembership:
    return AnalystComparableMembership(
        set_id=f"{suite.suite_id}--{thesis_id}",
        set_version=1,
        member_ordinal=index,
        platform_listing_id=listing_id,
        query_family_id=thesis_id,
        query_family_version=1,
        source_queries=source_queries,
        probe_run_ids=tuple(
            f"run:{thesis_id}:{position}" for position in range(len(source_queries))
        ),
        raw_snapshot_ids=(f"raw:{thesis_id}:{index}",),
        source_object_paths=(f"$.feed[0].items[{index}]",),
    )


def make_market_export(
    suite: ThesisSuiteDeclaration,
    snapshot: AnalystSnapshotReport,
) -> AnalystMarketExportReport:
    memberships = (
        _membership(suite, "headphones", 0, HEADPHONES[0], ("custom headphones",)),
        _membership(suite, "headphones", 1, HEADPHONES[1], ("decorate headphones",)),
        _membership(
            suite, "digicam", 0, DIGICAM[0], ("custom digicam", "decorate camera")
        ),
        _membership(suite, "digicam", 1, DIGICAM[1], ("decorate camera",)),
    )
    set_by_id = {
        listing_id: (
            f"{suite.suite_id}--headphones"
            if listing_id in HEADPHONES
            else f"{suite.suite_id}--digicam"
        )
        for listing_id in ALL_IDS
    }
    payload = AnalystMarketExportPayload(
        spec_version="analyst-market-export-v1",
        snapshot_id=snapshot.snapshot_id,
        snapshot_content_hash=snapshot.content_hash,
        collection_parameters_status="provisional_uncalibrated",
        effective_context={},
        search_page_limit=2,
        rich_metadata_raw_snapshot_ids=("raw:rich",),
        listings=tuple(_listing(item, set_by_id[item]) for item in ALL_IDS),
        comparable_memberships=memberships,
        update_observations=(),
        search_supply=(),
        search_exposures=(
            AnalystSearchExposure(
                set_id=f"{suite.suite_id}--headphones",
                set_version=1,
                platform_listing_id=HEADPHONES[0],
                query_text="custom headphones",
                probe_run_id="run:headphones:1",
                page_index=0,
                raw_snapshot_id="raw:headphones:0",
                source_object_path="$.feed[0].items[0]",
                exposure_kind="organic_search",
            ),
        ),
        feed_exposures=(),
    )
    return AnalystMarketExportReport(
        **payload.model_dump(mode="python"),
        content_hash=_hash_model(payload),
    )


def make_current(
    suite: ThesisSuiteDeclaration,
    snapshot: AnalystSnapshotReport,
    market_export: AnalystMarketExportReport,
) -> BoundExperimentEvidence:
    binding = ExperimentArtifactBinding(
        role="current",
        artifact_sha256="1" * 64,
        artifact_manifest_sha256="2" * 64,
        experiment_id=suite.suite_id,
        run_id="20260902T120000Z",
        manifest_sha256="3" * 64,
        snapshot_id=snapshot.snapshot_id,
        snapshot_content_hash=snapshot.content_hash,
        snapshot_created_at=snapshot.created_at,
        market_export_content_hash=market_export.content_hash,
        market_features_content_hash="4" * 64,
        verifier_status="pass",
    )
    return BoundExperimentEvidence(
        binding=binding,
        snapshot=snapshot,
        market_export=market_export,
    )


def _longitudinal(listing_id: str, rating_count: int) -> LongitudinalRatingDeltaV1:
    return LongitudinalRatingDeltaV1(
        status="no_prior_observation",
        current_observation_id=f"rating:{listing_id}",
        current_observed_at=BASE,
        current_rating_count=rating_count,
    )


def _traction_row(
    listing_id: str,
    *,
    title: str,
    rating_count: int,
    age_days: float | None,
) -> ThesisTractionRow:
    common = dict(
        platform_listing_id=listing_id,
        external_app_id=listing_id.rsplit(":", 1)[-1],
        canonical_url=f"https://yandex.ru/games/app/{listing_id.rsplit(':', 1)[-1]}",
        title=title,
        rating_count=rating_count,
        rating_count_observation_id=f"rating:{listing_id}",
        rating_count_observed_at=BASE,
        longitudinal=_longitudinal(listing_id, rating_count),
    )
    if age_days is None:
        return ThesisTractionRow(
            **common,
            first_published_at=None,
            first_published_observation_id=None,
            listing_age_days=None,
            age_bucket=None,
            lifetime_ratings_per_day=None,
            lifetime_pace_status="missing_first_published",
            suite_age_bucket_member_count=None,
            suite_age_bucket_pace_observed_count=None,
            suite_age_bucket_pace_coverage_ratio=None,
            suite_age_bucket_percentile=None,
        )
    bucket = (
        "lt_7_days" if age_days < 7 else
        "7_30_days" if age_days < 31 else
        "31_90_days" if age_days < 91 else
        "91_180_days" if age_days < 181 else
        "181_365_days" if age_days < 366 else
        "over_365_days"
    )
    return ThesisTractionRow(
        **common,
        first_published_at=BASE - timedelta(days=age_days),
        first_published_observation_id=f"published:{listing_id}",
        listing_age_days=age_days,
        age_bucket=bucket,
        lifetime_ratings_per_day=rating_count / age_days,
        lifetime_pace_status="observed",
        suite_age_bucket_member_count=1,
        suite_age_bucket_pace_observed_count=1,
        suite_age_bucket_pace_coverage_ratio=1.0,
        suite_age_bucket_percentile=1.0,
    )


def make_traction(
    suite: ThesisSuiteDeclaration,
    current: BoundExperimentEvidence,
) -> ThesisTractionFeaturesReport:
    headphones = (
        _traction_row(HEADPHONES[0], title="Headphone One", rating_count=100, age_days=10),
        _traction_row(HEADPHONES[1], title="Headphone Two", rating_count=50, age_days=200),
    )
    digicam = (
        _traction_row(DIGICAM[0], title="Camera One", rating_count=200, age_days=50),
        _traction_row(DIGICAM[1], title="Camera Two", rating_count=200, age_days=None),
    )
    coverage = ThesisFieldCoverage(
        member_count=2, observed_count=2, missing_count=0, coverage_ratio=1.0
    )
    payload = ThesisTractionFeaturesPayload(
        suite_id=suite.suite_id,
        suite_version=suite.suite_version,
        suite_content_hash=canonical_model_hash(suite),
        reference_time=BASE,
        current_experiment=current.binding,
        prior_experiments=(),
        theses=(
            ThesisTractionSet(
                thesis_id="headphones",
                thesis_version=1,
                comparable_set_id=f"{suite.suite_id}--headphones",
                comparable_set_version=1,
                rating_count_coverage=coverage,
                rows=headphones,
            ),
            ThesisTractionSet(
                thesis_id="digicam",
                thesis_version=1,
                comparable_set_id=f"{suite.suite_id}--digicam",
                comparable_set_version=1,
                rating_count_coverage=coverage,
                rows=digicam,
            ),
        ),
    )
    return ThesisTractionFeaturesReport(
        **payload.model_dump(mode="python"),
        content_hash=canonical_model_hash(payload),
    )


def _match(field: str, term: str) -> AnalystSemanticDimensionResult:
    return AnalystSemanticDimensionResult(
        status="match",
        matched_terms=(term,),
        evidence_snippets=(
            AnalystSemanticEvidenceSnippet(field=field, term=term, snippet=f"...{term}..."),
        ),
    )


def make_semantic(
    suite: ThesisSuiteDeclaration,
    snapshot: AnalystSnapshotReport,
    *,
    thesis_id: str,
    member_ids: tuple[str, ...],
    directness: tuple[str, ...],
) -> AnalystSemanticEnrichmentReport:
    compiled = {item.thesis_id: item for item in compile_thesis_suite(suite).semantic_theses}
    rows = []
    for index, (listing_id, label) in enumerate(zip(member_ids, directness, strict=True)):
        rows.append(
            AnalystSemanticListingRow(
                platform_listing_id=listing_id,
                external_app_id=listing_id.rsplit(":", 1)[-1],
                canonical_url=f"https://yandex.ru/games/app/{listing_id.rsplit(':', 1)[-1]}",
                comparable_set_ids=(f"{suite.suite_id}--{thesis_id}",),
                source=AnalystSemanticSourceReference(
                    raw_snapshot_id=f"raw:semantic:{thesis_id}:{index}",
                    retrieved_at=BASE.isoformat().replace("+00:00", "Z"),
                    source_object_path=f"$.games[{index}]",
                    parser_name="YandexGetGamesParser",
                    parser_version="2",
                ),
                corpus=AnalystSemanticCorpus(title=f"Semantic {listing_id}"),
                theme_match=_match("title", "headphone" if thesis_id == "headphones" else "camera"),
                mechanic_match=(
                    _match("description", "decorat")
                    if label == "direct_candidate"
                    else AnalystSemanticDimensionResult(status="no_match")
                ),
                reward_grammar_match=AnalystSemanticDimensionResult(status="not_configured"),
                directness=label,
            )
        )
    payload = AnalystSemanticEnrichmentPayload(
        spec_version="analyst-semantic-enrichment-v1",
        classifier_version="lexical-directness-v1",
        snapshot_id=snapshot.snapshot_id,
        snapshot_content_hash=snapshot.content_hash,
        thesis=compiled[thesis_id],
        listings=tuple(rows),
    )
    return AnalystSemanticEnrichmentReport(
        **payload.model_dump(mode="python"),
        content_hash=_hash_model(payload),
    )


def make_fixture() -> tuple[
    ThesisSuiteDeclaration,
    BoundExperimentEvidence,
    ThesisTractionFeaturesReport,
    tuple[AnalystSemanticEnrichmentReport, ...],
    tuple[AnalystDirectnessReviewReport, ...],
]:
    suite = make_suite()
    snapshot = make_snapshot(suite)
    market_export = make_market_export(suite, snapshot)
    current = make_current(suite, snapshot, market_export)
    traction = make_traction(suite, current)
    semantics = (
        make_semantic(
            suite,
            snapshot,
            thesis_id="headphones",
            member_ids=HEADPHONES,
            directness=("direct_candidate", "adjacent_candidate"),
        ),
        make_semantic(
            suite,
            snapshot,
            thesis_id="digicam",
            member_ids=DIGICAM,
            directness=("direct_candidate", "direct_candidate"),
        ),
    )
    reviews = (
        build_directness_review(
            suite,
            semantics[0],
            decisions=(
                DirectnessReviewDecisionV1(
                    platform_listing_id=HEADPHONES[0],
                    analyst_verdict="confirmed_direct",
                    reason_code="direct_mechanic_and_theme",
                    reviewed_at=BASE,
                ),
            ),
        ),
        build_directness_review(
            suite,
            semantics[1],
            decisions=tuple(
                DirectnessReviewDecisionV1(
                    platform_listing_id=listing_id,
                    analyst_verdict="confirmed_direct",
                    reason_code="direct_mechanic_and_theme",
                    reviewed_at=BASE + timedelta(minutes=index + 1),
                )
                for index, listing_id in enumerate(DIGICAM)
            ),
        ),
    )
    return suite, current, traction, semantics, reviews
