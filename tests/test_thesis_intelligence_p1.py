from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from yandex_analytics_reaper.thesis_intelligence import (
    ExperimentArtifactBinding,
    ThesisAnomalyPolicy,
    ThesisDeclaration,
    ThesisIntelligenceBuildInputs,
    ThesisIntelligenceError,
    ThesisReviewBinding,
    ThesisSemanticDeclaration,
    ThesisSuiteContext,
    ThesisSuiteDeclaration,
    build_intelligence_identity,
    build_intelligence_inputs,
    canonical_model_hash,
    compile_thesis_suite,
    validate_artifact_file_sha256,
)


def _suite() -> ThesisSuiteDeclaration:
    return ThesisSuiteDeclaration(
        suite_id="next-microgame-candidates",
        suite_version=1,
        context=ThesisSuiteContext(
            pages=3,
            session_profile="clean_anonymous",
            lang="ru",
            device="desktop",
            platform="desktop_other",
        ),
        anomaly_policy=ThesisAnomalyPolicy(
            max_age_days=180,
            min_rating_count=100,
            min_lifetime_ratings_per_day=5.0,
        ),
        theses=(
            ThesisDeclaration(
                thesis_id="satisfying-destruction",
                thesis_version=1,
                label="destruction x ordinary objects",
                queries=("сломать предметы", "разбить всё", "destroy objects"),
                semantic=ThesisSemanticDeclaration(
                    theme_terms=("предмет", "object"),
                    mechanic_terms=("слом", "разб", "destroy", "break"),
                    reward_grammar_terms=("разруш", "damage", "destroyed"),
                ),
            ),
            ThesisDeclaration(
                thesis_id="custom-digicam",
                thesis_version=2,
                label="customization x digicam",
                queries=("украсить камеру", "custom digicam"),
                semantic=ThesisSemanticDeclaration(
                    theme_terms=("камера", "camera", "digicam"),
                    mechanic_terms=("украс", "custom", "decorate"),
                    reward_grammar_terms=None,
                ),
            ),
        ),
    )


def _binding(
    *,
    role: str,
    marker: str,
    experiment_id: str = "next-microgame-candidates",
    run_id: str = "20260902T100000Z",
    snapshot_created_at: datetime | None = None,
) -> ExperimentArtifactBinding:
    return ExperimentArtifactBinding(
        role=role,
        artifact_sha256=marker * 64,
        artifact_manifest_sha256="a" * 64,
        experiment_id=experiment_id,
        run_id=run_id,
        manifest_sha256="b" * 64,
        snapshot_id=f"snapshot:{marker}",
        snapshot_content_hash="c" * 64,
        snapshot_created_at=(
            datetime(2026, 9, 2, 10, 0, tzinfo=UTC)
            if snapshot_created_at is None
            else snapshot_created_at
        ),
        market_export_content_hash="d" * 64,
        market_features_content_hash="e" * 64,
    )


def test_compile_thesis_suite_reuses_existing_experiment_and_semantic_contracts() -> None:
    suite = _suite()

    first = compile_thesis_suite(suite)
    second = compile_thesis_suite(suite)

    assert first == second
    assert first.suite_content_hash == canonical_model_hash(suite)
    assert first.experiment_manifest.schema_version == 1
    assert first.experiment_manifest.experiment_id == suite.suite_id
    assert first.experiment_manifest.context.model_dump() == suite.context.model_dump()
    assert tuple(item.id for item in first.experiment_manifest.families) == (
        "satisfying-destruction",
        "custom-digicam",
    )
    assert first.experiment_manifest.families[0].queries == suite.theses[0].queries
    assert first.experiment_manifest.families[1].queries == suite.theses[1].queries

    destruction, digicam = first.semantic_theses
    assert destruction.thesis_id == "satisfying-destruction"
    assert destruction.version == 1
    assert destruction.target_set_ids == (
        "next-microgame-candidates--satisfying-destruction",
    )
    assert destruction.theme.terms == ("предмет", "object")
    assert destruction.mechanic.terms == ("слом", "разб", "destroy", "break")
    assert destruction.reward_grammar is not None
    assert destruction.reward_grammar.terms == ("разруш", "damage", "destroyed")

    assert digicam.thesis_id == "custom-digicam"
    assert digicam.version == 2
    assert digicam.target_set_ids == ("next-microgame-candidates--custom-digicam",)
    assert digicam.reward_grammar is None


