from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from yandex_analytics_reaper.taxonomy import (
    TaxonomyDiversitySampleReport,
    TaxonomySampleEvidence,
    TaxonomySampleMember,
)
from yandex_analytics_reaper.taxonomy.theme_canonicalization import (
    THEME_CANONICALIZATION_CONTRACT_V1_CONTENT_HASH,
    THEME_CANONICALIZATION_TARGET,
    ThemeCandidateManifest,
    ThemeCandidateTerm,
    ThemeCanonicalizationBatch,
    ThemeCanonicalizationDecision,
    ThemeCanonicalizationError,
    ThemeCanonicalizationGoldDeclaration,
    ThemeCanonicalizationResolution,
    build_theme_canonicalization_gold_set,
    build_theme_canonicalization_report,
    theme_canonicalization_contract_content_hash,
    validate_theme_candidate_manifest,
    validate_theme_canonicalization_batch,
    validate_theme_canonicalization_report,
)


def _sample() -> TaxonomyDiversitySampleReport:
    selected = tuple(
        TaxonomySampleMember(
            ordinal=index,
            platform_listing_id=f"yandex_games:{7000 + index}",
            app_id=7000 + index,
            observed_titles=(f"Theme Game {index}",),
            developer_keys=(f"id:{8000 + index}",),
            category_ids=(index % 5,),
            tag_ids=(400 + index % 9,),
            origin_keys=("feed",),
            evidence=(
                TaxonomySampleEvidence(
                    probe_run_id="probe:theme-canonicalization",
                    raw_snapshot_id=f"raw-theme-{index:03d}",
                    page_index=0,
                    source_object_path=f"$.feed[0].items[{index}]",
                    origin_key="feed",
                ),
            ),
        )
        for index in range(100)
    )
    payload = {
        "spec_version": "taxonomy-diversity-sample-v1",
        "sample_id": "sample:theme-canonicalization",
        "target_size": 100,
        "max_per_developer": 2,
        "input_run_ids": ("probe:theme-canonicalization",),
        "selected": [member.model_dump(mode="json") for member in selected],
    }
    sample_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return TaxonomyDiversitySampleReport(
        sample_id="sample:theme-canonicalization",
        context_id="context:clean",
        input_run_ids=("probe:theme-canonicalization",),
        target_size=100,
        max_per_developer=2,
        candidate_pool_size=120,
        selected=selected,
        pool_category_id_count=5,
        selected_category_id_count=5,
        pool_tag_id_count=9,
        selected_tag_id_count=9,
        selected_known_developer_count=100,
        selected_origin_keys=("feed",),
        sample_content_hash=sample_hash,
    )


def _manifest(sample: TaxonomyDiversitySampleReport) -> ThemeCandidateManifest:
    return ThemeCandidateManifest(
        manifest_id="theme-manifest:1",
        sample_id=sample.sample_id,
        sample_content_hash=sample.sample_content_hash,
        created_at=datetime(2026, 8, 29, 18, 30, tzinfo=UTC),
        reviewed_listing_ids=tuple(
            member.platform_listing_id for member in sample.selected
        ),
        terms=tuple(
            ThemeCandidateTerm(
                term_id=f"theme-term:{index:03d}",
                platform_listing_id=member.platform_listing_id,
                surface_form=("Машины" if index % 2 == 0 else "Cars & Racing"),
                language=("ru" if index % 2 == 0 else "en"),
            )
            for index, member in enumerate(sample.selected)
        ),
    )


