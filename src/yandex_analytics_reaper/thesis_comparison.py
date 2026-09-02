from __future__ import annotations

import csv
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from yandex_analytics_reaper.analyst import (
    AnalystSemanticEnrichmentReport,
    validate_analyst_semantic_enrichment,
)
from yandex_analytics_reaper.thesis_anomaly import (
    AnomalyEvaluationV1,
    AnomalyQueueStatusV1,
    FreshAnomalyQueueReport,
    ThesisAnomalyQueue,
    validate_fresh_anomaly_queue,
)
from yandex_analytics_reaper.thesis_directness import (
    AnalystDirectnessReviewReport,
    CompetitorQualityV1,
    build_competitor_quality,
    validate_directness_review,
)
from yandex_analytics_reaper.thesis_intelligence import (
    THESIS_INTELLIGENCE_METHOD_VERSION,
    ExperimentArtifactBinding,
    ThesisAnomalyPolicy,
    ThesisDeclaration,
    ThesisIntelligenceError,
    ThesisSuiteDeclaration,
    canonical_model_hash,
    compile_thesis_suite,
)
from yandex_analytics_reaper.thesis_traction import (
    BoundExperimentEvidence,
    ThesisTractionFeaturesReport,
    ThesisTractionRow,
    ThesisTractionSet,
    validate_traction_features,
)

THESIS_INTELLIGENCE_REPORT_SPEC_VERSION: Literal["thesis-intelligence-report-v1"] = (
    "thesis-intelligence-report-v1"
)
THESIS_COMPARISON_SPEC_VERSION: Literal["thesis-comparison-v1"] = "thesis-comparison-v1"

type ListingMetricNameV1 = Literal["rating_count", "lifetime_ratings_per_day"]


class ThesisIntelligencePayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: Literal["thesis-intelligence-report-v1"] = (
        THESIS_INTELLIGENCE_REPORT_SPEC_VERSION
    )
    method_version: Literal["thesis-intelligence-method-v1"] = THESIS_INTELLIGENCE_METHOD_VERSION
    suite_id: str
    suite_version: int = Field(ge=1)
    thesis_id: str
    thesis_version: int = Field(ge=1)
    label: str

    current_experiment: ExperimentArtifactBinding
    prior_experiments: tuple[ExperimentArtifactBinding, ...]
    comparable_set_id: str
    comparable_set_version: int = Field(ge=1)
    semantic_report_content_hash: str
    review_content_hash: str | None = None

    traction: tuple[ThesisTractionRow, ...] = Field(min_length=1)

    anomaly_policy: ThesisAnomalyPolicy | None
    anomaly_status: AnomalyQueueStatusV1
    anomaly_evaluations: tuple[AnomalyEvaluationV1, ...]
    anomaly_candidate_listing_ids: tuple[str, ...]

    competitor_quality: CompetitorQualityV1

    @field_validator("semantic_report_content_hash", "review_content_hash")
    @classmethod
    def validate_hash(cls, value: str | None) -> str | None:
        if value is not None:
            _require_sha256(value)
        return value

    @model_validator(mode="after")
    def validate_semantics(self) -> Self:
        if self.current_experiment.role != "current":
            raise ValueError("thesis report current experiment must have role=current")
        if any(item.role != "prior" for item in self.prior_experiments):
            raise ValueError("thesis report prior experiments must have role=prior")
        expected_priors = tuple(
            sorted(
                self.prior_experiments,
                key=lambda item: (
                    item.snapshot_created_at,
                    item.experiment_id,
                    item.run_id,
                    item.artifact_sha256,
                ),
            )
        )
        if self.prior_experiments != expected_priors:
            raise ValueError("thesis report prior experiments must use canonical order")
        prior_hashes = [item.artifact_sha256 for item in self.prior_experiments]
        if len(set(prior_hashes)) != len(prior_hashes):
            raise ValueError("thesis report prior experiment hashes must be unique")
        if self.current_experiment.artifact_sha256 in prior_hashes:
            raise ValueError("thesis report current artifact cannot also be prior")
        if self.comparable_set_version != 1:
            raise ValueError("thesis report v1 requires comparable_set_version=1")

        traction_ids = tuple(item.platform_listing_id for item in self.traction)
        if len(set(traction_ids)) != len(traction_ids):
            raise ValueError("thesis report traction listing IDs must be unique")
        if self.competitor_quality.raw_search_union_member_count != len(traction_ids):
            raise ValueError("competitor quality raw union must equal traction member count")

        if self.anomaly_policy is None:
            if self.anomaly_status != "disabled":
                raise ValueError("missing anomaly policy requires disabled status")
            if self.anomaly_evaluations or self.anomaly_candidate_listing_ids:
                raise ValueError("disabled anomaly report must not carry evaluations/candidates")
        else:
            if self.anomaly_status != "enabled":
                raise ValueError("configured anomaly policy requires enabled status")
            evaluation_ids = tuple(
                item.platform_listing_id for item in self.anomaly_evaluations
            )
            if evaluation_ids != traction_ids:
                raise ValueError("enabled anomaly evaluations must follow traction order")
            qualified = {
                item.platform_listing_id
                for item in self.anomaly_evaluations
                if item.is_anomaly_candidate
            }
            if set(self.anomaly_candidate_listing_ids) != qualified:
                raise ValueError("anomaly candidate IDs must equal qualifying evaluations")
            if len(set(self.anomaly_candidate_listing_ids)) != len(
                self.anomaly_candidate_listing_ids
            ):
                raise ValueError("anomaly candidate listing IDs must be unique")

        review_present = self.review_content_hash is not None
        if self.competitor_quality.review_artifact_present != review_present:
            raise ValueError(
                "review hash presence must match competitor-quality review presence"
            )
        return self


