from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from yandex_analytics_reaper.thesis_intelligence import (
    ThesisAnomalyPolicy,
    ThesisIntelligenceError,
    ThesisSuiteDeclaration,
    canonical_model_hash,
)
from yandex_analytics_reaper.thesis_traction import (
    ThesisTractionFeaturesReport,
    ThesisTractionRow,
    validate_traction_features,
)

FRESH_ANOMALY_QUEUE_SPEC_VERSION: Literal["fresh-anomaly-queue-v1"] = (
    "fresh-anomaly-queue-v1"
)

type AnomalyGateStatusV1 = Literal["pass", "fail", "unknown", "not_configured"]
type AnomalyQueueStatusV1 = Literal["enabled", "disabled"]


class AnomalyEvaluationV1(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    platform_listing_id: str
    max_age_days_status: AnomalyGateStatusV1
    min_rating_count_status: AnomalyGateStatusV1
    min_lifetime_ratings_per_day_status: AnomalyGateStatusV1
    min_age_bucket_percentile_status: AnomalyGateStatusV1
    min_observed_rating_delta_per_day_status: AnomalyGateStatusV1
    is_anomaly_candidate: bool

    @model_validator(mode="after")
    def validate_candidate_state(self) -> Self:
        statuses = (
            self.max_age_days_status,
            self.min_rating_count_status,
            self.min_lifetime_ratings_per_day_status,
            self.min_age_bucket_percentile_status,
            self.min_observed_rating_delta_per_day_status,
        )
        configured = tuple(status for status in statuses if status != "not_configured")
        if not configured:
            raise ValueError("enabled anomaly evaluation requires at least one configured gate")
        if self.is_anomaly_candidate != all(status == "pass" for status in configured):
            raise ValueError("anomaly candidate flag does not match configured gate statuses")
        return self


class AnomalyCandidateV1(BaseModel):
    """Review-queue entry carrying the exact descriptive facts used for v1 ordering."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    platform_listing_id: str
    lifetime_ratings_per_day: float | None = Field(default=None, ge=0.0)
    rating_count: int | None = Field(default=None, ge=0)
    listing_age_days: float | None = Field(default=None, ge=0.0)


class ThesisAnomalyQueue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    thesis_id: str
    thesis_version: int = Field(ge=1)
    status: AnomalyQueueStatusV1
    evaluations: tuple[AnomalyEvaluationV1, ...]
    candidates: tuple[AnomalyCandidateV1, ...]

    @model_validator(mode="after")
    def validate_queue(self) -> Self:
        evaluation_ids = [item.platform_listing_id for item in self.evaluations]
        if len(set(evaluation_ids)) != len(evaluation_ids):
            raise ValueError("anomaly evaluations must have unique listing IDs")
        candidate_ids = [item.platform_listing_id for item in self.candidates]
        if len(set(candidate_ids)) != len(candidate_ids):
            raise ValueError("anomaly candidate listing IDs must be unique")
        if self.status == "disabled":
            if self.evaluations or self.candidates:
                raise ValueError("disabled anomaly queue must be empty")
            return self

        qualified_ids = {
            item.platform_listing_id
            for item in self.evaluations
            if item.is_anomaly_candidate
        }
        if set(candidate_ids) != qualified_ids:
            raise ValueError("candidate queue must contain exactly qualifying evaluations")
        if self.candidates != tuple(sorted(self.candidates, key=_candidate_sort_key)):
            raise ValueError("anomaly candidates do not follow frozen v1 queue ordering")
        return self


class FreshAnomalyQueuePayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: Literal["fresh-anomaly-queue-v1"] = FRESH_ANOMALY_QUEUE_SPEC_VERSION
    suite_id: str
    suite_version: int = Field(ge=1)
    suite_content_hash: str
    traction_report_content_hash: str
    status: AnomalyQueueStatusV1
    policy: ThesisAnomalyPolicy | None
    theses: tuple[ThesisAnomalyQueue, ...] = Field(min_length=1)

    @field_validator("suite_content_hash", "traction_report_content_hash")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        invalid = any(character not in "0123456789abcdef" for character in value)
        if len(value) != 64 or invalid:
            raise ValueError("anomaly report hashes must be lowercase SHA-256 digests")
        return value

    @model_validator(mode="after")
    def validate_status(self) -> Self:
        expected: AnomalyQueueStatusV1 = "disabled" if self.policy is None else "enabled"
        if self.status != expected:
            raise ValueError("anomaly report status does not match policy presence")
        if any(item.status != self.status for item in self.theses):
            raise ValueError("all thesis anomaly queues must match report status")
        return self


class FreshAnomalyQueueReport(FreshAnomalyQueuePayload):
    content_hash: str

    @field_validator("content_hash")
    @classmethod
    def validate_content_hash(cls, value: str) -> str:
        invalid = any(character not in "0123456789abcdef" for character in value)
        if len(value) != 64 or invalid:
            raise ValueError("content_hash must be a lowercase SHA-256 digest")
        return value


def build_fresh_anomaly_queue(
    suite: ThesisSuiteDeclaration,
    traction: ThesisTractionFeaturesReport,
) -> FreshAnomalyQueueReport:
    """Apply only explicit suite policy gates to frozen P2 traction rows."""
    suite = ThesisSuiteDeclaration.model_validate(suite.model_dump())
    traction = validate_traction_features(traction)

    suite_hash = canonical_model_hash(suite)
    if (
        traction.suite_id != suite.suite_id
        or traction.suite_version != suite.suite_version
        or traction.suite_content_hash != suite_hash
    ):
        raise ThesisIntelligenceError("traction report does not bind the supplied thesis suite")

    expected_theses = tuple((item.thesis_id, item.thesis_version) for item in suite.theses)
    actual_theses = tuple((item.thesis_id, item.thesis_version) for item in traction.theses)
    if actual_theses != expected_theses:
        raise ThesisIntelligenceError("traction thesis order/identity does not match suite")

    policy = suite.anomaly_policy
    status: AnomalyQueueStatusV1 = "disabled" if policy is None else "enabled"
    thesis_queues: list[ThesisAnomalyQueue] = []
    for traction_set in traction.theses:
        if policy is None:
            thesis_queues.append(
                ThesisAnomalyQueue(
                    thesis_id=traction_set.thesis_id,
                    thesis_version=traction_set.thesis_version,
                    status="disabled",
                    evaluations=(),
                    candidates=(),
                )
            )
            continue

        evaluations = tuple(_evaluate_row(row, policy) for row in traction_set.rows)
        evaluation_by_id = {item.platform_listing_id: item for item in evaluations}
        candidates = tuple(
            sorted(
                (
                    _candidate_from_row(row)
                    for row in traction_set.rows
                    if evaluation_by_id[row.platform_listing_id].is_anomaly_candidate
                ),
                key=_candidate_sort_key,
            )
        )
        thesis_queues.append(
            ThesisAnomalyQueue(
                thesis_id=traction_set.thesis_id,
                thesis_version=traction_set.thesis_version,
                status="enabled",
                evaluations=evaluations,
                candidates=candidates,
            )
        )

    payload = FreshAnomalyQueuePayload(
        suite_id=suite.suite_id,
        suite_version=suite.suite_version,
        suite_content_hash=suite_hash,
        traction_report_content_hash=traction.content_hash,
        status=status,
        policy=policy,
        theses=tuple(thesis_queues),
    )
    report = FreshAnomalyQueueReport(
        **payload.model_dump(mode="python"),
        content_hash=canonical_model_hash(payload),
    )
    return validate_fresh_anomaly_queue(report)


def validate_fresh_anomaly_queue(
    report: FreshAnomalyQueueReport,
) -> FreshAnomalyQueueReport:
    report = FreshAnomalyQueueReport.model_validate(report.model_dump())
    payload = FreshAnomalyQueuePayload.model_validate(
        report.model_dump(exclude={"content_hash"})
    )
    if report.content_hash != canonical_model_hash(payload):
        raise ThesisIntelligenceError("fresh anomaly queue content_hash mismatch")
    return report


def _evaluate_row(
    row: ThesisTractionRow,
    policy: ThesisAnomalyPolicy,
) -> AnomalyEvaluationV1:
    max_age_status = _maximum_gate(row.listing_age_days, policy.max_age_days)
    rating_status = _minimum_gate(row.rating_count, policy.min_rating_count)
    lifetime_status = _minimum_gate(
        row.lifetime_ratings_per_day,
        policy.min_lifetime_ratings_per_day,
    )
    percentile_status = _minimum_gate(
        row.suite_age_bucket_percentile,
        policy.min_age_bucket_percentile,
    )
    delta_status = _observed_delta_gate(
        row,
        policy.min_observed_rating_delta_per_day,
    )
    statuses = (
        max_age_status,
        rating_status,
        lifetime_status,
        percentile_status,
        delta_status,
    )
    configured = tuple(value for value in statuses if value != "not_configured")
    if not configured:
        raise ThesisIntelligenceError("anomaly policy unexpectedly has no configured gates")
    return AnomalyEvaluationV1(
        platform_listing_id=row.platform_listing_id,
        max_age_days_status=max_age_status,
        min_rating_count_status=rating_status,
        min_lifetime_ratings_per_day_status=lifetime_status,
        min_age_bucket_percentile_status=percentile_status,
        min_observed_rating_delta_per_day_status=delta_status,
        is_anomaly_candidate=all(value == "pass" for value in configured),
    )


def _minimum_gate(
    value: int | float | None,
    threshold: int | float | None,
) -> AnomalyGateStatusV1:
    if threshold is None:
        return "not_configured"
    if value is None:
        return "unknown"
    return "pass" if value >= threshold else "fail"


def _maximum_gate(
    value: float | None,
    threshold: float | None,
) -> AnomalyGateStatusV1:
    if threshold is None:
        return "not_configured"
    if value is None:
        return "unknown"
    return "pass" if value <= threshold else "fail"


def _observed_delta_gate(
    row: ThesisTractionRow,
    threshold: float | None,
) -> AnomalyGateStatusV1:
    if threshold is None:
        return "not_configured"
    if row.longitudinal.status not in {"observed", "negative_revision"}:
        return "unknown"
    value = row.longitudinal.observed_rating_delta_per_day
    if value is None:
        raise ThesisIntelligenceError(
            "usable longitudinal state is missing observed_rating_delta_per_day"
        )
    return "pass" if value >= threshold else "fail"


def _candidate_from_row(row: ThesisTractionRow) -> AnomalyCandidateV1:
    return AnomalyCandidateV1(
        platform_listing_id=row.platform_listing_id,
        lifetime_ratings_per_day=row.lifetime_ratings_per_day,
        rating_count=row.rating_count,
        listing_age_days=row.listing_age_days,
    )


def _candidate_sort_key(
    candidate: AnomalyCandidateV1,
) -> tuple[bool, float, bool, int, bool, float, str]:
    pace = candidate.lifetime_ratings_per_day
    rating = candidate.rating_count
    age = candidate.listing_age_days
    return (
        pace is None,
        -(pace if pace is not None else 0.0),
        rating is None,
        -(rating if rating is not None else 0),
        age is None,
        age if age is not None else 0.0,
        candidate.platform_listing_id,
    )