def test_suite_rejects_query_reuse_across_theses() -> None:
    suite = _suite()
    duplicated = suite.theses[1].model_copy(
        update={"queries": (suite.theses[0].queries[0], "custom digicam")}
    )

    with pytest.raises(ValidationError, match="exact query may belong to only one suite thesis"):
        ThesisSuiteDeclaration.model_validate(
            suite.model_copy(update={"theses": (suite.theses[0], duplicated)}).model_dump()
        )


def test_suite_reuses_semantic_rule_normalization_validation() -> None:
    with pytest.raises(ValidationError, match="unique after normalization"):
        ThesisSemanticDeclaration(theme_terms=("Object", "OBJECT"), mechanic_terms=("break",))


def test_empty_anomaly_policy_is_rejected_and_none_is_allowed() -> None:
    with pytest.raises(ValidationError, match="at least one gate"):
        ThesisAnomalyPolicy()

    suite = _suite().model_copy(update={"anomaly_policy": None})
    assert ThesisSuiteDeclaration.model_validate(suite.model_dump()).anomaly_policy is None


def test_build_inputs_canonicalize_history_and_review_order() -> None:
    suite = _suite()
    current = _binding(role="current", marker="1")
    earlier = _binding(
        role="prior",
        marker="2",
        experiment_id="older-sweep",
        run_id="20260831T100000Z",
        snapshot_created_at=datetime(2026, 8, 31, 10, 0, tzinfo=UTC),
    )
    later = _binding(
        role="prior",
        marker="3",
        experiment_id="later-sweep",
        run_id="20260901T100000Z",
        snapshot_created_at=datetime(2026, 9, 1, 10, 0, tzinfo=UTC),
    )
    reviews = (
        ThesisReviewBinding(
            thesis_id="custom-digicam",
            review_content_hash="4" * 64,
            semantic_report_content_hash="5" * 64,
        ),
        ThesisReviewBinding(
            thesis_id="satisfying-destruction",
            review_content_hash="6" * 64,
            semantic_report_content_hash="7" * 64,
        ),
    )

    inputs = build_intelligence_inputs(
        suite,
        current_experiment=current,
        prior_experiments=(later, earlier),
        review_bindings=reviews,
    )

    assert inputs.current_experiment == current
    assert inputs.prior_experiments == (earlier, later)
    assert tuple(item.thesis_id for item in inputs.review_bindings) == (
        "satisfying-destruction",
        "custom-digicam",
    )


def test_noncanonical_direct_build_inputs_are_rejected() -> None:
    current = _binding(role="current", marker="1")
    earlier = _binding(
        role="prior",
        marker="2",
        snapshot_created_at=datetime(2026, 8, 31, 10, 0, tzinfo=UTC),
    )
    later = _binding(
        role="prior",
        marker="3",
        snapshot_created_at=datetime(2026, 9, 1, 10, 0, tzinfo=UTC),
    )

    with pytest.raises(ValidationError, match="canonical history ordering"):
        ThesisIntelligenceBuildInputs(
            suite_content_hash="f" * 64,
            current_experiment=current,
            prior_experiments=(later, earlier),
        )


