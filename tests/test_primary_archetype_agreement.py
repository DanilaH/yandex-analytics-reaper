from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from yandex_analytics_reaper.taxonomy import (
    PrimaryGameplayArchetype,
    TaxonomyAnnotationBatch,
    TaxonomyAnnotationConfidence,
    TaxonomyDiversitySampleReport,
    TaxonomyGoldSetDeclaration,
    TaxonomyManualLabel,
    TaxonomySampleEvidence,
    TaxonomySampleMember,
    build_taxonomy_gold_set,
    validate_taxonomy_annotation_batch,
)
from yandex_analytics_reaper.taxonomy.agreement import (
    PRIMARY_ARCHETYPE_AGREEMENT_CONTRACT_V1_CONTENT_HASH,
    PRIMARY_ARCHETYPE_AGREEMENT_TARGET,
    PrimaryArchetypeAgreementError,
    build_primary_archetype_agreement_report,
    primary_archetype_agreement_contract_content_hash,
    validate_primary_archetype_agreement_report,
)


def _sample() -> TaxonomyDiversitySampleReport:
    selected = tuple(
        TaxonomySampleMember(
            ordinal=index,
            platform_listing_id=f"yandex_games:{3000 + index}",
            app_id=3000 + index,
            observed_titles=(f"Agreement Game {index}",),
            developer_keys=(f"id:{4000 + index}",),
            category_ids=(index % 5,),
            tag_ids=(200 + index % 9,),
            origin_keys=("feed",),
            evidence=(
                TaxonomySampleEvidence(
                    probe_run_id="probe:agreement",
                    raw_snapshot_id=f"raw-agreement-{index:03d}",
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
        "sample_id": "sample:agreement",
        "target_size": 100,
        "max_per_developer": 2,
        "input_run_ids": ("probe:agreement",),
        "selected": [member.model_dump(mode="json") for member in selected],
    }
    sample_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return TaxonomyDiversitySampleReport(
        sample_id="sample:agreement",
        context_id="context:clean",
        input_run_ids=("probe:agreement",),
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


def _labels(
    sample: TaxonomyDiversitySampleReport,
    *,
    variant: str,
) -> tuple[TaxonomyManualLabel, ...]:
    labels: list[TaxonomyManualLabel] = []
    for index, member in enumerate(sample.selected):
        if variant == "reviewer-b" and index < 20:
            archetype = PrimaryGameplayArchetype.MATCH
            confidence = TaxonomyAnnotationConfidence.MEDIUM
            rationale = None
        elif variant == "reviewer-b" and index < 25:
            archetype = PrimaryGameplayArchetype.UNKNOWN
            confidence = TaxonomyAnnotationConfidence.LOW
            rationale = "Evidence remains ambiguous for this listing."
        else:
            archetype = PrimaryGameplayArchetype.MERGE
            confidence = TaxonomyAnnotationConfidence.HIGH
            rationale = None
        labels.append(
            TaxonomyManualLabel(
                platform_listing_id=member.platform_listing_id,
                primary_archetype=archetype,
                confidence=confidence,
                rationale=rationale,
            )
        )
    return tuple(labels)


def _batch(
    sample: TaxonomyDiversitySampleReport,
    *,
    batch_id: str,
    annotator_id: str,
    variant: str,
) -> TaxonomyAnnotationBatch:
    return TaxonomyAnnotationBatch(
        batch_id=batch_id,
        annotator_id=annotator_id,
        sample_id=sample.sample_id,
        sample_content_hash=sample.sample_content_hash,
        created_at=datetime(2026, 8, 29, 15, 0, tzinfo=UTC),
        labels=_labels(sample, variant=variant),
    )


def _gold_set_for_batches(
    sample: TaxonomyDiversitySampleReport,
    batches: tuple[TaxonomyAnnotationBatch, ...],
):
    validated = tuple(validate_taxonomy_annotation_batch(sample, batch) for batch in batches)
    declaration = TaxonomyGoldSetDeclaration(
        gold_set_id="gold:agreement",
        sample_id=sample.sample_id,
        sample_content_hash=sample.sample_content_hash,
        adjudicator_id="adjudicator:a",
        adjudicated_at=datetime(2026, 8, 29, 16, 0, tzinfo=UTC),
        source_annotation_batch_hashes=tuple(
            batch.annotation_batch_hash for batch in validated
        ),
        labels=_labels(sample, variant="reviewer-a"),
    )
    return build_taxonomy_gold_set(sample, declaration, batches)


def _gold_fixture():
    sample = _sample()
    batch_a = _batch(
        sample,
        batch_id="batch:agreement:a",
        annotator_id="annotator:a",
        variant="reviewer-a",
    )
    batch_b = _batch(
        sample,
        batch_id="batch:agreement:b",
        annotator_id="annotator:b",
        variant="reviewer-b",
    )
    gold_set = _gold_set_for_batches(sample, (batch_a, batch_b))
    return sample, gold_set, batch_a, batch_b


def test_primary_agreement_contract_identity_is_frozen() -> None:
    assert PRIMARY_ARCHETYPE_AGREEMENT_CONTRACT_V1_CONTENT_HASH == (
        "e09af2c913058837724d51fad30a0b29e95faf7dd2d00ce91a99ccb0506e368f"
    )
    assert primary_archetype_agreement_contract_content_hash() == (
        PRIMARY_ARCHETYPE_AGREEMENT_CONTRACT_V1_CONTENT_HASH
    )
    assert PRIMARY_ARCHETYPE_AGREEMENT_TARGET == 0.90


def test_agreement_report_uses_independent_batches_and_symmetric_confusions() -> None:
    sample, gold_set, batch_a, batch_b = _gold_fixture()

    report = build_primary_archetype_agreement_report(
        sample,
        gold_set,
        (batch_a, batch_b),
    )

    assert report.total_labels == 100
    assert report.source_batch_count == 2
    assert report.pairwise_comparison_count == 100
    assert report.pairwise_agreement_count == 75
    assert report.pairwise_disagreement_count == 25
    assert report.pairwise_agreement_rate == 0.75
    assert report.meets_initial_primary_agreement_target is False
    assert report.unanimous_listing_count == 75
    assert report.unanimous_listing_rate == 0.75
    assert report.low_confidence_assignment_count == 5
    assert report.low_confidence_assignment_rate == 0.025
    assert report.unknown_assignment_count == 5
    assert report.unknown_assignment_rate == 0.025
    assert report.other_assignment_count == 0
    assert report.disagreement_listing_ids == tuple(
        member.platform_listing_id for member in sample.selected[:25]
    )
    assert tuple(
        (
            pair.archetype_a,
            pair.archetype_b,
            pair.comparison_count,
            pair.comparison_rate,
        )
        for pair in report.confusion_pairs
    ) == (
        (
            PrimaryGameplayArchetype.MERGE,
            PrimaryGameplayArchetype.MATCH,
            20,
            0.2,
        ),
        (
            PrimaryGameplayArchetype.MERGE,
            PrimaryGameplayArchetype.UNKNOWN,
            5,
            0.05,
        ),
    )


def test_pairwise_formula_handles_three_independent_annotators() -> None:
    sample = _sample()
    batch_a = _batch(
        sample,
        batch_id="batch:agreement:a",
        annotator_id="annotator:a",
        variant="reviewer-a",
    )
    batch_b = _batch(
        sample,
        batch_id="batch:agreement:b",
        annotator_id="annotator:b",
        variant="reviewer-b",
    )
    batch_c = _batch(
        sample,
        batch_id="batch:agreement:c",
        annotator_id="annotator:c",
        variant="reviewer-a",
    )
    batches = (batch_a, batch_b, batch_c)
    gold_set = _gold_set_for_batches(sample, batches)

    report = build_primary_archetype_agreement_report(sample, gold_set, batches)

    assert report.source_batch_count == 3
    assert report.pairwise_comparison_count == 300
    assert report.pairwise_agreement_count == 250
    assert report.pairwise_disagreement_count == 50
    assert report.pairwise_agreement_rate == 250 / 300
    assert report.unanimous_listing_count == 75
    assert tuple(pair.comparison_count for pair in report.confusion_pairs) == (40, 10)


def test_gold_alignment_metrics_are_not_fake_classifier_metrics() -> None:
    sample, gold_set, batch_a, batch_b = _gold_fixture()

    report = build_primary_archetype_agreement_report(
        sample,
        gold_set,
        (batch_a, batch_b),
    )
    by_archetype = {metric.archetype: metric for metric in report.class_metrics}

    merge = by_archetype[PrimaryGameplayArchetype.MERGE]
    assert merge.gold_support_count == 100
    assert merge.annotation_assignment_count == 175
    assert merge.gold_alignment_true_positive_count == 175
    assert merge.gold_alignment_false_positive_count == 0
    assert merge.gold_alignment_false_negative_count == 25
    assert merge.gold_alignment_precision == 1.0
    assert merge.gold_alignment_recall == 0.875

    match = by_archetype[PrimaryGameplayArchetype.MATCH]
    assert match.gold_support_count == 0
    assert match.annotation_assignment_count == 20
    assert match.gold_alignment_true_positive_count == 0
    assert match.gold_alignment_false_positive_count == 20
    assert match.gold_alignment_false_negative_count == 0
    assert match.gold_alignment_precision == 0.0
    assert match.gold_alignment_recall is None

    unsupported = by_archetype[PrimaryGameplayArchetype.SHOOTER]
    assert unsupported.gold_support_count == 0
    assert unsupported.annotation_assignment_count == 0
    assert unsupported.gold_alignment_precision is None
    assert unsupported.gold_alignment_recall is None


def test_agreement_requires_at_least_two_independent_source_batches() -> None:
    sample, gold_set, batch_a, _ = _gold_fixture()

    with pytest.raises(PrimaryArchetypeAgreementError, match="at least two independent"):
        build_primary_archetype_agreement_report(sample, gold_set, (batch_a,))


def test_agreement_requires_exact_gold_source_batch_order_and_identity() -> None:
    sample, gold_set, batch_a, batch_b = _gold_fixture()

    with pytest.raises(PrimaryArchetypeAgreementError, match="exactly match gold-set"):
        build_primary_archetype_agreement_report(
            sample,
            gold_set,
            (batch_b, batch_a),
        )


def test_agreement_revalidates_annotation_model_copy() -> None:
    sample, gold_set, batch_a, batch_b = _gold_fixture()
    tampered = batch_b.model_copy(update={"labels": batch_b.labels[:-1]})

    with pytest.raises(ValidationError):
        build_primary_archetype_agreement_report(
            sample,
            gold_set,
            (batch_a, tampered),
        )


def test_persisted_agreement_report_rebuild_detects_tamper() -> None:
    sample, gold_set, batch_a, batch_b = _gold_fixture()
    report = build_primary_archetype_agreement_report(
        sample,
        gold_set,
        (batch_a, batch_b),
    )

    assert validate_primary_archetype_agreement_report(
        sample,
        gold_set,
        (batch_a, batch_b),
        report,
    ) == report

    tampered = report.model_copy(update={"pairwise_agreement_count": 76})
    with pytest.raises(ValidationError, match="cover all comparisons"):
        validate_primary_archetype_agreement_report(
            sample,
            gold_set,
            (batch_a, batch_b),
            tampered,
        )
