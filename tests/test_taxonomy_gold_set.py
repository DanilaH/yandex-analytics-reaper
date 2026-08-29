from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from yandex_analytics_reaper.taxonomy import (
    PrimaryGameplayArchetype,
    TaxonomyDiversitySampleReport,
    TaxonomySampleEvidence,
    TaxonomySampleMember,
)
from yandex_analytics_reaper.taxonomy.gold_set import (
    ANNOTATION_CONTRACT_V1_CONTENT_HASH,
    TaxonomyAnnotationBatch,
    TaxonomyAnnotationConfidence,
    TaxonomyGoldSetDeclaration,
    TaxonomyGoldSetError,
    TaxonomyManualLabel,
    build_taxonomy_gold_set,
    taxonomy_annotation_contract_content_hash,
    validate_taxonomy_annotation_batch,
)


def _sample() -> TaxonomyDiversitySampleReport:
    selected = tuple(
        TaxonomySampleMember(
            ordinal=index,
            platform_listing_id=f"yandex_games:{1000 + index}",
            app_id=1000 + index,
            observed_titles=(f"Game {index}",),
            developer_keys=(f"id:{2000 + index}",),
            category_ids=(index % 5,),
            tag_ids=(100 + index % 7,),
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
        "sample_id": "taxonomy-sample-1",
        "target_size": 100,
        "max_per_developer": 2,
        "input_run_ids": ("probe:one",),
        "selected": [member.model_dump(mode="json") for member in selected],
    }
    content_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return TaxonomyDiversitySampleReport(
        sample_id="taxonomy-sample-1",
        context_id="context:clean",
        input_run_ids=("probe:one",),
        target_size=100,
        max_per_developer=2,
        candidate_pool_size=100,
        selected=selected,
        pool_category_id_count=5,
        selected_category_id_count=5,
        pool_tag_id_count=7,
        selected_tag_id_count=7,
        selected_known_developer_count=100,
        selected_origin_keys=("feed",),
        sample_content_hash=content_hash,
    )


def _labels(sample: TaxonomyDiversitySampleReport) -> tuple[TaxonomyManualLabel, ...]:
    return tuple(
        TaxonomyManualLabel(
            platform_listing_id=member.platform_listing_id,
            primary_archetype=PrimaryGameplayArchetype.MERGE,
            mechanics=("merge",),
            objectives=("collect",),
            meta_systems=("linear_levels",),
            tones=("relaxing",),
            confidence=TaxonomyAnnotationConfidence.HIGH,
        )
        for member in sample.selected
    )


def _batch(
    sample: TaxonomyDiversitySampleReport,
    *,
    batch_id: str = "batch:a",
    annotator_id: str = "annotator:a",
) -> TaxonomyAnnotationBatch:
    return TaxonomyAnnotationBatch(
        batch_id=batch_id,
        annotator_id=annotator_id,
        sample_id=sample.sample_id,
        sample_content_hash=sample.sample_content_hash,
        created_at=datetime(2026, 8, 29, 12, 0, tzinfo=UTC),
        labels=_labels(sample),
    )


def test_annotation_contract_hash_is_frozen() -> None:
    assert taxonomy_annotation_contract_content_hash() == ANNOTATION_CONTRACT_V1_CONTENT_HASH


def test_unknown_and_other_require_explicit_rationale() -> None:
    with pytest.raises(ValidationError, match="rationale"):
        TaxonomyManualLabel(
            platform_listing_id="yandex_games:1",
            primary_archetype=PrimaryGameplayArchetype.UNKNOWN,
            confidence=TaxonomyAnnotationConfidence.LOW,
        )

    label = TaxonomyManualLabel(
        platform_listing_id="yandex_games:1",
        primary_archetype=PrimaryGameplayArchetype.OTHER,
        confidence=TaxonomyAnnotationConfidence.MEDIUM,
        rationale="Observed gameplay is outside every current primary archetype.",
    )
    assert label.primary_archetype is PrimaryGameplayArchetype.OTHER


def test_annotation_batch_validates_exact_sample_and_canonicalizes_time() -> None:
    sample = _sample()
    plus_three = timezone(timedelta(hours=3))
    batch = _batch(sample).model_copy(
        update={"created_at": datetime(2026, 8, 29, 15, 0, tzinfo=plus_three)}
    )
    validated = validate_taxonomy_annotation_batch(sample, batch)

    assert len(validated.labels) == 100
    assert validated.created_at == datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
    assert len(validated.annotation_batch_hash) == 64

    wrong_order = _batch(sample).model_copy(update={"labels": tuple(reversed(_labels(sample)))})
    with pytest.raises(TaxonomyGoldSetError, match="sample ordinal order"):
        validate_taxonomy_annotation_batch(sample, wrong_order)


def test_annotation_boundary_revalidates_model_copy_updates() -> None:
    sample = _sample()
    tampered = _batch(sample).model_copy(update={"label_registry_version": 2})

    with pytest.raises(ValidationError):
        validate_taxonomy_annotation_batch(sample, tampered)


def test_annotation_boundary_rejects_tampered_sample_content() -> None:
    sample = _sample()
    tampered_member = sample.selected[0].model_copy(update={"observed_titles": ("Changed",)})
    tampered = sample.model_copy(update={"selected": (tampered_member,) + sample.selected[1:]})

    with pytest.raises(TaxonomyGoldSetError, match="content hash"):
        validate_taxonomy_annotation_batch(tampered, _batch(sample))


def test_gold_set_reconciles_source_batches_and_hashes_adjudication() -> None:
    sample = _sample()
    batch = _batch(sample)
    validated = validate_taxonomy_annotation_batch(sample, batch)
    declaration = TaxonomyGoldSetDeclaration(
        gold_set_id="gold:1",
        sample_id=sample.sample_id,
        sample_content_hash=sample.sample_content_hash,
        adjudicator_id="adjudicator:a",
        adjudicated_at=datetime(2026, 8, 29, 14, 0, tzinfo=UTC),
        source_annotation_batch_hashes=(validated.annotation_batch_hash,),
        labels=_labels(sample),
    )

    report = build_taxonomy_gold_set(sample, declaration, (batch,))

    assert report.sample_content_hash == sample.sample_content_hash
    assert report.source_batches[0].annotation_batch_hash == validated.annotation_batch_hash
    assert len(report.labels) == 100
    assert len(report.gold_set_content_hash) == 64

    wrong_sources = declaration.model_copy(
        update={"source_annotation_batch_hashes": ("f" * 64,)}
    )
    with pytest.raises(TaxonomyGoldSetError, match="exactly match"):
        build_taxonomy_gold_set(sample, wrong_sources, (batch,))


def test_gold_set_rejects_duplicate_annotators() -> None:
    sample = _sample()
    first = _batch(sample, batch_id="batch:a", annotator_id="annotator:a")
    second = _batch(sample, batch_id="batch:b", annotator_id="annotator:a")
    first_valid = validate_taxonomy_annotation_batch(sample, first)
    second_valid = validate_taxonomy_annotation_batch(sample, second)
    declaration = TaxonomyGoldSetDeclaration(
        gold_set_id="gold:1",
        sample_id=sample.sample_id,
        sample_content_hash=sample.sample_content_hash,
        adjudicator_id="adjudicator:a",
        adjudicated_at=datetime(2026, 8, 29, 14, 0, tzinfo=UTC),
        source_annotation_batch_hashes=(
            first_valid.annotation_batch_hash,
            second_valid.annotation_batch_hash,
        ),
        labels=_labels(sample),
    )

    with pytest.raises(TaxonomyGoldSetError, match="unique annotators"):
        build_taxonomy_gold_set(sample, declaration, (first, second))
