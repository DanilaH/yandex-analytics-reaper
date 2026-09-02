from __future__ import annotations

from pathlib import Path

import pytest
from thesis_comparison_fixture import DIGICAM, HEADPHONES, make_fixture

from yandex_analytics_reaper.thesis_anomaly import build_fresh_anomaly_queue
from yandex_analytics_reaper.thesis_comparison import (
    ThesisComparisonPayload,
    ThesisComparisonReport,
    build_thesis_comparison,
    build_thesis_intelligence_reports,
    validate_thesis_comparison,
    write_thesis_comparison_csv,
    write_thesis_comparison_json,
    write_thesis_comparison_markdown,
    write_thesis_intelligence_csv,
    write_thesis_intelligence_json,
)
from yandex_analytics_reaper.thesis_intelligence import (
    ThesisIntelligenceError,
    canonical_model_hash,
)


def _build_with_reviews():
    suite, current, traction, semantics, reviews = make_fixture()
    anomaly = build_fresh_anomaly_queue(suite, traction)
    reports = build_thesis_intelligence_reports(
        suite,
        current=current,
        traction=traction,
        anomaly=anomaly,
        semantic_reports=semantics,
        reviews=reviews,
    )
    comparison = build_thesis_comparison(
        suite,
        thesis_reports=reports,
        semantic_reports=tuple(reversed(semantics)),
        reviews=tuple(reversed(reviews)),
    )
    return suite, reports, comparison


def test_builds_declaration_order_reports_without_ranking() -> None:
    suite, reports, comparison = _build_with_reviews()

    assert [item.thesis_id for item in reports] == ["headphones", "digicam"]
    assert [item.thesis_id for item in comparison.rows] == ["headphones", "digicam"]
    assert comparison.thesis_report_hashes == tuple(item.content_hash for item in reports)
    assert comparison.current_experiment_artifact_sha256 == "1" * 64
    assert comparison.prior_experiment_artifact_sha256s == ()
    assert comparison.suite_id == suite.suite_id

    headphones, digicam = comparison.rows
    assert headphones.raw_union_members == 2
    assert headphones.direct_candidates == 1
    assert headphones.adjacent_candidates == 1
    assert headphones.confirmed_direct == 1
    assert headphones.fresh_confirmed_direct_180d == 1
    assert headphones.recent_release_180d_share == pytest.approx(0.5)
    assert headphones.recent_release_coverage_ratio == pytest.approx(1.0)
    assert headphones.best_confirmed_direct_rating_count is not None
    assert headphones.best_confirmed_direct_rating_count.platform_listing_id == HEADPHONES[0]
    assert headphones.best_adjacent_rating_count is not None
    assert headphones.best_adjacent_rating_count.platform_listing_id == HEADPHONES[1]
    assert headphones.longitudinal_coverage_ratio == 0.0
    assert headphones.mean_pairwise_query_jaccard == 0.0

    assert digicam.confirmed_direct == 2
    assert digicam.fresh_confirmed_direct_180d == 1
    assert digicam.recent_release_180d_share == pytest.approx(1.0)
    assert digicam.recent_release_coverage_ratio == pytest.approx(0.5)
    assert digicam.best_confirmed_direct_rating_count is not None
    assert digicam.best_confirmed_direct_rating_count.platform_listing_id == DIGICAM[0]
    assert digicam.best_confirmed_direct_lifetime_pace is not None
    assert digicam.best_confirmed_direct_lifetime_pace.platform_listing_id == DIGICAM[0]
    assert digicam.best_confirmed_direct_lifetime_pace.observation_id is None
    assert digicam.best_adjacent_rating_count is None
    assert digicam.mean_pairwise_query_jaccard == pytest.approx(0.5)
    assert digicam.multi_query_member_share == pytest.approx(0.5)


def test_adjacent_never_substitutes_for_missing_confirmed_direct() -> None:
    suite, current, traction, semantics, _ = make_fixture()
    anomaly = build_fresh_anomaly_queue(suite, traction)
    reports = build_thesis_intelligence_reports(
        suite,
        current=current,
        traction=traction,
        anomaly=anomaly,
        semantic_reports=semantics,
        reviews=(),
    )
    comparison = build_thesis_comparison(
        suite,
        thesis_reports=reports,
        semantic_reports=semantics,
        reviews=(),
    )

    headphones = comparison.rows[0]
    assert headphones.confirmed_direct == 0
    assert headphones.best_confirmed_direct_rating_count is None
    assert headphones.best_confirmed_direct_lifetime_pace is None
    assert headphones.best_adjacent_rating_count is not None
    assert headphones.best_adjacent_rating_count.platform_listing_id == HEADPHONES[1]


def test_comparison_rejects_reordered_rows_even_with_recomputed_hash() -> None:
    suite, reports, comparison = _build_with_reviews()
    payload = ThesisComparisonPayload.model_validate(
        {
            **comparison.model_dump(exclude={"content_hash"}),
            "rows": tuple(reversed(comparison.rows)),
            "thesis_report_hashes": tuple(reversed(comparison.thesis_report_hashes)),
        }
    )
    tampered = ThesisComparisonReport(
        **payload.model_dump(mode="python"),
        content_hash=canonical_model_hash(payload),
    )
    with pytest.raises(ThesisIntelligenceError, match="suite declaration order"):
        validate_thesis_comparison(
            tampered,
            suite=suite,
            thesis_reports=tuple(reversed(reports)),
        )


def test_outputs_are_create_only_and_markdown_disclaims_winner(tmp_path: Path) -> None:
    _, reports, comparison = _build_with_reviews()

    thesis_json = tmp_path / "thesis.json"
    thesis_csv = tmp_path / "thesis.csv"
    comparison_json = tmp_path / "comparison.json"
    comparison_csv = tmp_path / "comparison.csv"
    comparison_md = tmp_path / "comparison.md"
    write_thesis_intelligence_json(reports[0], thesis_json)
    write_thesis_intelligence_csv(reports[0], thesis_csv)
    write_thesis_comparison_json(comparison, comparison_json)
    write_thesis_comparison_csv(comparison, comparison_csv)
    write_thesis_comparison_markdown(comparison, comparison_md)

    assert thesis_json.exists()
    assert thesis_csv.exists()
    assert comparison_json.exists()
    assert comparison_csv.exists()
    text = comparison_md.read_text(encoding="utf-8")
    assert "no winner is implied" in text
    assert "Custom Headphones" in text
    assert "Custom Digicam" in text

    with pytest.raises(ThesisIntelligenceError, match="already exists"):
        write_thesis_comparison_markdown(comparison, comparison_md)