def _decisions(
    manifest: ThemeCandidateManifest,
    *,
    variant: str,
) -> tuple[ThemeCanonicalizationDecision, ...]:
    decisions: list[ThemeCanonicalizationDecision] = []
    for index, term in enumerate(manifest.terms):
        if variant == "reviewer-b" and index < 2:
            decisions.append(
                ThemeCanonicalizationDecision(
                    term_id=term.term_id,
                    resolution=ThemeCanonicalizationResolution.CANONICAL,
                    canonical_theme_key="vehicles",
                )
            )
        elif variant == "reviewer-b" and index < 4:
            decisions.append(
                ThemeCanonicalizationDecision(
                    term_id=term.term_id,
                    resolution=ThemeCanonicalizationResolution.UNKNOWN,
                    rationale="The candidate is too ambiguous to canonicalize confidently.",
                )
            )
        elif variant == "reviewer-b" and index == 4:
            decisions.append(
                ThemeCanonicalizationDecision(
                    term_id=term.term_id,
                    resolution=ThemeCanonicalizationResolution.NOT_THEME,
                    rationale="The extracted surface form is not a durable game theme.",
                )
            )
        elif variant == "reviewer-c" and index < 6:
            decisions.append(
                ThemeCanonicalizationDecision(
                    term_id=term.term_id,
                    resolution=ThemeCanonicalizationResolution.CANONICAL,
                    canonical_theme_key="vehicles",
                )
            )
        else:
            decisions.append(
                ThemeCanonicalizationDecision(
                    term_id=term.term_id,
                    resolution=ThemeCanonicalizationResolution.CANONICAL,
                    canonical_theme_key="cars",
                )
            )
    return tuple(decisions)


def _batch(
    sample: TaxonomyDiversitySampleReport,
    manifest: ThemeCandidateManifest,
    *,
    batch_id: str,
    annotator_id: str,
    variant: str,
) -> ThemeCanonicalizationBatch:
    validated_manifest = validate_theme_candidate_manifest(sample, manifest)
    return ThemeCanonicalizationBatch(
        batch_id=batch_id,
        annotator_id=annotator_id,
        manifest_id=validated_manifest.manifest_id,
        manifest_content_hash=validated_manifest.manifest_content_hash,
        sample_id=validated_manifest.sample_id,
        sample_content_hash=validated_manifest.sample_content_hash,
        created_at=datetime(2026, 8, 29, 19, 0, tzinfo=UTC),
        decisions=_decisions(manifest, variant=variant),
    )


def _gold_fixture():
    sample = _sample()
    manifest = _manifest(sample)
    batch_a = _batch(
        sample,
        manifest,
        batch_id="theme-batch:a",
        annotator_id="theme-annotator:a",
        variant="reviewer-a",
    )
    batch_b = _batch(
        sample,
        manifest,
        batch_id="theme-batch:b",
        annotator_id="theme-annotator:b",
        variant="reviewer-b",
    )
    validated_a = validate_theme_canonicalization_batch(sample, manifest, batch_a)
    validated_b = validate_theme_canonicalization_batch(sample, manifest, batch_b)
    validated_manifest = validate_theme_candidate_manifest(sample, manifest)
    declaration = ThemeCanonicalizationGoldDeclaration(
        gold_set_id="theme-gold:1",
        manifest_id=validated_manifest.manifest_id,
        manifest_content_hash=validated_manifest.manifest_content_hash,
        sample_id=validated_manifest.sample_id,
        sample_content_hash=validated_manifest.sample_content_hash,
        adjudicator_id="theme-adjudicator:a",
        adjudicated_at=datetime(2026, 8, 29, 20, 0, tzinfo=UTC),
        source_annotation_batch_hashes=(
            validated_a.annotation_batch_hash,
            validated_b.annotation_batch_hash,
        ),
        decisions=_decisions(manifest, variant="reviewer-a"),
    )
    gold_set = build_theme_canonicalization_gold_set(
        sample,
        manifest,
        declaration,
        (batch_a, batch_b),
    )
    return sample, manifest, gold_set, batch_a, batch_b


def test_theme_canonicalization_contract_identity_is_frozen() -> None:
    assert THEME_CANONICALIZATION_CONTRACT_V1_CONTENT_HASH == (
        "a69d87f545c11a5058e2a83b86d6c0bf7a800e4c57a6792ac456a16a578951d6"
    )
    assert theme_canonicalization_contract_content_hash() == (
        THEME_CANONICALIZATION_CONTRACT_V1_CONTENT_HASH
    )
    assert THEME_CANONICALIZATION_TARGET == 0.95


def test_manifest_requires_full_sample_review_but_preserves_raw_surface_forms() -> None:
    sample = _sample()
    manifest = _manifest(sample)

    validated = validate_theme_candidate_manifest(sample, manifest)

    assert validated.reviewed_listing_ids == tuple(
        member.platform_listing_id for member in sample.selected
    )
    assert validated.terms[0].surface_form == "Машины"
    assert validated.terms[1].surface_form == "Cars & Racing"
    assert len(validated.manifest_content_hash) == 64

    broken = manifest.model_copy(
        update={"reviewed_listing_ids": manifest.reviewed_listing_ids[:-1]}
    )
    with pytest.raises(ValidationError):
        validate_theme_candidate_manifest(sample, broken)


