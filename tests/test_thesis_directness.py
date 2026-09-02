from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import BaseModel, ValidationError

from yandex_analytics_reaper.analyst import (
    AnalystComparableMembership,
    AnalystFeedExposure,
    AnalystListingRow,
    AnalystMarketExportPayload,
    AnalystMarketExportReport,
    AnalystResolvedValue,
    AnalystSearchExposure,
    AnalystSemanticCorpus,
    AnalystSemanticDimensionResult,
    AnalystSemanticEnrichmentPayload,
    AnalystSemanticEnrichmentReport,
    AnalystSemanticEvidenceSnippet,
    AnalystSemanticListingRow,
    AnalystSemanticSourceReference,
)
from yandex_analytics_reaper.thesis_directness import (
    AnalystDirectnessReviewPayload,
    AnalystDirectnessReviewReport,
    DirectnessReviewDecisionV1,
    build_competitor_quality,
    build_directness_review,
    validate_directness_review,
)
from yandex_analytics_reaper.thesis_intelligence import (
    ThesisDeclaration,
    ThesisIntelligenceError,
    ThesisSemanticDeclaration,
    ThesisSuiteContext,
    ThesisSuiteDeclaration,
    canonical_model_hash,
    compile_thesis_suite,
)

_BASE = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)
_SET_ID = "quality-suite--headphones"
_IDS = tuple(f"yandex_games:{value}" for value in range(1, 5))