class ThesisIntelligenceReport(ThesisIntelligencePayload):
    content_hash: str

    @field_validator("content_hash")
    @classmethod
    def validate_content_hash(cls, value: str) -> str:
        _require_sha256(value)
        return value


class ListingMetricHighlightV1(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    platform_listing_id: str
    title: str | None
    metric_name: ListingMetricNameV1
    value: float
    observation_id: str | None
    status: Literal["observed"] = "observed"

    @field_validator("value")
    @classmethod
    def validate_finite_value(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("metric highlight value must be finite")
        return value


class ThesisComparisonRow(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    thesis_id: str
    thesis_version: int = Field(ge=1)
    label: str

    raw_union_members: int = Field(ge=1)
    semantic_coverage_ratio: float = Field(ge=0.0, le=1.0)
    direct_candidates: int = Field(ge=0)
    adjacent_candidates: int = Field(ge=0)
    confirmed_direct: int = Field(ge=0)
    unresolved_direct_review: int = Field(ge=0)

    fresh_confirmed_direct_180d: int = Field(ge=0)
    recent_release_180d_share: float | None = Field(default=None, ge=0.0, le=1.0)
    recent_release_coverage_ratio: float = Field(ge=0.0, le=1.0)

    best_confirmed_direct_rating_count: ListingMetricHighlightV1 | None
    best_confirmed_direct_lifetime_pace: ListingMetricHighlightV1 | None
    best_adjacent_rating_count: ListingMetricHighlightV1 | None

    anomaly_candidate_count: int = Field(ge=0)
    longitudinal_observed_count: int = Field(ge=0)
    longitudinal_coverage_ratio: float = Field(ge=0.0, le=1.0)

    mean_pairwise_query_jaccard: float | None = Field(default=None, ge=0.0, le=1.0)
    multi_query_member_share: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        if self.direct_candidates + self.adjacent_candidates > self.raw_union_members:
            raise ValueError("direct + adjacent candidates cannot exceed raw union")
        if self.confirmed_direct > self.direct_candidates:
            raise ValueError("confirmed direct cannot exceed semantic direct candidates")
        if self.unresolved_direct_review > self.direct_candidates:
            raise ValueError("unresolved direct review cannot exceed semantic direct candidates")
        if self.fresh_confirmed_direct_180d > self.confirmed_direct:
            raise ValueError("fresh confirmed direct cannot exceed confirmed direct")
        if self.anomaly_candidate_count > self.raw_union_members:
            raise ValueError("anomaly candidate count cannot exceed raw union")
        if self.longitudinal_observed_count > self.raw_union_members:
            raise ValueError("longitudinal observed count cannot exceed raw union")
        expected_longitudinal = self.longitudinal_observed_count / self.raw_union_members
        if self.longitudinal_coverage_ratio != expected_longitudinal:
            raise ValueError("longitudinal coverage ratio does not match counts")
        _validate_highlight_metric(
            self.best_confirmed_direct_rating_count,
            "rating_count",
        )
        _validate_highlight_metric(
            self.best_confirmed_direct_lifetime_pace,
            "lifetime_ratings_per_day",
        )
        _validate_highlight_metric(self.best_adjacent_rating_count, "rating_count")
        return self


class ThesisComparisonPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: Literal["thesis-comparison-v1"] = THESIS_COMPARISON_SPEC_VERSION
    suite_id: str
    suite_version: int = Field(ge=1)
    current_experiment_artifact_sha256: str
    prior_experiment_artifact_sha256s: tuple[str, ...]
    thesis_report_hashes: tuple[str, ...] = Field(min_length=1)
    rows: tuple[ThesisComparisonRow, ...] = Field(min_length=1)

    @field_validator(
        "current_experiment_artifact_sha256",
        "prior_experiment_artifact_sha256s",
        "thesis_report_hashes",
    )
    @classmethod
    def validate_hashes(
        cls,
        value: str | tuple[str, ...],
    ) -> str | tuple[str, ...]:
        if isinstance(value, str):
            _require_sha256(value)
        else:
            for item in value:
                _require_sha256(item)
        return value

    @model_validator(mode="after")
    def validate_shape(self) -> Self:
        if len(self.thesis_report_hashes) != len(self.rows):
            raise ValueError(
                "comparison thesis report hashes must align one-to-one with rows"
            )
        ids = [item.thesis_id for item in self.rows]
        if len(set(ids)) != len(ids):
            raise ValueError("comparison thesis IDs must be unique")
        if len(set(self.prior_experiment_artifact_sha256s)) != len(
            self.prior_experiment_artifact_sha256s
        ):
            raise ValueError("comparison prior artifact hashes must be unique")
        return self


class ThesisComparisonReport(ThesisComparisonPayload):
    content_hash: str

    @field_validator("content_hash")
    @classmethod
    def validate_content_hash(cls, value: str) -> str:
        _require_sha256(value)
        return value


def build_thesis_intelligence_reports(
    suite: ThesisSuiteDeclaration,
    *,
    current: BoundExperimentEvidence,
    traction: ThesisTractionFeaturesReport,
    anomaly: FreshAnomalyQueueReport,
    semantic_reports: Sequence[AnalystSemanticEnrichmentReport],
    reviews: Sequence[AnalystDirectnessReviewReport] = (),
) -> tuple[ThesisIntelligenceReport, ...]:
    """Bind P2/P3/P4 evidence into one canonical report per thesis."""
    suite = ThesisSuiteDeclaration.model_validate(suite.model_dump())
    current = BoundExperimentEvidence.model_validate(current.model_dump())
    traction = validate_traction_features(traction)
    anomaly = validate_fresh_anomaly_queue(anomaly)

    suite_hash = canonical_model_hash(suite)
    if (
        traction.suite_id != suite.suite_id
        or traction.suite_version != suite.suite_version
        or traction.suite_content_hash != suite_hash
    ):
        raise ThesisIntelligenceError("traction report does not bind supplied thesis suite")
    if current.binding != traction.current_experiment:
        raise ThesisIntelligenceError(
            "current evidence binding does not equal traction binding"
        )
    if (
        anomaly.suite_id != suite.suite_id
        or anomaly.suite_version != suite.suite_version
        or anomaly.suite_content_hash != suite_hash
        or anomaly.traction_report_content_hash != traction.content_hash
    ):
        raise ThesisIntelligenceError(
            "anomaly report does not bind supplied suite/traction"
        )

    semantic_by_id = _semantic_reports_by_thesis(suite, semantic_reports)
    review_by_id = _reviews_by_thesis(suite, semantic_by_id, reviews)
    traction_by_id = _traction_sets_by_thesis(suite, traction)
    anomaly_by_id = _anomaly_queues_by_thesis(suite, anomaly)

    reports: list[ThesisIntelligenceReport] = []
    for thesis in suite.theses:
        semantic = semantic_by_id[thesis.thesis_id]
        review = review_by_id.get(thesis.thesis_id)
        traction_set = traction_by_id[thesis.thesis_id]
        anomaly_queue = anomaly_by_id[thesis.thesis_id]

        if (
            semantic.snapshot_id != current.snapshot.snapshot_id
            or semantic.snapshot_content_hash != current.snapshot.content_hash
        ):
            raise ThesisIntelligenceError(
                f"semantic report for {thesis.thesis_id} does not bind current snapshot"
            )
        expected_set_id = f"{suite.suite_id}--{thesis.thesis_id}"
        if semantic.thesis.target_set_ids != (expected_set_id,):
            raise ThesisIntelligenceError(
                f"semantic report for {thesis.thesis_id} targets the wrong comparable"
            )
        traction_ids = tuple(item.platform_listing_id for item in traction_set.rows)
        semantic_ids = tuple(item.platform_listing_id for item in semantic.listings)
        if semantic_ids != traction_ids:
            raise ThesisIntelligenceError(
                f"semantic/traction listing order differs for thesis {thesis.thesis_id}"
            )

        quality = build_competitor_quality(
            suite,
            semantic,
            current.market_export,
            review=review,
        )
        reports.append(
            _build_one_thesis_report(
                suite=suite,
                thesis=thesis,
                traction=traction,
                traction_set=traction_set,
                anomaly_queue=anomaly_queue,
                semantic=semantic,
                review=review,
                quality=quality,
            )
        )
    return tuple(reports)


def build_thesis_comparison(
    suite: ThesisSuiteDeclaration,
    *,
    thesis_reports: Sequence[ThesisIntelligenceReport],
    semantic_reports: Sequence[AnalystSemanticEnrichmentReport],
    reviews: Sequence[AnalystDirectnessReviewReport] = (),
) -> ThesisComparisonReport:
    """Create declaration-order descriptive comparison without ranking or recommendation."""
    suite = ThesisSuiteDeclaration.model_validate(suite.model_dump())
    reports = tuple(
        validate_thesis_intelligence_report(item) for item in thesis_reports
    )
    expected_ids = tuple(item.thesis_id for item in suite.theses)
    actual_ids = tuple(item.thesis_id for item in reports)
    if actual_ids != expected_ids:
        raise ThesisIntelligenceError(
            "thesis report order/identity does not match suite"
        )

    semantic_by_id = _semantic_reports_by_thesis(suite, semantic_reports)
    review_by_id = _reviews_by_thesis(suite, semantic_by_id, reviews)

    current_hashes = {item.current_experiment.artifact_sha256 for item in reports}
    if len(current_hashes) != 1:
        raise ThesisIntelligenceError(
            "thesis reports do not share one current experiment artifact"
        )
    canonical_prior_hashes = tuple(
        item.artifact_sha256 for item in reports[0].prior_experiments
    )
    for report in reports:
        report_prior_hashes = tuple(
            item.artifact_sha256 for item in report.prior_experiments
        )
        if report_prior_hashes != canonical_prior_hashes:
            raise ThesisIntelligenceError(
                "thesis reports do not share canonical prior artifacts"
            )

    rows: list[ThesisComparisonRow] = []
    for thesis, report in zip(suite.theses, reports, strict=True):
        semantic = semantic_by_id[thesis.thesis_id]
        if report.semantic_report_content_hash != semantic.content_hash:
            raise ThesisIntelligenceError(
                "thesis report semantic hash does not match supplied report"
            )
        review = review_by_id.get(thesis.thesis_id)
        review_hash = None if review is None else review.content_hash
        if review_hash != report.review_content_hash:
            raise ThesisIntelligenceError(
                "thesis report review hash does not match supplied review"
            )
        _validate_report_against_semantic_and_review(report, semantic, review)
        rows.append(_comparison_row(thesis, report, semantic, review))

    payload = ThesisComparisonPayload(
        suite_id=suite.suite_id,
        suite_version=suite.suite_version,
        current_experiment_artifact_sha256=next(iter(current_hashes)),
        prior_experiment_artifact_sha256s=canonical_prior_hashes,
        thesis_report_hashes=tuple(item.content_hash for item in reports),
        rows=tuple(rows),
    )
    report = ThesisComparisonReport(
        **payload.model_dump(mode="python"),
        content_hash=canonical_model_hash(payload),
    )
    return validate_thesis_comparison(
        report,
        suite=suite,
        thesis_reports=reports,
    )


def validate_thesis_intelligence_report(
    report: ThesisIntelligenceReport,
) -> ThesisIntelligenceReport:
    report = ThesisIntelligenceReport.model_validate(report.model_dump())
    payload = ThesisIntelligencePayload.model_validate(
        report.model_dump(exclude={"content_hash"})
    )
    if report.content_hash != canonical_model_hash(payload):
        raise ThesisIntelligenceError(
            "thesis intelligence report content_hash mismatch"
        )
    return report


def validate_thesis_comparison(
    report: ThesisComparisonReport,
    *,
    suite: ThesisSuiteDeclaration | None = None,
    thesis_reports: Sequence[ThesisIntelligenceReport] | None = None,
) -> ThesisComparisonReport:
    report = ThesisComparisonReport.model_validate(report.model_dump())
    payload = ThesisComparisonPayload.model_validate(
        report.model_dump(exclude={"content_hash"})
    )
    if report.content_hash != canonical_model_hash(payload):
        raise ThesisIntelligenceError("thesis comparison content_hash mismatch")
    if suite is not None:
        suite = ThesisSuiteDeclaration.model_validate(suite.model_dump())
        expected = tuple(
            (item.thesis_id, item.thesis_version, item.label) for item in suite.theses
        )
        actual = tuple(
            (item.thesis_id, item.thesis_version, item.label) for item in report.rows
        )
        if (
            report.suite_id != suite.suite_id
            or report.suite_version != suite.suite_version
            or actual != expected
        ):
            raise ThesisIntelligenceError(
                "comparison rows do not match suite declaration order"
            )
    if thesis_reports is not None:
        reports = tuple(
            validate_thesis_intelligence_report(item) for item in thesis_reports
        )
        expected_hashes = tuple(item.content_hash for item in reports)
        if report.thesis_report_hashes != expected_hashes:
            raise ThesisIntelligenceError(
                "comparison thesis report hashes do not match reports"
            )
    return report


def write_thesis_intelligence_json(
    report: ThesisIntelligenceReport,
    path: Path,
) -> None:
    report = validate_thesis_intelligence_report(report)
    _write_create_only(path, report.model_dump_json(indent=2) + "\n")


def write_thesis_intelligence_csv(
    report: ThesisIntelligenceReport,
    path: Path,
) -> None:
    report = validate_thesis_intelligence_report(report)
    rows: list[dict[str, object]] = []
    evaluations = {
        item.platform_listing_id: item for item in report.anomaly_evaluations
    }
    candidates = set(report.anomaly_candidate_listing_ids)
    for row in report.traction:
        evaluation = evaluations.get(row.platform_listing_id)
        rows.append(
            {
                "platform_listing_id": row.platform_listing_id,
                "title": row.title,
                "listing_age_days": row.listing_age_days,
                "age_bucket": row.age_bucket,
                "rating_count": row.rating_count,
                "lifetime_ratings_per_day": row.lifetime_ratings_per_day,
                "suite_age_bucket_percentile": row.suite_age_bucket_percentile,
                "longitudinal_status": row.longitudinal.status,
                "observed_rating_delta_per_day": (
                    row.longitudinal.observed_rating_delta_per_day
                ),
                "anomaly_candidate": row.platform_listing_id in candidates,
                "anomaly_max_age": (
                    None if evaluation is None else evaluation.max_age_days_status
                ),
                "anomaly_min_rating_count": (
                    None
                    if evaluation is None
                    else evaluation.min_rating_count_status
                ),
                "anomaly_min_lifetime_pace": (
                    None
                    if evaluation is None
                    else evaluation.min_lifetime_ratings_per_day_status
                ),
                "anomaly_min_age_bucket_percentile": (
                    None
                    if evaluation is None
                    else evaluation.min_age_bucket_percentile_status
                ),
                "anomaly_min_observed_delta": (
                    None
                    if evaluation is None
                    else evaluation.min_observed_rating_delta_per_day_status
                ),
            }
        )
    _write_csv_create_only(path, rows)


def write_thesis_comparison_json(
    report: ThesisComparisonReport,
    path: Path,
) -> None:
    report = validate_thesis_comparison(report)
    _write_create_only(path, report.model_dump_json(indent=2) + "\n")


def write_thesis_comparison_csv(
    report: ThesisComparisonReport,
    path: Path,
) -> None:
    report = validate_thesis_comparison(report)
    rows: list[dict[str, object]] = []
    for row in report.rows:
        record = row.model_dump(
            mode="json",
            exclude={
                "best_confirmed_direct_rating_count",
                "best_confirmed_direct_lifetime_pace",
                "best_adjacent_rating_count",
            },
        )
        _flatten_highlight(
            record,
            "best_confirmed_direct_rating_count",
            row.best_confirmed_direct_rating_count,
        )
        _flatten_highlight(
            record,
            "best_confirmed_direct_lifetime_pace",
            row.best_confirmed_direct_lifetime_pace,
        )
        _flatten_highlight(
            record,
            "best_adjacent_rating_count",
            row.best_adjacent_rating_count,
        )
        rows.append(record)
    _write_csv_create_only(path, rows)


def write_thesis_comparison_markdown(
    report: ThesisComparisonReport,
    path: Path,
) -> None:
    report = validate_thesis_comparison(report)
    header = (
        "| Thesis | Raw | Direct | Confirmed | Fresh confirmed <=180d | Anomalies | "
        "Semantic coverage | Longitudinal coverage | Mean query Jaccard |"
    )
    lines = [
        "# Thesis comparison",
        "",
        "Descriptive evidence only. Rows follow suite declaration order; no winner is implied.",
        "",
        header,
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in report.rows:
        lines.append(
            "| "
            + " | ".join(
                (
                    row.label,
                    str(row.raw_union_members),
                    str(row.direct_candidates),
                    str(row.confirmed_direct),
                    str(row.fresh_confirmed_direct_180d),
                    str(row.anomaly_candidate_count),
                    _format_ratio(row.semantic_coverage_ratio),
                    _format_ratio(row.longitudinal_coverage_ratio),
                    _format_optional_ratio(row.mean_pairwise_query_jaccard),
                )
            )
            + " |"
        )
    lines.append("")
    _write_create_only(path, "\n".join(lines))


def _build_one_thesis_report(
    *,
    suite: ThesisSuiteDeclaration,
    thesis: ThesisDeclaration,
    traction: ThesisTractionFeaturesReport,
    traction_set: ThesisTractionSet,
    anomaly_queue: ThesisAnomalyQueue,
    semantic: AnalystSemanticEnrichmentReport,
    review: AnalystDirectnessReviewReport | None,
    quality: CompetitorQualityV1,
) -> ThesisIntelligenceReport:
    traction_ids = tuple(item.platform_listing_id for item in traction_set.rows)
    if anomaly_queue.status == "enabled":
        evaluation_ids = tuple(
            item.platform_listing_id for item in anomaly_queue.evaluations
        )
        if evaluation_ids != traction_ids:
            raise ThesisIntelligenceError(
                "anomaly evaluations do not follow thesis traction order"
            )
    candidate_ids = tuple(
        item.platform_listing_id for item in anomaly_queue.candidates
    )

    payload = ThesisIntelligencePayload(
        suite_id=suite.suite_id,
        suite_version=suite.suite_version,
        thesis_id=thesis.thesis_id,
        thesis_version=thesis.thesis_version,
        label=thesis.label,
        current_experiment=traction.current_experiment,
        prior_experiments=traction.prior_experiments,
        comparable_set_id=traction_set.comparable_set_id,
        comparable_set_version=traction_set.comparable_set_version,
        semantic_report_content_hash=semantic.content_hash,
        review_content_hash=None if review is None else review.content_hash,
        traction=traction_set.rows,
        anomaly_policy=suite.anomaly_policy,
        anomaly_status=anomaly_queue.status,
        anomaly_evaluations=anomaly_queue.evaluations,
        anomaly_candidate_listing_ids=candidate_ids,
        competitor_quality=quality,
    )
    report = ThesisIntelligenceReport(
        **payload.model_dump(mode="python"),
        content_hash=canonical_model_hash(payload),
    )
    return validate_thesis_intelligence_report(report)


def _comparison_row(
    thesis: ThesisDeclaration,
    report: ThesisIntelligenceReport,
    semantic: AnalystSemanticEnrichmentReport,
    review: AnalystDirectnessReviewReport | None,
) -> ThesisComparisonRow:
    traction_by_id = {
        item.platform_listing_id: item for item in report.traction
    }
    order = {
        item.platform_listing_id: index
        for index, item in enumerate(report.traction)
    }

    confirmed_ids: set[str] = set()
    if review is not None:
        confirmed_ids = {
            item.platform_listing_id
            for item in review.rows
            if item.analyst_verdict == "confirmed_direct"
        }
    adjacent_ids = {
        item.platform_listing_id
        for item in semantic.listings
        if item.directness == "adjacent_candidate"
    }

    fresh_confirmed = sum(
        _is_fresh_180d(traction_by_id[listing_id])
        for listing_id in confirmed_ids
    )
    age_values = [
        age
        for item in report.traction
        if (age := item.listing_age_days) is not None
    ]
    recent = sum(age <= 180.0 for age in age_values)
    recent_share = None if not age_values else recent / len(age_values)
    recent_coverage = len(age_values) / len(report.traction)

    longitudinal_observed = sum(
        item.longitudinal.status in {"observed", "negative_revision"}
        for item in report.traction
    )

    quality = report.competitor_quality
    return ThesisComparisonRow(
        thesis_id=thesis.thesis_id,
        thesis_version=thesis.thesis_version,
        label=thesis.label,
        raw_union_members=quality.raw_search_union_member_count,
        semantic_coverage_ratio=quality.semantic_source_coverage_ratio,
        direct_candidates=quality.semantic_direct_candidate_count,
        adjacent_candidates=quality.semantic_adjacent_candidate_count,
        confirmed_direct=quality.confirmed_direct_count,
        unresolved_direct_review=quality.unresolved_direct_candidate_count,
        fresh_confirmed_direct_180d=fresh_confirmed,
        recent_release_180d_share=recent_share,
        recent_release_coverage_ratio=recent_coverage,
        best_confirmed_direct_rating_count=_best_highlight(
            confirmed_ids,
            traction_by_id,
            order,
            metric_name="rating_count",
        ),
        best_confirmed_direct_lifetime_pace=_best_highlight(
            confirmed_ids,
            traction_by_id,
            order,
            metric_name="lifetime_ratings_per_day",
        ),
        best_adjacent_rating_count=_best_highlight(
            adjacent_ids,
            traction_by_id,
            order,
            metric_name="rating_count",
        ),
        anomaly_candidate_count=len(report.anomaly_candidate_listing_ids),
        longitudinal_observed_count=longitudinal_observed,
        longitudinal_coverage_ratio=longitudinal_observed / len(report.traction),
        mean_pairwise_query_jaccard=(
            quality.query_surface.mean_pairwise_jaccard
        ),
        multi_query_member_share=quality.query_surface.multi_query_member_share,
    )


def _validate_report_against_semantic_and_review(
    report: ThesisIntelligenceReport,
    semantic: AnalystSemanticEnrichmentReport,
    review: AnalystDirectnessReviewReport | None,
) -> None:
    traction_ids = tuple(item.platform_listing_id for item in report.traction)
    semantic_ids = tuple(item.platform_listing_id for item in semantic.listings)
    if traction_ids != semantic_ids:
        raise ThesisIntelligenceError(
            "thesis report traction order does not match semantic comparable order"
        )
    direct = sum(item.directness == "direct_candidate" for item in semantic.listings)
    adjacent = sum(item.directness == "adjacent_candidate" for item in semantic.listings)
    quality = report.competitor_quality
    if (
        quality.semantic_direct_candidate_count != direct
        or quality.semantic_adjacent_candidate_count != adjacent
    ):
        raise ThesisIntelligenceError(
            "thesis report competitor quality disagrees with semantic directness"
        )

    review_rows = () if review is None else review.rows
    confirmed = sum(
        item.analyst_verdict == "confirmed_direct" for item in review_rows
    )
    unresolved = sum(item.analyst_verdict == "unresolved" for item in review_rows)
    if (
        quality.confirmed_direct_count != confirmed
        or quality.unresolved_direct_candidate_count != unresolved
    ):
        raise ThesisIntelligenceError(
            "thesis report competitor quality disagrees with directness review"
        )


def _best_highlight(
    listing_ids: set[str],
    traction_by_id: Mapping[str, ThesisTractionRow],
    order: Mapping[str, int],
    *,
    metric_name: ListingMetricNameV1,
) -> ListingMetricHighlightV1 | None:
    candidates: list[tuple[float, int, ThesisTractionRow]] = []
    for listing_id in listing_ids:
        row = traction_by_id.get(listing_id)
        if row is None:
            raise ThesisIntelligenceError(
                "highlight listing is outside thesis comparable"
            )
        raw_value = (
            row.rating_count
            if metric_name == "rating_count"
            else row.lifetime_ratings_per_day
        )
        if raw_value is None:
            continue
        value = float(raw_value)
        if not math.isfinite(value):
            raise ThesisIntelligenceError("highlight metric is not finite")
        candidates.append((value, order[listing_id], row))
    if not candidates:
        return None
    _, _, best = max(candidates, key=lambda item: (item[0], -item[1]))
    if metric_name == "rating_count":
        if best.rating_count is None:
            raise ThesisIntelligenceError(
                "selected rating-count highlight unexpectedly lacks value"
            )
        value = float(best.rating_count)
        observation_id = best.rating_count_observation_id
    else:
        if best.lifetime_ratings_per_day is None:
            raise ThesisIntelligenceError(
                "selected lifetime-pace highlight unexpectedly lacks value"
            )
        value = best.lifetime_ratings_per_day
        observation_id = None
    return ListingMetricHighlightV1(
        platform_listing_id=best.platform_listing_id,
        title=best.title,
        metric_name=metric_name,
        value=value,
        observation_id=observation_id,
    )


def _semantic_reports_by_thesis(
    suite: ThesisSuiteDeclaration,
    reports: Sequence[AnalystSemanticEnrichmentReport],
) -> dict[str, AnalystSemanticEnrichmentReport]:
    expected = {item.thesis_id for item in suite.theses}
    by_id: dict[str, AnalystSemanticEnrichmentReport] = {}
    compiled = {
        item.thesis_id: item for item in compile_thesis_suite(suite).semantic_theses
    }
    for source_report in reports:
        report = validate_analyst_semantic_enrichment(source_report)
        thesis_id = report.thesis.thesis_id
        if thesis_id not in expected:
            raise ThesisIntelligenceError(
                "semantic report references thesis outside suite"
            )
        if thesis_id in by_id:
            raise ThesisIntelligenceError("duplicate semantic report for thesis")
        if report.thesis != compiled[thesis_id]:
            raise ThesisIntelligenceError(
                "semantic report declaration does not equal suite compile"
            )
        by_id[thesis_id] = report
    if set(by_id) != expected:
        raise ThesisIntelligenceError(
            "one semantic report is required for every suite thesis"
        )
    return by_id


def _reviews_by_thesis(
    suite: ThesisSuiteDeclaration,
    semantics: Mapping[str, AnalystSemanticEnrichmentReport],
    reviews: Sequence[AnalystDirectnessReviewReport],
) -> dict[str, AnalystDirectnessReviewReport]:
    by_id: dict[str, AnalystDirectnessReviewReport] = {}
    for review in reviews:
        thesis_id = review.thesis_id
        if thesis_id not in semantics:
            raise ThesisIntelligenceError(
                "review references thesis outside semantic report set"
            )
        if thesis_id in by_id:
            raise ThesisIntelligenceError("duplicate directness review for thesis")
        by_id[thesis_id] = validate_directness_review(
            review,
            suite=suite,
            semantic_report=semantics[thesis_id],
        )
    return by_id


def _traction_sets_by_thesis(
    suite: ThesisSuiteDeclaration,
    traction: ThesisTractionFeaturesReport,
) -> dict[str, ThesisTractionSet]:
    expected = tuple(
        (item.thesis_id, item.thesis_version) for item in suite.theses
    )
    actual = tuple(
        (item.thesis_id, item.thesis_version) for item in traction.theses
    )
    if actual != expected:
        raise ThesisIntelligenceError(
            "traction thesis order/identity does not match suite"
        )
    return {item.thesis_id: item for item in traction.theses}


def _anomaly_queues_by_thesis(
    suite: ThesisSuiteDeclaration,
    anomaly: FreshAnomalyQueueReport,
) -> dict[str, ThesisAnomalyQueue]:
    expected = tuple(
        (item.thesis_id, item.thesis_version) for item in suite.theses
    )
    actual = tuple(
        (item.thesis_id, item.thesis_version) for item in anomaly.theses
    )
    if actual != expected:
        raise ThesisIntelligenceError(
            "anomaly thesis order/identity does not match suite"
        )
    return {item.thesis_id: item for item in anomaly.theses}


def _validate_highlight_metric(
    highlight: ListingMetricHighlightV1 | None,
    metric_name: ListingMetricNameV1,
) -> None:
    if highlight is not None and highlight.metric_name != metric_name:
        raise ValueError(
            "comparison highlight metric name does not match field"
        )


def _is_fresh_180d(row: ThesisTractionRow) -> bool:
    return row.listing_age_days is not None and row.listing_age_days <= 180.0


def _flatten_highlight(
    record: dict[str, object],
    prefix: str,
    highlight: ListingMetricHighlightV1 | None,
) -> None:
    record[f"{prefix}_listing_id"] = (
        None if highlight is None else highlight.platform_listing_id
    )
    record[f"{prefix}_title"] = None if highlight is None else highlight.title
    record[f"{prefix}_value"] = None if highlight is None else highlight.value
    record[f"{prefix}_observation_id"] = (
        None if highlight is None else highlight.observation_id
    )


def _write_csv_create_only(
    path: Path,
    rows: list[dict[str, object]],
) -> None:
    if not rows:
        raise ThesisIntelligenceError("CSV output requires at least one row")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.open("x", encoding="utf-8", newline="")
    except FileExistsError as exc:
        raise ThesisIntelligenceError(f"output already exists: {path}") from exc
    except OSError as exc:
        raise ThesisIntelligenceError(str(exc)) from exc
    with handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _write_create_only(path: Path, content: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.open("x", encoding="utf-8", newline="")
    except FileExistsError as exc:
        raise ThesisIntelligenceError(f"output already exists: {path}") from exc
    except OSError as exc:
        raise ThesisIntelligenceError(str(exc)) from exc
    with handle:
        handle.write(content)


def _format_ratio(value: float) -> str:
    return f"{value:.3f}"


def _format_optional_ratio(value: float | None) -> str:
    return "—" if value is None else _format_ratio(value)


def _require_sha256(value: str) -> None:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError("value must be a lowercase SHA-256 hex digest")