def test_manifest_terms_must_follow_sample_listing_order() -> None:
    sample = _sample()
    manifest = _manifest(sample)
    terms = list(manifest.terms)
    terms[0], terms[1] = terms[1], terms[0]
    broken = manifest.model_copy(update={"terms": tuple(terms)})

    with pytest.raises(ThemeCanonicalizationError, match="sample listing order"):
        validate_theme_candidate_manifest(sample, broken)


def test_resolution_semantics_are_fail_closed() -> None:
    with pytest.raises(ValidationError, match="requires canonical_theme_key"):
        ThemeCanonicalizationDecision(
            term_id="term:1",
            resolution=ThemeCanonicalizationResolution.CANONICAL,
        )

    with pytest.raises(ValidationError, match="cannot carry a theme key"):
        ThemeCanonicalizationDecision(
            term_id="term:2",
            resolution=ThemeCanonicalizationResolution.UNKNOWN,
            canonical_theme_key="cars",
            rationale="Ambiguous.",
        )

    with pytest.raises(ValidationError, match="must be lowercase"):
        ThemeCanonicalizationDecision(
            term_id="term:3",
            resolution=ThemeCanonicalizationResolution.CANONICAL,
            canonical_theme_key="Cars",
        )


def test_theme_report_uses_exact_outcome_agreement_and_keeps_state_diagnostics() -> None:
    sample, manifest, gold_set, batch_a, batch_b = _gold_fixture()

    report = build_theme_canonicalization_report(
        sample,
        manifest,
        gold_set,
        (batch_a, batch_b),
    )

    assert report.total_candidate_terms == 100
    assert report.source_batch_count == 2
    assert report.pairwise_comparison_count == 100
    assert report.pairwise_agreement_count == 95
    assert report.pairwise_disagreement_count == 5
    assert report.pairwise_agreement_rate == 0.95
    assert report.meets_initial_theme_canonicalization_target is True
    assert report.unanimous_term_count == 95
    assert report.canonical_assignment_count == 197
    assert report.canonical_assignment_rate == 197 / 200
    assert report.unknown_assignment_count == 2
    assert report.unknown_assignment_rate == 0.01
    assert report.not_theme_assignment_count == 1
    assert report.not_theme_assignment_rate == 0.005
    assert report.gold_alignment_count == 195
    assert report.gold_alignment_rate == 0.975
    assert report.disagreement_term_ids == tuple(
        term.term_id for term in manifest.terms[:5]
    )
    assert tuple(
        (pair.outcome_a, pair.outcome_b, pair.comparison_count)
        for pair in report.confusion_pairs
    ) == (
        ("theme:cars", "theme:vehicles", 2),
        ("theme:cars", "unknown", 2),
        ("not_theme", "theme:cars", 1),
    )
    assert report.canonical_gold_theme_keys == ("cars",)


def test_open_theme_metrics_use_gold_alignment_without_fake_recall() -> None:
    sample, manifest, gold_set, batch_a, batch_b = _gold_fixture()
    report = build_theme_canonicalization_report(
        sample,
        manifest,
        gold_set,
        (batch_a, batch_b),
    )
    by_key = {metric.canonical_theme_key: metric for metric in report.theme_metrics}

    cars = by_key["cars"]
    assert cars.gold_support_count == 100
    assert cars.annotation_assignment_count == 195
    assert cars.gold_alignment_true_positive_count == 195
    assert cars.gold_alignment_false_positive_count == 0
    assert cars.gold_alignment_false_negative_count == 5
    assert cars.gold_alignment_precision == 1.0
    assert cars.gold_alignment_recall == 0.975

    vehicles = by_key["vehicles"]
    assert vehicles.gold_support_count == 0
    assert vehicles.annotation_assignment_count == 2
    assert vehicles.gold_alignment_true_positive_count == 0
    assert vehicles.gold_alignment_false_positive_count == 2
    assert vehicles.gold_alignment_false_negative_count == 0
    assert vehicles.gold_alignment_precision == 0.0
    assert vehicles.gold_alignment_recall is None