def _hash_model(model: BaseModel) -> str:
    encoded = json.dumps(
        model.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _suite() -> ThesisSuiteDeclaration:
    return ThesisSuiteDeclaration(
        suite_id="quality-suite",
        suite_version=1,
        context=ThesisSuiteContext(
            pages=2,
            session_profile="clean_anonymous",
            lang="ru",
            device="desktop",
            platform="web",
        ),
        theses=(
            ThesisDeclaration(
                thesis_id="headphones",
                thesis_version=1,
                label="Custom Headphones",
                queries=("custom headphones", "decorate headphones"),
                semantic=ThesisSemanticDeclaration(
                    theme_terms=("headphone",),
                    mechanic_terms=("decorat",),
                    reward_grammar_terms=("charm",),
                ),
            ),
        ),
    )


def _match(field: str, term: str) -> AnalystSemanticDimensionResult:
    return AnalystSemanticDimensionResult(
        status="match",
        matched_terms=(term,),
        evidence_snippets=(
            AnalystSemanticEvidenceSnippet(field=field, term=term, snippet=f"...{term}..."),
        ),
    )


def _no_match() -> AnalystSemanticDimensionResult:
    return AnalystSemanticDimensionResult(status="no_match")


def _unknown() -> AnalystSemanticDimensionResult:
    return AnalystSemanticDimensionResult(status="unknown")


def _source(index: int) -> AnalystSemanticSourceReference:
    return AnalystSemanticSourceReference(
        raw_snapshot_id=f"raw:{index}",
        retrieved_at=_BASE.isoformat().replace("+00:00", "Z"),
        source_object_path=f"$.games[{index}]",
        parser_name="YandexGetGamesParser",
        parser_version="2",
    )


def _semantic(*, direct_count: int = 2) -> AnalystSemanticEnrichmentReport:
    suite = _suite()
    thesis = compile_thesis_suite(suite).semantic_theses[0]
    rows: list[AnalystSemanticListingRow] = []
    for index, listing_id in enumerate(_IDS):
        source = None if index == 3 else _source(index)
        if index < direct_count:
            directness = "direct_candidate"
            theme = _match("title", "headphone")
            mechanic = _match("description", "decorat")
            reward = _no_match()
        elif index == 2:
            directness = "adjacent_candidate"
            theme = _match("title", "headphone")
            mechanic = _no_match()
            reward = _no_match()
        else:
            directness = "insufficient_evidence"
            theme = _unknown()
            mechanic = _unknown()
            reward = _unknown()
        rows.append(
            AnalystSemanticListingRow(
                platform_listing_id=listing_id,
                external_app_id=str(index + 1),
                canonical_url=f"https://yandex.ru/games/app/{index + 1}",
                comparable_set_ids=(_SET_ID,),
                source=source,
                corpus=AnalystSemanticCorpus(
                    title=None if source is None else f"Game {index + 1}",
                    description=None if source is None else "decorate headphones",
                ),
                theme_match=theme,
                mechanic_match=mechanic,
                reward_grammar_match=reward,
                directness=directness,
            )
        )
    payload = AnalystSemanticEnrichmentPayload(
        spec_version="analyst-semantic-enrichment-v1",
        classifier_version="lexical-directness-v1",
        snapshot_id="snapshot:quality",
        snapshot_content_hash="a" * 64,
        thesis=thesis,
        listings=tuple(rows),
    )
    return AnalystSemanticEnrichmentReport(
        **payload.model_dump(mode="python"),
        content_hash=_hash_model(payload),
    )


def _missing() -> AnalystResolvedValue:
    return AnalystResolvedValue(missing_reason="not_observed")


def _listing(listing_id: str) -> AnalystListingRow:
    external = listing_id.rsplit(":", 1)[-1]
    return AnalystListingRow(
        platform_listing_id=listing_id,
        platform="yandex_games",
        external_app_id=external,
        canonical_url=f"https://yandex.ru/games/app/{external}",
        comparable_set_ids=(_SET_ID,),
        title=_missing(),
        developer_id=_missing(),
        developer_name=_missing(),
        first_published_at=_missing(),
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
        rating_count=_missing(),
    )


def _membership(index: int, source_queries: tuple[str, ...]) -> AnalystComparableMembership:
    return AnalystComparableMembership(
        set_id=_SET_ID,
        set_version=1,
        member_ordinal=index,
        platform_listing_id=_IDS[index],
        query_family_id="headphones",
        query_family_version=1,
        source_queries=source_queries,
        probe_run_ids=tuple(f"run:{query}" for query in source_queries),
        raw_snapshot_ids=(f"raw:search:{index}",),
        source_object_paths=(f"$.feed[0].items[{index}]",),
    )


def _market_export() -> AnalystMarketExportReport:
    memberships = (
        _membership(0, ("custom headphones",)),
        _membership(1, ("custom headphones", "decorate headphones")),
        _membership(2, ("decorate headphones",)),
        _membership(3, ("decorate headphones",)),
    )
    payload = AnalystMarketExportPayload(
        spec_version="analyst-market-export-v1",
        snapshot_id="snapshot:quality",
        snapshot_content_hash="a" * 64,
        collection_parameters_status="provisional_uncalibrated",
        effective_context={},
        search_page_limit=2,
        rich_metadata_raw_snapshot_ids=("raw:rich",),
        listings=tuple(_listing(listing_id) for listing_id in _IDS),
        comparable_memberships=memberships,
        update_observations=(),
        search_supply=(),
        search_exposures=(
            AnalystSearchExposure(
                set_id=_SET_ID,
                set_version=1,
                platform_listing_id=_IDS[0],
                query_text="custom headphones",
                probe_run_id="run:custom headphones",
                page_index=0,
                raw_snapshot_id="raw:search:0",
                source_object_path="$.feed[0].items[0]",
                exposure_kind="organic_search",
            ),
        ),
        feed_exposures=tuple[AnalystFeedExposure, ...](),
    )
    return AnalystMarketExportReport(
        **payload.model_dump(mode="python"),
        content_hash=_hash_model(payload),
    )


def _decision(
    listing_id: str,
    verdict: str,
    reason: str,
    *,
    note: str | None = None,
    minutes: int = 0,
) -> DirectnessReviewDecisionV1:
    return DirectnessReviewDecisionV1(
        platform_listing_id=listing_id,
        analyst_verdict=verdict,
        reason_code=reason,
        note=note,
        reviewed_at=_BASE + timedelta(minutes=minutes),
    )


def test_review_canonicalizes_to_semantic_order_and_quality_is_transparent() -> None:
    suite = _suite()
    semantic = _semantic()
    review = build_directness_review(
        suite,
        semantic,
        decisions=(
            _decision(_IDS[1], "not_direct", "mechanic_mismatch", minutes=2),
            _decision(_IDS[0], "confirmed_direct", "direct_mechanic_and_theme", minutes=1),
        ),
    )

    assert [item.platform_listing_id for item in review.rows] == [_IDS[0], _IDS[1]]
    quality = build_competitor_quality(suite, semantic, _market_export(), review=review)

    assert quality.raw_search_union_member_count == 4
    assert quality.semantic_source_observed_count == 3
    assert quality.semantic_source_missing_count == 1
    assert quality.semantic_source_coverage_ratio == pytest.approx(0.75)
    assert quality.semantic_direct_candidate_count == 2
    assert quality.semantic_adjacent_candidate_count == 1
    assert quality.semantic_insufficient_evidence_count == 1
    assert quality.semantic_direct_candidate_share == pytest.approx(0.5)
    assert quality.reviewed_direct_candidate_count == 2
    assert quality.confirmed_direct_count == 1
    assert quality.rejected_direct_false_positive_count == 1
    assert quality.manual_direct_review_coverage_ratio == pytest.approx(1.0)
    assert quality.direct_review_state == "all_reviewed_with_confirmed"

    surface = quality.query_surface
    assert surface.query_count == 2
    assert surface.members_seen_by_multiple_queries == 1
    assert surface.multi_query_member_share == pytest.approx(0.25)
    assert [(item.organic_member_count, item.unique_contribution_count) for item in surface.queries] == [
        (2, 1),
        (3, 2),
    ]
    assert surface.pairwise[0].intersection_count == 1
    assert surface.pairwise[0].union_count == 4
    assert surface.pairwise[0].jaccard == pytest.approx(0.25)
    assert surface.mean_pairwise_jaccard == pytest.approx(0.25)
    assert surface.median_pairwise_jaccard == pytest.approx(0.25)


def test_partial_and_zero_direct_review_states_remain_bounded() -> None:
    suite = _suite()
    semantic = _semantic()
    partial = build_directness_review(
        suite,
        semantic,
        decisions=(
            _decision(_IDS[0], "unresolved", "insufficient_context"),
        ),
    )
    partial_quality = build_competitor_quality(
        suite,
        semantic,
        _market_export(),
        review=partial,
    )
    assert partial_quality.direct_review_state == "partially_reviewed"
    assert partial_quality.manual_direct_review_coverage_ratio == pytest.approx(0.5)
    assert partial_quality.unresolved_direct_candidate_count == 1

    no_direct = _semantic(direct_count=0)
    zero_quality = build_competitor_quality(suite, no_direct, _market_export())
    assert zero_quality.semantic_direct_candidate_count == 0
    assert zero_quality.manual_direct_review_coverage_ratio is None
    assert zero_quality.direct_review_state == "no_direct_candidates"


def test_review_rejects_non_direct_rows_invalid_reason_pairs_and_unexplained_other() -> None:
    suite = _suite()
    semantic = _semantic()
    with pytest.raises(ThesisIntelligenceError, match="only classify semantic direct candidates"):
        build_directness_review(
            suite,
            semantic,
            decisions=(
                _decision(_IDS[2], "not_direct", "theme_mismatch"),
            ),
        )

    with pytest.raises(ValidationError, match="verdict/reason_code"):
        _decision(_IDS[0], "confirmed_direct", "theme_mismatch")

    with pytest.raises(ValidationError, match="requires a review note"):
        _decision(_IDS[0], "confirmed_direct", "other")


def test_review_validation_rejects_reordered_rows_even_with_recomputed_hash() -> None:
    suite = _suite()
    semantic = _semantic()
    review = build_directness_review(
        suite,
        semantic,
        decisions=(
            _decision(_IDS[0], "confirmed_direct", "direct_mechanic_and_theme"),
            _decision(_IDS[1], "adjacent", "theme_incidental"),
        ),
    )
    payload = AnalystDirectnessReviewPayload.model_validate(
        {**review.model_dump(exclude={"content_hash"}), "rows": tuple(reversed(review.rows))}
    )
    tampered = AnalystDirectnessReviewReport(
        **payload.model_dump(mode="python"),
        content_hash=canonical_model_hash(payload),
    )
    with pytest.raises(ThesisIntelligenceError, match="semantic listing order"):
        validate_directness_review(tampered, suite=suite, semantic_report=semantic)


def test_quality_rejects_snapshot_and_query_family_mismatches() -> None:
    suite = _suite()
    semantic = _semantic()
    export = _market_export()
    bad_payload = AnalystMarketExportPayload.model_validate(
        {**export.model_dump(exclude={"content_hash"}), "snapshot_content_hash": "b" * 64}
    )
    bad_export = AnalystMarketExportReport(
        **bad_payload.model_dump(mode="python"),
        content_hash=_hash_model(bad_payload),
    )
    with pytest.raises(ThesisIntelligenceError, match="same snapshot"):
        build_competitor_quality(suite, semantic, bad_export)

    memberships = list(export.comparable_memberships)
    memberships[0] = memberships[0].model_copy(update={"source_queries": ("wrong query",)})
    query_payload = AnalystMarketExportPayload.model_validate(
        {**export.model_dump(exclude={"content_hash"}), "comparable_memberships": memberships}
    )
    query_export = AnalystMarketExportReport(
        **query_payload.model_dump(mode="python"),
        content_hash=_hash_model(query_payload),
    )
    with pytest.raises(ThesisIntelligenceError, match="source_queries disagree"):
        build_competitor_quality(suite, semantic, query_export)
