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
from yandex_analytics_reaper.taxonomy.primary_validation import (
    PRIMARY_ARCHETYPE_VALIDATION_CONTRACT_V1_CONTENT_HASH,
    PrimaryArchetypeLabelReview,
    PrimaryArchetypeReviewDisposition,
    PrimaryArchetypeValidationDeclaration,
    PrimaryArchetypeValidationError,
    build_primary_archetype_validation_report,
    primary_archetype_validation_contract_content_hash,
    validate_primary_archetype_validation_report,
)

_MODELED = tuple(
    archetype
    for archetype in PrimaryGameplayArchetype
    if archetype not in {PrimaryGameplayArchetype.OTHER, PrimaryGameplayArchetype.UNKNOWN}
)


def _sample() -> TaxonomyDiversitySampleReport:
    selected = tuple(
        TaxonomySampleMember(
            ordinal=index,
            platform_listing_id=f"yandex_games:{1000 + index}",
            app_id=1000 + index,
            observed_titles=(f"Game {index}",),
            developer_keys=(f"id:{2000 + index}",),
            category_ids=(index % 7,),
            tag_ids=(100 + index % 11,),
            origin_keys=("feed",),
            evidence=(
                TaxonomySampleEvidence(
                    probe_run_id="probe:one",
                    raw_snapshot_id=f"raw-{index:03d}",
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
        "sample_id": "sample:primary-validation",
        "target_size": 100,
        "max_per_developer": 2,
        "input_run_ids": ("probe:one",),
        "selected": [member.model_dump(mode="json") for member in selected],
    }
    sample_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return TaxonomyDiversitySampleReport(
        sample_id="sample:primary-validation",
        context_id="context:clean",
        input_run_ids=("probe:one",),
        target_size=100,
        max_per_developer=2,
        candidate_pool_size=120,
        selected=selected,
        pool_category_id_count=7,
        selected_category_id_count=7,
        pool_tag_id_count=11,
        selected_tag_id_count=11,
        selected_known_developer_count=100,
        selected_origin_keys=("feed",),
        sample_content_hash=sample_hash,
    )


def _gold_labels(
    sample: TaxonomyDiversitySampleReport,
    *,
    omit_archetype: PrimaryGameplayArchetype | None = None,
) -> tuple[TaxonomyManualLabel, ...]:
    modeled = tuple(archetype for archetype in _MODELED if archetype is not omit_archetype)
    labels: list[TaxonomyManualLabel] = []
    modeled_slots = 80
    for index, member in enumerate(sample.selected):
        if index < modeled_slots:
            archetype = modeled[index % len(modeled)]
            labels.append(
                TaxonomyManualLabel(
                    platform_listing_id=member.platform_listing_id,
                    primary_archetype=archetype,
                    confidence=TaxonomyAnnotationConfidence.HIGH,
                )
            )
        elif index < 90:
            labels.append(
                TaxonomyManualLabel(
                    platform_listing_id=member.platform_listing_id,
                    primary_archetype=PrimaryGameplayArchetype.OTHER,
                    confidence=TaxonomyAnnotationConfidence.MEDIUM,
                    rationale="Gameplay is understood but outside the modeled archetypes.",
                )
            )
        else:
            labels.append(
                TaxonomyManualLabel(
                    platform_listing_id=member.platform_listing_id,
                    primary_archetype=PrimaryGameplayArchetype.UNKNOWN,
                    confidence=TaxonomyAnnotationConfidence.LOW,
                    rationale="Available evidence is insufficient for a reliable primary label.",
                )
            )
    return tuple(labels)


def _gold_set(
    sample: TaxonomyDiversitySampleReport,
    *,
    omit_archetype: PrimaryGameplayArchetype | None = None,
):
    labels = _gold_labels(sample, omit_archetype=omit_archetype)
    batch = TaxonomyAnnotationBatch(
        batch_id="batch:primary-validation",
        annotator_id="annotator:a",
        sample_id=sample.sample_id,
        sample_content_hash=sample.sample_content_hash,
        created_at=datetime(2026, 8, 29, 12, 0, tzinfo=UTC),
        labels=labels,
    )
    validated = validate_taxonomy_annotation_batch(sample, batch)
    declaration = TaxonomyGoldSetDeclaration(
        gold_set_id="gold:primary-validation",
        sample_id=sample.sample_id,
        sample_content_hash=sample.sample_content_hash,
        adjudicator_id="adjudicator:a",
        adjudicated_at=datetime(2026, 8, 29, 13, 0, tzinfo=UTC),
        source_annotation_batch_hashes=(validated.annotation_batch_hash,),
        labels=labels,
    )
    return build_taxonomy_gold_set(sample, declaration, (batch,))


def _reviews(gold_set) -> tuple[PrimaryArchetypeLabelReview, ...]:
    by_archetype: dict[PrimaryGameplayArchetype, list[str]] = {
        archetype: [] for archetype in _MODELED
    }
    for label in gold_set.labels:
        if label.primary_archetype in by_archetype:
            by_archetype[label.primary_archetype].append(label.platform_listing_id)
    return tuple(
        PrimaryArchetypeLabelReview(
            archetype=archetype,
            disposition=(
                PrimaryArchetypeReviewDisposition.KEEP
                if by_archetype[archetype]
                else PrimaryArchetypeReviewDisposition.INSUFFICIENT_EVIDENCE
            ),
            evidence_listing_ids=(
                (by_archetype[archetype][0],) if by_archetype[archetype] else ()
            ),
            rationale=(
                "Observed gold examples support the current broad aggregation boundary."
                if by_archetype[archetype]
                else "The gold set contains no adjudicated examples for this archetype."
            ),
        )
        for archetype in _MODELED
    )


def _declaration(gold_set) -> PrimaryArchetypeValidationDeclaration:
    return PrimaryArchetypeValidationDeclaration(
        review_id="primary-review:1",
        reviewer_id="reviewer:a",
        gold_set_id=gold_set.gold_set_id,
        gold_set_content_hash=gold_set.gold_set_content_hash,
        reviewed_at=datetime(2026, 8, 29, 14, 0, tzinfo=UTC),
        reviews=_reviews(gold_set),
    )


def test_primary_validation_contract_identity_is_frozen() -> None:
    assert PRIMARY_ARCHETYPE_VALIDATION_CONTRACT_V1_CONTENT_HASH == (
        "6cd79128d565e4673dc61e76612587cd0ad849eafa3ab4e37468e3bc51c72576"
    )
    assert (
        primary_archetype_validation_contract_content_hash()
        == PRIMARY_ARCHETYPE_VALIDATION_CONTRACT_V1_CONTENT_HASH
    )


def test_validation_report_keeps_special_states_as_diagnostics() -> None:
    sample = _sample()
    gold_set = _gold_set(sample)
    declaration = _declaration(gold_set)

    report = build_primary_archetype_validation_report(sample, gold_set, declaration)

    assert report.total_labels == 100
    assert report.modeled_label_count == 80
    assert report.other_count == 10
    assert report.other_rate == 0.1
    assert report.unknown_count == 10
    assert report.unknown_rate == 0.1
    assert report.high_confidence_count == 80
    assert report.medium_confidence_count == 10
    assert report.low_confidence_count == 10
    assert report.labels_with_support == len(_MODELED)
    assert report.labels_without_support == 0
    assert report.revision_candidate_count == 0
    assert tuple(entry.archetype for entry in report.entries) == _MODELED
    assert len(report.validation_content_hash) == 64


def test_zero_support_forces_insufficient_evidence() -> None:
    sample = _sample()
    missing = PrimaryGameplayArchetype.CUSTOMIZATION
    gold_set = _gold_set(sample, omit_archetype=missing)
    reviews = list(_reviews(gold_set))
    missing_index = _MODELED.index(missing)
    reviews[missing_index] = reviews[missing_index].model_copy(
        update={
            "disposition": PrimaryArchetypeReviewDisposition.KEEP,
            "evidence_listing_ids": (),
        }
    )
    declaration = PrimaryArchetypeValidationDeclaration(
        review_id="primary-review:zero-support",
        reviewer_id="reviewer:a",
        gold_set_id=gold_set.gold_set_id,
        gold_set_content_hash=gold_set.gold_set_content_hash,
        reviewed_at=datetime(2026, 8, 29, 14, 0, tzinfo=UTC),
        reviews=tuple(reviews),
    )

    with pytest.raises(PrimaryArchetypeValidationError, match="zero gold-set support"):
        build_primary_archetype_validation_report(sample, gold_set, declaration)


def test_review_evidence_must_match_adjudicated_archetype() -> None:
    sample = _sample()
    gold_set = _gold_set(sample)
    reviews = list(_reviews(gold_set))
    wrong_id = gold_set.labels[4].platform_listing_id
    reviews[0] = reviews[0].model_copy(update={"evidence_listing_ids": (wrong_id,)})
    declaration = PrimaryArchetypeValidationDeclaration(
        review_id="primary-review:wrong-evidence",
        reviewer_id="reviewer:a",
        gold_set_id=gold_set.gold_set_id,
        gold_set_content_hash=gold_set.gold_set_content_hash,
        reviewed_at=datetime(2026, 8, 29, 14, 0, tzinfo=UTC),
        reviews=tuple(reviews),
    )

    with pytest.raises(PrimaryArchetypeValidationError, match="must use listings adjudicated"):
        build_primary_archetype_validation_report(sample, gold_set, declaration)


def test_declaration_requires_every_modeled_archetype_in_registry_order() -> None:
    sample = _sample()
    gold_set = _gold_set(sample)
    reviews = _reviews(gold_set)

    with pytest.raises(ValidationError, match="every modeled archetype"):
        PrimaryArchetypeValidationDeclaration(
            review_id="primary-review:missing-row",
            reviewer_id="reviewer:a",
            gold_set_id=gold_set.gold_set_id,
            gold_set_content_hash=gold_set.gold_set_content_hash,
            reviewed_at=datetime(2026, 8, 29, 14, 0, tzinfo=UTC),
            reviews=reviews[:-1],
        )


def test_persisted_validation_report_rebuild_detects_tamper() -> None:
    sample = _sample()
    gold_set = _gold_set(sample)
    declaration = _declaration(gold_set)
    report = build_primary_archetype_validation_report(sample, gold_set, declaration)

    assert (
        validate_primary_archetype_validation_report(sample, gold_set, declaration, report)
        == report
    )

    tampered = report.model_copy(update={"revision_candidate_count": 1})
    with pytest.raises(PrimaryArchetypeValidationError, match="does not match rebuilt content"):
        validate_primary_archetype_validation_report(sample, gold_set, declaration, tampered)