def test_below_target_theme_agreement_does_not_pass() -> None:
    sample = _sample()
    manifest = _manifest(sample)
    batch_a = _batch(
        sample,
        manifest,
        batch_id="theme-batch:a",
        annotator_id="theme-annotator:a",
        variant="reviewer-a",
    )
    batch_c = _batch(
        sample,
        manifest,
        batch_id="theme-batch:c",
        annotator_id="theme-annotator:c",
        variant="reviewer-c",
    )
    validated_a = validate_theme_canonicalization_batch(sample, manifest, batch_a)
    validated_c = validate_theme_canonicalization_batch(sample, manifest, batch_c)
    validated_manifest = validate_theme_candidate_manifest(sample, manifest)
    declaration = ThemeCanonicalizationGoldDeclaration(
        gold_set_id="theme-gold:below-target",
        manifest_id=validated_manifest.manifest_id,
        manifest_content_hash=validated_manifest.manifest_content_hash,
        sample_id=validated_manifest.sample_id,
        sample_content_hash=validated_manifest.sample_content_hash,
        adjudicator_id="theme-adjudicator:a",
        adjudicated_at=datetime(2026, 8, 29, 20, 0, tzinfo=UTC),
        source_annotation_batch_hashes=(
            validated_a.annotation_batch_hash,
            validated_c.annotation_batch_hash,
        ),
        decisions=_decisions(manifest, variant="reviewer-a"),
    )
    gold_set = build_theme_canonicalization_gold_set(
        sample,
        manifest,
        declaration,
        (batch_a, batch_c),
    )

    report = build_theme_canonicalization_report(
        sample,
        manifest,
        gold_set,
        (batch_a, batch_c),
    )

    assert report.pairwise_agreement_rate == 0.94
    assert report.meets_initial_theme_canonicalization_target is False


def test_gold_set_requires_at_least_two_distinct_annotators() -> None:
    sample = _sample()
    manifest = _manifest(sample)
    batch_a = _batch(
        sample,
        manifest,
        batch_id="theme-batch:a",
        annotator_id="theme-annotator:a",
        variant="reviewer-a",
    )
    validated_a = validate_theme_canonicalization_batch(sample, manifest, batch_a)
    validated_manifest = validate_theme_candidate_manifest(sample, manifest)
    declaration = ThemeCanonicalizationGoldDeclaration(
        gold_set_id="theme-gold:single",
        manifest_id=validated_manifest.manifest_id,
        manifest_content_hash=validated_manifest.manifest_content_hash,
        sample_id=validated_manifest.sample_id,
        sample_content_hash=validated_manifest.sample_content_hash,
        adjudicator_id="theme-adjudicator:a",
        adjudicated_at=datetime(2026, 8, 29, 20, 0, tzinfo=UTC),
        source_annotation_batch_hashes=(validated_a.annotation_batch_hash,) * 2,
        decisions=_decisions(manifest, variant="reviewer-a"),
    )

    with pytest.raises(ValidationError, match="source annotation hashes must be unique"):
        build_theme_canonicalization_gold_set(
            sample,
            manifest,
            declaration,
            (batch_a,),
        )


def test_annotation_model_copy_is_revalidated() -> None:
    sample, manifest, gold_set, batch_a, batch_b = _gold_fixture()
    tampered = batch_b.model_copy(update={"decisions": batch_b.decisions[:-1]})

    with pytest.raises(ThemeCanonicalizationError, match="every manifest term"):
        build_theme_canonicalization_report(
            sample,
            manifest,
            gold_set,
            (batch_a, tampered),
        )


def test_persisted_theme_report_rebuild_detects_tamper() -> None:
    sample, manifest, gold_set, batch_a, batch_b = _gold_fixture()
    report = build_theme_canonicalization_report(
        sample,
        manifest,
        gold_set,
        (batch_a, batch_b),
    )

    assert validate_theme_canonicalization_report(
        sample,
        manifest,
        gold_set,
        (batch_a, batch_b),
        report,
    ) == report

    tampered = report.model_copy(update={"gold_alignment_count": 194})
    with pytest.raises(ValidationError, match="gold alignment rate is inconsistent"):
        validate_theme_canonicalization_report(
            sample,
            manifest,
            gold_set,
            (batch_a, batch_b),
            tampered,
        )