def test_build_inputs_reject_duplicate_history_and_unknown_review_thesis() -> None:
    suite = _suite()
    current = _binding(role="current", marker="1")
    prior = _binding(role="prior", marker="2")

    with pytest.raises(ThesisIntelligenceError, match="history artifact hashes must be unique"):
        build_intelligence_inputs(
            suite,
            current_experiment=current,
            prior_experiments=(prior, prior),
        )

    with pytest.raises(ThesisIntelligenceError, match="outside the suite"):
        build_intelligence_inputs(
            suite,
            current_experiment=current,
            review_bindings=(
                ThesisReviewBinding(
                    thesis_id="unknown-thesis",
                    review_content_hash="3" * 64,
                    semantic_report_content_hash="4" * 64,
                ),
            ),
        )


def test_current_binding_must_match_suite_and_role() -> None:
    suite = _suite()

    with pytest.raises(ThesisIntelligenceError, match="role=current"):
        build_intelligence_inputs(
            suite,
            current_experiment=_binding(role="prior", marker="1"),
        )

    with pytest.raises(ThesisIntelligenceError, match="experiment_id must match suite_id"):
        build_intelligence_inputs(
            suite,
            current_experiment=_binding(
                role="current",
                marker="1",
                experiment_id="another-experiment",
            ),
        )


def test_build_identity_is_deterministic_and_review_sensitive() -> None:
    suite = _suite()
    current = _binding(role="current", marker="1")
    review = ThesisReviewBinding(
        thesis_id="satisfying-destruction",
        review_content_hash="2" * 64,
        semantic_report_content_hash="3" * 64,
    )

    no_review = build_intelligence_identity(suite, current_experiment=current)
    no_review_again = build_intelligence_identity(suite, current_experiment=current)
    reviewed = build_intelligence_identity(
        suite,
        current_experiment=current,
        review_bindings=(review,),
    )

    assert no_review == no_review_again
    assert no_review.build_input_hash != reviewed.build_input_hash
    expected_suffix = f"/{no_review.build_input_hash}.zip"
    assert no_review.relative_artifact_path == (
        "artifacts/intelligence/next-microgame-candidates/"
        "20260902T100000Z/"
        f"{no_review.build_input_hash}.zip"
    )
    assert no_review.relative_artifact_path.endswith(expected_suffix)


def test_prior_cli_order_does_not_change_build_identity() -> None:
    suite = _suite()
    current = _binding(role="current", marker="1")
    earlier = _binding(
        role="prior",
        marker="2",
        snapshot_created_at=datetime(2026, 8, 31, 10, 0, tzinfo=UTC),
    )
    later = _binding(
        role="prior",
        marker="3",
        snapshot_created_at=datetime(2026, 9, 1, 10, 0, tzinfo=UTC),
    )

    left = build_intelligence_identity(
        suite,
        current_experiment=current,
        prior_experiments=(earlier, later),
    )
    right = build_intelligence_identity(
        suite,
        current_experiment=current,
        prior_experiments=(later, earlier),
    )

    assert left == right


def test_canonical_hash_normalizes_equivalent_timestamp_offsets() -> None:
    utc_binding = _binding(
        role="prior",
        marker="2",
        snapshot_created_at=datetime(2026, 9, 2, 10, 0, tzinfo=UTC),
    )
    plus_two_binding = utc_binding.model_copy(
        update={
            "snapshot_created_at": datetime(
                2026,
                9,
                2,
                12,
                0,
                tzinfo=timezone(timedelta(hours=2)),
            )
        }
    )

    assert canonical_model_hash(utc_binding) == canonical_model_hash(plus_two_binding)


def test_artifact_file_hash_validation_fails_closed(tmp_path: Path) -> None:
    artifact = tmp_path / "experiment.zip"
    artifact.write_bytes(b"frozen experiment bytes")

    import hashlib

    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    binding = _binding(role="current", marker="1").model_copy(
        update={"artifact_sha256": digest}
    )

    validate_artifact_file_sha256(binding, artifact)

    artifact.write_bytes(b"changed bytes")
    with pytest.raises(ThesisIntelligenceError, match="SHA-256 mismatch"):
        validate_artifact_file_sha256(binding, artifact)
