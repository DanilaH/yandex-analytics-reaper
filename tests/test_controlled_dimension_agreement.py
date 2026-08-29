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
from yandex_analytics_reaper.taxonomy.controlled_agreement import (
    CONTROLLED_DIMENSION_AGREEMENT_CONTRACT_V1_CONTENT_HASH,
    CONTROLLED_DIMENSION_AGREEMENT_TARGET,
    ControlledDimensionAgreementError,
    build_controlled_dimension_agreement_report,
    controlled_dimension_agreement_contract_content_hash,
    validate_controlled_dimension_agreement_report,
)
from yandex_analytics_reaper.taxonomy.registries import ControlledLabelDimension


def _sample() -> TaxonomyDiversitySampleReport:
    selected = tuple(
        TaxonomySampleMember(
            ordinal=index,
            platform_listing_id=f"yandex_games:{5000 + index}",
            app_id=5000 + index,
            observed_titles=(f"Controlled Agreement Game {index}",),
            developer_keys=(f"id:{6000 + index}",),
            category_ids=(index % 5,),
            tag_ids=(300 + index % 9,),
            origin_keys=("feed",),
            evidence=(
                TaxonomySampleEvidence(
                    probe_run_id="probe:controlled-agreement",
                    raw_snapshot_id=f"raw-controlled-{index:03d}",
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
        "sample_id": "sample:controlled-agreement",
        "target_size": 100,
        "max_per_developer": 2,
        "input_run_ids": ("probe:controlled-agreement",),
        "selected": [member.model_dump(mode="json") for member in selected],
    }
    sample_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return TaxonomyDiversitySampleReport(
        sample_id="sample:controlled-agreement",
        context_id="context:clean",
        input_run_ids=("probe:controlled-agreement",),
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
        mechanics = ("merge", "tap")
        objectives = ("solve",)
        meta_systems = ("none",)
        tones = ("relaxing",)
        if variant == "reviewer-b":
            if index < 20:
                mechanics = ("tap", "match")
            if 20 <= index < 30:
                objectives = ()
            if 30 <= index < 35:
                tones = ("tense",)
        elif variant == "order-only":
            mechanics = ("tap", "merge")
        labels.append(
            TaxonomyManualLabel(
                platform_listing_id=member.platform_listing_id,
                primary_archetype=PrimaryGameplayArchetype.MERGE,
                mechanics=mechanics,
                objectives=objectives,
                meta_systems=meta_systems,
                tones=tones,
                confidence=TaxonomyAnnotationConfidence.HIGH,
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
        created_at=datetime(2026, 8, 29, 17, 0, tzinfo=UTC),
        labels=_labels(sample, variant=variant),
    )


def _gold_set_for_batches(
    sample: TaxonomyDiversitySampleReport,
    batches: tuple[TaxonomyAnnotationBatch, ...],
):
    validated = tuple(validate_taxonomy_annotation_batch(sample, batch) for batch in batches)
    declaration = TaxonomyGoldSetDeclaration(
        gold_set_id="gold:controlled-agreement",
        sample_id=sample.sample_id,
        sample_content_hash=sample.sample_content_hash,
        adjudicator_id="adjudicator:a",
        adjudicated_at=datetime(2026, 8, 29, 18, 0, tzinfo=UTC),
        source_annotation_batch_hashes=tuple(
            batch.annotation_batch_hash for batch in validated
        ),
        labels=_labels(sample, variant="reviewer-a"),
    )
    return build_taxonomy_gold_set(sample, declaration, batches)


def _fixture():
    sample = _sample()
    batch_a = _batch(
        sample,
        batch_id="batch:controlled:a",
        annotator_id="annotator:a",
        variant="reviewer-a",
    )
    batch_b = _batch(
        sample,
        batch_id="batch:controlled:b",
        annotator_id="annotator:b",
        variant="reviewer-b",
    )
    gold_set = _gold_set_for_batches(sample, (batch_a, batch_b))
    return sample, gold_set, batch_a, batch_b


def test_controlled_agreement_contract_identity_is_frozen() -> None:
    assert CONTROLLED_DIMENSION_AGREEMENT_CONTRACT_V1_CONTENT_HASH == (
        "9bebd5221d664ace6b6c046384bed76bbd37153908b4852317cfa74a4832798b"
    )
    assert controlled_dimension_agreement_contract_content_hash() == (
        CONTROLLED_DIMENSION_AGREEMENT_CONTRACT_V1_CONTENT_HASH
    )
    assert CONTROLLED_DIMENSION_AGREEMENT_TARGET == 0.90


def test_controlled_dimensions_use_exact_set_pairwise_agreement() -> None:
    sample, gold_set, batch_a, batch_b = _fixture()

    report = build_controlled_dimension_agreement_report(
        sample,
        gold_set,
        (batch_a, batch_b),
    )
    by_dimension = {entry.dimension: entry for entry in report.dimensions}

    mechanics = by_dimension[ControlledLabelDimension.MECHANICS]
    assert mechanics.pairwise_comparison_count == 100
    assert mechanics.pairwise_exact_match_count == 80
    assert mechanics.pairwise_exact_mismatch_count == 20
    assert mechanics.pairwise_exact_match_rate == 0.8
    assert mechanics.meets_initial_agreement_target is False
    assert mechanics.unanimous_listing_count == 80
    assert mechanics.disagreement_listing_ids == tuple(
        member.platform_listing_id for member in sample.selected[:20]
    )

    objectives = by_dimension[ControlledLabelDimension.OBJECTIVES]
    assert objectives.pairwise_exact_match_rate == 0.9
    assert objectives.meets_initial_agreement_target is True

    meta_systems = by_dimension[ControlledLabelDimension.META_SYSTEMS]
    assert meta_systems.pairwise_exact_match_rate == 1.0
    assert meta_systems.meets_initial_agreement_target is True

    tones = by_dimension[ControlledLabelDimension.TONES]
    assert tones.pairwise_exact_match_rate == 0.95
    assert tones.meets_initial_agreement_target is True
    assert report.all_dimensions_meet_initial_agreement_target is False


def test_multi_label_input_order_is_not_a_false_disagreement() -> None:
    sample = _sample()
    batch_a = _batch(
        sample,
        batch_id="batch:controlled:a",
        annotator_id="annotator:a",
        variant="reviewer-a",
    )
    batch_b = _batch(
        sample,
        batch_id="batch:controlled:order",
        annotator_id="annotator:b",
        variant="order-only",
    )
    gold_set = _gold_set_for_batches(sample, (batch_a, batch_b))

    report = build_controlled_dimension_agreement_report(
        sample,
        gold_set,
        (batch_a, batch_b),
    )

    assert all(entry.pairwise_exact_match_rate == 1.0 for entry in report.dimensions)
    assert all(not entry.disagreement_listing_ids for entry in report.dimensions)
    assert report.all_dimensions_meet_initial_agreement_target is True


def test_controlled_label_gold_alignment_handles_unsupported_labels() -> None:
    sample, gold_set, batch_a, batch_b = _fixture()
    report = build_controlled_dimension_agreement_report(
        sample,
        gold_set,
        (batch_a, batch_b),
    )
    mechanics = next(
        entry
        for entry in report.dimensions
        if entry.dimension is ControlledLabelDimension.MECHANICS
    )
    by_label = {metric.label: metric for metric in mechanics.label_metrics}

    merge = by_label["merge"]
    assert merge.gold_support_count == 100
    assert merge.annotation_assignment_count == 180
    assert merge.gold_alignment_true_positive_count == 180
    assert merge.gold_alignment_false_positive_count == 0
    assert merge.gold_alignment_false_negative_count == 20
    assert merge.gold_alignment_precision == 1.0
    assert merge.gold_alignment_recall == 0.9

    match = by_label["match"]
    assert match.gold_support_count == 0
    assert match.annotation_assignment_count == 20
    assert match.gold_alignment_precision == 0.0
    assert match.gold_alignment_recall is None

    timing = by_label["timing"]
    assert timing.gold_support_count == 0
    assert timing.annotation_assignment_count == 0
    assert timing.gold_alignment_precision is None
    assert timing.gold_alignment_recall is None


def test_controlled_agreement_requires_exact_gold_source_batch_order() -> None:
    sample, gold_set, batch_a, batch_b = _fixture()

    with pytest.raises(ControlledDimensionAgreementError, match="exactly match gold-set"):
        build_controlled_dimension_agreement_report(
            sample,
            gold_set,
            (batch_b, batch_a),
        )


def test_controlled_agreement_revalidates_annotation_model_copy() -> None:
    sample, gold_set, batch_a, batch_b = _fixture()
    tampered = batch_b.model_copy(update={"labels": batch_b.labels[:-1]})

    with pytest.raises(ValidationError):
        build_controlled_dimension_agreement_report(
            sample,
            gold_set,
            (batch_a, tampered),
        )


def test_persisted_controlled_agreement_report_rebuild_detects_tamper() -> None:
    sample, gold_set, batch_a, batch_b = _fixture()
    report = build_controlled_dimension_agreement_report(
        sample,
        gold_set,
        (batch_a, batch_b),
    )

    assert validate_controlled_dimension_agreement_report(
        sample,
        gold_set,
        (batch_a, batch_b),
        report,
    ) == report

    tampered = report.model_copy(
        update={"all_dimensions_meet_initial_agreement_target": True}
    )
    with pytest.raises(ValidationError, match="aggregate target result"):
        validate_controlled_dimension_agreement_report(
            sample,
            gold_set,
            (batch_a, batch_b),
            tampered,
        )
