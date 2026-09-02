from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Self
from zipfile import BadZipFile, ZipFile

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from yandex_analytics_reaper.analyst import (
    AnalystListingRow,
    AnalystMarketExportReport,
    AnalystResolvedValue,
    AnalystSnapshotReport,
)
from yandex_analytics_reaper.thesis_artifacts import load_experiment_artifact_binding
from yandex_analytics_reaper.thesis_intelligence import (
    ExperimentArtifactBinding,
    ThesisIntelligenceError,
    ThesisSuiteDeclaration,
    build_intelligence_inputs,
    canonical_model_hash,
    validate_artifact_file_sha256,
)

TRACTION_FEATURES_SPEC_VERSION: Literal["traction-features-v1"] = "traction-features-v1"

type AgeBucketV1 = Literal[
    "lt_7_days",
    "7_30_days",
    "31_90_days",
    "91_180_days",
    "181_365_days",
    "over_365_days",
]
type LifetimePaceStatusV1 = Literal[
    "observed",
    "missing_first_published",
    "missing_rating_count",
    "too_young",
]
type LongitudinalStatusV1 = Literal[
    "observed",
    "negative_revision",
    "current_missing",
    "no_prior_observation",
    "interval_too_short",
]


class BoundExperimentEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    binding: ExperimentArtifactBinding
    snapshot: AnalystSnapshotReport
    market_export: AnalystMarketExportReport

    @model_validator(mode="after")
    def validate_binding(self) -> Self:
        if self.snapshot.snapshot_id != self.binding.snapshot_id:
            raise ValueError("bound snapshot_id does not match experiment binding")
        if self.snapshot.content_hash != self.binding.snapshot_content_hash:
            raise ValueError("bound snapshot hash does not match experiment binding")
        if self.snapshot.created_at != self.binding.snapshot_created_at:
            raise ValueError("bound snapshot reference time does not match experiment binding")
        if self.market_export.snapshot_id != self.snapshot.snapshot_id:
            raise ValueError("bound market export snapshot_id does not match snapshot")
        if self.market_export.snapshot_content_hash != self.snapshot.content_hash:
            raise ValueError("bound market export snapshot hash does not match snapshot")
        if self.market_export.content_hash != self.binding.market_export_content_hash:
            raise ValueError("bound market export hash does not match experiment binding")
        return self


class LongitudinalRatingDeltaV1(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: LongitudinalStatusV1
    prior_artifact_sha256: str | None = None
    previous_observation_id: str | None = None
    previous_observed_at: AwareDatetime | None = None
    previous_rating_count: int | None = Field(default=None, ge=0)
    current_observation_id: str | None = None
    current_observed_at: AwareDatetime | None = None
    current_rating_count: int | None = Field(default=None, ge=0)
    delta_interval_days: float | None = Field(default=None, gt=0.0)
    rating_count_delta: int | None = None
    observed_rating_delta_per_day: float | None = None

    @field_validator("prior_artifact_sha256")
    @classmethod
    def validate_prior_hash(cls, value: str | None) -> str | None:
        if value is None:
            return None
        invalid = any(character not in "0123456789abcdef" for character in value)
        if len(value) != 64 or invalid:
            raise ValueError("prior_artifact_sha256 must be a lowercase SHA-256 digest")
        return value

    @model_validator(mode="after")
    def validate_state(self) -> Self:
        current = (
            self.current_observation_id,
            self.current_observed_at,
            self.current_rating_count,
        )
        previous = (
            self.prior_artifact_sha256,
            self.previous_observation_id,
            self.previous_observed_at,
            self.previous_rating_count,
        )
        delta = (self.delta_interval_days, self.rating_count_delta)

        if self.status == "current_missing":
            if any(value is not None for value in (*current, *previous, *delta)):
                raise ValueError("current_missing longitudinal state cannot carry observations")
            if self.observed_rating_delta_per_day is not None:
                raise ValueError("current_missing longitudinal state cannot carry velocity")
            return self

        if any(value is None for value in current):
            raise ValueError("non-missing longitudinal state requires the current observation")

        if self.status == "no_prior_observation":
            if any(value is not None for value in (*previous, *delta)):
                raise ValueError("no_prior_observation cannot carry prior/delta fields")
            if self.observed_rating_delta_per_day is not None:
                raise ValueError("no_prior_observation cannot carry velocity")
            return self

        if any(value is None for value in previous) or any(value is None for value in delta):
            raise ValueError("selected-prior longitudinal state requires prior and delta fields")

        interval = _required_float(self.delta_interval_days)
        rating_delta = _required_int(self.rating_count_delta)
        previous_count = _required_int(self.previous_rating_count)
        current_count = _required_int(self.current_rating_count)
        if rating_delta != current_count - previous_count:
            raise ValueError("rating_count_delta does not match current - previous")
        if interval < 1.0:
            if self.status != "interval_too_short":
                raise ValueError("sub-day longitudinal interval must be interval_too_short")
            if self.observed_rating_delta_per_day is not None:
                raise ValueError("interval_too_short cannot expose observed daily delta")
            return self

        expected_velocity = rating_delta / interval
        if self.observed_rating_delta_per_day is None or not math.isclose(
            self.observed_rating_delta_per_day,
            expected_velocity,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("observed daily delta does not match rating delta / interval")
        expected_status: LongitudinalStatusV1 = (
            "negative_revision" if rating_delta < 0 else "observed"
        )
        if self.status != expected_status:
            raise ValueError("longitudinal status does not match rating delta sign")
        return self


class ThesisTractionRow(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    platform_listing_id: str
    external_app_id: str
    canonical_url: str
    title: str | None

    first_published_at: AwareDatetime | None
    first_published_observation_id: str | None
    listing_age_days: float | None = Field(default=None, ge=0.0)
    age_bucket: AgeBucketV1 | None

    rating_count: int | None = Field(default=None, ge=0)
    rating_count_observation_id: str | None
    rating_count_observed_at: AwareDatetime | None

    lifetime_ratings_per_day: float | None = Field(default=None, ge=0.0)
    lifetime_pace_status: LifetimePaceStatusV1

    suite_age_bucket_member_count: int | None = Field(default=None, ge=1)
    suite_age_bucket_pace_observed_count: int | None = Field(default=None, ge=0)
    suite_age_bucket_pace_coverage_ratio: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    suite_age_bucket_percentile: float | None = Field(default=None, ge=0.0, le=1.0)

    longitudinal: LongitudinalRatingDeltaV1

    @model_validator(mode="after")
    def validate_semantics(self) -> Self:
        if self.first_published_at is None:
            if self.first_published_observation_id is not None:
                raise ValueError("missing publication time cannot carry an observation ID")
            if self.listing_age_days is not None or self.age_bucket is not None:
                raise ValueError("missing publication time cannot carry age/bucket")
        elif self.first_published_observation_id is None:
            raise ValueError("observed publication time requires an observation ID")

        if self.rating_count is None:
            if (
                self.rating_count_observation_id is not None
                or self.rating_count_observed_at is not None
            ):
                raise ValueError("missing rating_count cannot carry observation evidence")
            if self.longitudinal.status != "current_missing":
                raise ValueError("missing rating_count requires current_missing longitudinal state")
        else:
            if self.rating_count_observation_id is None or self.rating_count_observed_at is None:
                raise ValueError("observed rating_count requires observation evidence")
            if (
                self.longitudinal.current_rating_count != self.rating_count
                or self.longitudinal.current_observation_id != self.rating_count_observation_id
                or self.longitudinal.current_observed_at != self.rating_count_observed_at
            ):
                raise ValueError("longitudinal current point must equal row rating evidence")

        if self.lifetime_pace_status == "observed":
            if (
                self.listing_age_days is None
                or self.listing_age_days < 1.0
                or self.rating_count is None
                or self.lifetime_ratings_per_day is None
            ):
                raise ValueError("observed lifetime pace lacks method prerequisites")
            expected_pace = self.rating_count / self.listing_age_days
            if not math.isclose(
                self.lifetime_ratings_per_day,
                expected_pace,
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                raise ValueError("lifetime pace does not match rating_count / listing_age_days")
        elif self.lifetime_ratings_per_day is not None:
            raise ValueError("unavailable lifetime pace cannot carry a numeric pace")

        coverage = (
            self.suite_age_bucket_member_count,
            self.suite_age_bucket_pace_observed_count,
            self.suite_age_bucket_pace_coverage_ratio,
        )
        if self.age_bucket is None:
            if any(value is not None for value in coverage):
                raise ValueError("missing age bucket cannot carry suite cohort facts")
            if self.suite_age_bucket_percentile is not None:
                raise ValueError("missing age bucket cannot carry percentile")
            return self
        if any(value is None for value in coverage):
            raise ValueError("observed age bucket requires suite cohort facts")
        members = _required_int(self.suite_age_bucket_member_count)
        observed = _required_int(self.suite_age_bucket_pace_observed_count)
        ratio = _required_float(self.suite_age_bucket_pace_coverage_ratio)
        if observed > members:
            raise ValueError("pace-observed cohort count cannot exceed bucket members")
        if not math.isclose(ratio, observed / members, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError("suite cohort coverage ratio does not match counts")
        if self.lifetime_pace_status == "observed":
            if self.suite_age_bucket_percentile is None:
                raise ValueError("observed lifetime pace requires suite percentile")
        elif self.suite_age_bucket_percentile is not None:
            raise ValueError("unavailable lifetime pace cannot carry suite percentile")
        return self


class ThesisFieldCoverage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    member_count: int = Field(ge=1)
    observed_count: int = Field(ge=0)
    missing_count: int = Field(ge=0)
    coverage_ratio: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        if self.observed_count > self.member_count:
            raise ValueError("coverage observed_count cannot exceed member_count")
        if self.missing_count != self.member_count - self.observed_count:
            raise ValueError("coverage missing_count must equal member_count - observed_count")
        expected = self.observed_count / self.member_count
        if not math.isclose(self.coverage_ratio, expected, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError("coverage ratio does not match counts")
        return self


class ThesisTractionSet(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    thesis_id: str
    thesis_version: int = Field(ge=1)
    comparable_set_id: str
    comparable_set_version: int = Field(ge=1)
    rating_count_coverage: ThesisFieldCoverage
    rows: tuple[ThesisTractionRow, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_rating_coverage(self) -> Self:
        observed = sum(row.rating_count is not None for row in self.rows)
        expected = ThesisFieldCoverage(
            member_count=len(self.rows),
            observed_count=observed,
            missing_count=len(self.rows) - observed,
            coverage_ratio=observed / len(self.rows),
        )
        if self.rating_count_coverage != expected:
            raise ValueError("rating_count_coverage does not match traction rows")
        return self


class ThesisTractionFeaturesPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: Literal["traction-features-v1"] = TRACTION_FEATURES_SPEC_VERSION
    suite_id: str
    suite_version: int = Field(ge=1)
    suite_content_hash: str
    reference_time: AwareDatetime
    current_experiment: ExperimentArtifactBinding
    prior_experiments: tuple[ExperimentArtifactBinding, ...]
    theses: tuple[ThesisTractionSet, ...] = Field(min_length=1)

    @field_validator("suite_content_hash")
    @classmethod
    def validate_suite_hash(cls, value: str) -> str:
        invalid = any(character not in "0123456789abcdef" for character in value)
        if len(value) != 64 or invalid:
            raise ValueError("suite_content_hash must be a lowercase SHA-256 digest")
        return value

    @model_validator(mode="after")
    def validate_experiment_bindings(self) -> Self:
        if self.current_experiment.role != "current":
            raise ValueError("traction current experiment must have role=current")
        if any(item.role != "prior" for item in self.prior_experiments):
            raise ValueError("traction prior experiments must have role=prior")
        expected = tuple(
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
        if self.prior_experiments != expected:
            raise ValueError("traction prior experiments must use canonical history order")
        hashes = [item.artifact_sha256 for item in self.prior_experiments]
        if len(set(hashes)) != len(hashes):
            raise ValueError("traction prior experiment hashes must be unique")
        if self.current_experiment.artifact_sha256 in hashes:
            raise ValueError("traction current artifact cannot also be prior")
        return self


class ThesisTractionFeaturesReport(ThesisTractionFeaturesPayload):
    content_hash: str

    @field_validator("content_hash")
    @classmethod
    def validate_content_hash(cls, value: str) -> str:
        invalid = any(character not in "0123456789abcdef" for character in value)
        if len(value) != 64 or invalid:
            raise ValueError("content_hash must be a lowercase SHA-256 digest")
        return value


@dataclass(frozen=True)
class _PriorRatingPoint:
    artifact_sha256: str
    observation_id: str
    observed_at: datetime
    rating_count: int


@dataclass(frozen=True)
class _PriorEvidenceView:
    binding: ExperimentArtifactBinding
    rows_by_id: Mapping[str, AnalystListingRow]


@dataclass(frozen=True)
class _PreTraction:
    source: AnalystListingRow
    title: str | None
    first_published_at: datetime | None
    first_published_observation_id: str | None
    listing_age_days: float | None
    age_bucket: AgeBucketV1 | None
    rating_count: int | None
    rating_count_observation_id: str | None
    rating_count_observed_at: datetime | None
    lifetime_ratings_per_day: float | None
    lifetime_pace_status: LifetimePaceStatusV1
    longitudinal: LongitudinalRatingDeltaV1


def load_bound_experiment_evidence(
    artifact_path: Path,
    *,
    role: Literal["current", "prior"],
    expected_suite: ThesisSuiteDeclaration | None = None,
) -> BoundExperimentEvidence:
    """Verify a frozen experiment ZIP, then expose snapshot/export evidence needed by P2."""
    binding = load_experiment_artifact_binding(
        artifact_path,
        role=role,
        expected_suite=expected_suite,
    )
    try:
        with ZipFile(artifact_path, mode="r") as archive:
            snapshot = AnalystSnapshotReport.model_validate_json(
                archive.read("reports/analyst-snapshot.json")
            )
            market_export = AnalystMarketExportReport.model_validate_json(
                archive.read("reports/market-export.json")
            )
    except (BadZipFile, KeyError, OSError, ValidationError, ValueError) as exc:
        raise ThesisIntelligenceError(
            f"experiment artifact evidence cannot be loaded for traction: {exc}"
        ) from exc
    validate_artifact_file_sha256(binding, artifact_path)
    return BoundExperimentEvidence(
        binding=binding,
        snapshot=snapshot,
        market_export=market_export,
    )


def build_traction_features(
    suite: ThesisSuiteDeclaration,
    *,
    current: BoundExperimentEvidence,
    priors: Sequence[BoundExperimentEvidence] = (),
) -> ThesisTractionFeaturesReport:
    """Derive deterministic P2 traction features without network or ambient mutable state."""
    suite = ThesisSuiteDeclaration.model_validate(suite.model_dump())
    current = BoundExperimentEvidence.model_validate(current.model_dump())
    prior_evidence = tuple(
        BoundExperimentEvidence.model_validate(item.model_dump()) for item in priors
    )

    inputs = build_intelligence_inputs(
        suite,
        current_experiment=current.binding,
        prior_experiments=tuple(item.binding for item in prior_evidence),
    )
    by_hash = {item.binding.artifact_sha256: item for item in prior_evidence}
    ordered_priors = tuple(
        _PriorEvidenceView(
            binding=item,
            rows_by_id=_rows_by_id(by_hash[item.artifact_sha256].market_export),
        )
        for item in inputs.prior_experiments
    )

    if current.binding.role != "current":
        raise ThesisIntelligenceError("traction current evidence must have role=current")
    if current.binding.experiment_id != suite.suite_id:
        raise ThesisIntelligenceError("traction current experiment must match suite_id")

    current_rows = _rows_by_id(current.market_export)
    comparable_by_id = {
        (item.set_id, item.version): item for item in current.snapshot.comparable_sets
    }
    expected_comparable_keys = {
        (f"{suite.suite_id}--{thesis.thesis_id}", 1) for thesis in suite.theses
    }
    if set(comparable_by_id) != expected_comparable_keys:
        raise ThesisIntelligenceError(
            "current snapshot comparable scope does not equal the suite-compiled thesis scope"
        )

    ordered_unique_ids: list[str] = []
    thesis_bindings: list[tuple[str, int, str, int, tuple[str, ...]]] = []
    for thesis in suite.theses:
        set_id = f"{suite.suite_id}--{thesis.thesis_id}"
        key = (set_id, 1)
        binding = comparable_by_id.get(key)
        if binding is None:
            raise ThesisIntelligenceError(
                f"current snapshot is missing compiled comparable set {set_id}@1"
            )
        for listing_id in binding.member_listing_ids:
            if listing_id not in current_rows:
                raise ThesisIntelligenceError(
                    f"current market export is missing comparable member {listing_id}"
                )
            if listing_id not in ordered_unique_ids:
                ordered_unique_ids.append(listing_id)
        thesis_bindings.append(
            (
                thesis.thesis_id,
                thesis.thesis_version,
                binding.set_id,
                binding.version,
                binding.member_listing_ids,
            )
        )

    pre_rows = {
        listing_id: _derive_pre_traction(
            current_rows[listing_id],
            reference_time=current.snapshot.created_at,
            priors=ordered_priors,
        )
        for listing_id in ordered_unique_ids
    }
    cohorts = _build_age_bucket_cohorts(pre_rows)

    thesis_sets: list[ThesisTractionSet] = []
    for thesis_id, thesis_version, set_id, set_version, member_listing_ids in thesis_bindings:
        rows = tuple(
            _materialize_row(pre_rows[listing_id], cohorts)
            for listing_id in member_listing_ids
        )
        observed_rating_count = sum(row.rating_count is not None for row in rows)
        thesis_sets.append(
            ThesisTractionSet(
                thesis_id=thesis_id,
                thesis_version=thesis_version,
                comparable_set_id=set_id,
                comparable_set_version=set_version,
                rating_count_coverage=ThesisFieldCoverage(
                    member_count=len(rows),
                    observed_count=observed_rating_count,
                    missing_count=len(rows) - observed_rating_count,
                    coverage_ratio=observed_rating_count / len(rows),
                ),
                rows=rows,
            )
        )

    payload = ThesisTractionFeaturesPayload(
        suite_id=suite.suite_id,
        suite_version=suite.suite_version,
        suite_content_hash=canonical_model_hash(suite),
        reference_time=current.snapshot.created_at,
        current_experiment=inputs.current_experiment,
        prior_experiments=inputs.prior_experiments,
        theses=tuple(thesis_sets),
    )
    report = ThesisTractionFeaturesReport(
        **payload.model_dump(mode="python"),
        content_hash=canonical_model_hash(payload),
    )
    return validate_traction_features(report)


def validate_traction_features(
    report: ThesisTractionFeaturesReport,
) -> ThesisTractionFeaturesReport:
    report = ThesisTractionFeaturesReport.model_validate(report.model_dump())
    payload = ThesisTractionFeaturesPayload.model_validate(
        report.model_dump(exclude={"content_hash"})
    )
    if report.content_hash != canonical_model_hash(payload):
        raise ThesisIntelligenceError("traction feature report content_hash mismatch")
    if report.reference_time != report.current_experiment.snapshot_created_at:
        raise ThesisIntelligenceError(
            "traction reference_time must equal current snapshot reference time"
        )
    return report


def _derive_pre_traction(
    row: AnalystListingRow,
    *,
    reference_time: datetime,
    priors: Sequence[_PriorEvidenceView],
) -> _PreTraction:
    title = _resolved_string(row.title, field_name="title", listing_id=row.platform_listing_id)
    first_published_at, first_published_observation_id = _publication(row)
    listing_age_days = _listing_age_days(first_published_at, reference_time)
    age_bucket = _age_bucket(listing_age_days)
    rating_count, rating_observation_id, rating_observed_at = _rating_observation(row)
    pace, pace_status = _lifetime_pace(listing_age_days, rating_count)
    longitudinal = _longitudinal(
        row.platform_listing_id,
        current_rating_count=rating_count,
        current_observation_id=rating_observation_id,
        current_observed_at=rating_observed_at,
        priors=priors,
    )
    return _PreTraction(
        source=row,
        title=title,
        first_published_at=first_published_at,
        first_published_observation_id=first_published_observation_id,
        listing_age_days=listing_age_days,
        age_bucket=age_bucket,
        rating_count=rating_count,
        rating_count_observation_id=rating_observation_id,
        rating_count_observed_at=rating_observed_at,
        lifetime_ratings_per_day=pace,
        lifetime_pace_status=pace_status,
        longitudinal=longitudinal,
    )


def _materialize_row(
    pre: _PreTraction,
    cohorts: Mapping[AgeBucketV1, tuple[int, tuple[float, ...]]],
) -> ThesisTractionRow:
    member_count: int | None = None
    observed_count: int | None = None
    coverage_ratio: float | None = None
    percentile: float | None = None
    if pre.age_bucket is not None:
        member_count, observed_paces = cohorts[pre.age_bucket]
        observed_count = len(observed_paces)
        coverage_ratio = observed_count / member_count
        if pre.lifetime_ratings_per_day is not None:
            percentile = (
                sum(value <= pre.lifetime_ratings_per_day for value in observed_paces)
                / observed_count
            )
    return ThesisTractionRow(
        platform_listing_id=pre.source.platform_listing_id,
        external_app_id=pre.source.external_app_id,
        canonical_url=pre.source.canonical_url,
        title=pre.title,
        first_published_at=pre.first_published_at,
        first_published_observation_id=pre.first_published_observation_id,
        listing_age_days=pre.listing_age_days,
        age_bucket=pre.age_bucket,
        rating_count=pre.rating_count,
        rating_count_observation_id=pre.rating_count_observation_id,
        rating_count_observed_at=pre.rating_count_observed_at,
        lifetime_ratings_per_day=pre.lifetime_ratings_per_day,
        lifetime_pace_status=pre.lifetime_pace_status,
        suite_age_bucket_member_count=member_count,
        suite_age_bucket_pace_observed_count=observed_count,
        suite_age_bucket_pace_coverage_ratio=coverage_ratio,
        suite_age_bucket_percentile=percentile,
        longitudinal=pre.longitudinal,
    )


def _build_age_bucket_cohorts(
    pre_rows: Mapping[str, _PreTraction],
) -> dict[AgeBucketV1, tuple[int, tuple[float, ...]]]:
    members: dict[AgeBucketV1, int] = {}
    paces: dict[AgeBucketV1, list[float]] = {}
    for pre in pre_rows.values():
        if pre.age_bucket is None:
            continue
        members[pre.age_bucket] = members.get(pre.age_bucket, 0) + 1
        if pre.lifetime_pace_status == "observed":
            if pre.lifetime_ratings_per_day is None:
                raise ThesisIntelligenceError("observed lifetime pace is missing its numeric value")
            paces.setdefault(pre.age_bucket, []).append(pre.lifetime_ratings_per_day)
    return {
        bucket: (count, tuple(sorted(paces.get(bucket, ()))))
        for bucket, count in members.items()
    }


def _longitudinal(
    listing_id: str,
    *,
    current_rating_count: int | None,
    current_observation_id: str | None,
    current_observed_at: datetime | None,
    priors: Sequence[_PriorEvidenceView],
) -> LongitudinalRatingDeltaV1:
    if current_rating_count is None:
        return LongitudinalRatingDeltaV1(status="current_missing")
    if current_observation_id is None or current_observed_at is None:
        raise ThesisIntelligenceError(
            f"observed current rating_count lacks evidence for {listing_id}"
        )

    points: list[_PriorRatingPoint] = []
    for prior in priors:
        prior_row = prior.rows_by_id.get(listing_id)
        if prior_row is None:
            continue
        count, observation_id, observed_at = _rating_observation(prior_row)
        if count is None or observation_id is None or observed_at is None:
            continue
        if observed_at >= current_observed_at:
            continue
        points.append(
            _PriorRatingPoint(
                artifact_sha256=prior.binding.artifact_sha256,
                observation_id=observation_id,
                observed_at=observed_at,
                rating_count=count,
            )
        )

    if not points:
        return LongitudinalRatingDeltaV1(
            status="no_prior_observation",
            current_observation_id=current_observation_id,
            current_observed_at=current_observed_at,
            current_rating_count=current_rating_count,
        )

    latest_time = max(item.observed_at for item in points)
    latest = [item for item in points if item.observed_at == latest_time]
    values = {item.rating_count for item in latest}
    if len(values) != 1:
        raise ThesisIntelligenceError(
            f"conflicting prior rating_count values at {latest_time.isoformat()} for {listing_id}"
        )
    selected = min(
        latest,
        key=lambda item: (item.artifact_sha256, item.observation_id),
    )
    interval_days = (current_observed_at - selected.observed_at).total_seconds() / 86_400
    if interval_days <= 0:
        raise ThesisIntelligenceError("selected prior observation must precede current observation")
    delta = current_rating_count - selected.rating_count
    if interval_days < 1.0:
        return LongitudinalRatingDeltaV1(
            status="interval_too_short",
            prior_artifact_sha256=selected.artifact_sha256,
            previous_observation_id=selected.observation_id,
            previous_observed_at=selected.observed_at,
            previous_rating_count=selected.rating_count,
            current_observation_id=current_observation_id,
            current_observed_at=current_observed_at,
            current_rating_count=current_rating_count,
            delta_interval_days=interval_days,
            rating_count_delta=delta,
            observed_rating_delta_per_day=None,
        )
    return LongitudinalRatingDeltaV1(
        status="negative_revision" if delta < 0 else "observed",
        prior_artifact_sha256=selected.artifact_sha256,
        previous_observation_id=selected.observation_id,
        previous_observed_at=selected.observed_at,
        previous_rating_count=selected.rating_count,
        current_observation_id=current_observation_id,
        current_observed_at=current_observed_at,
        current_rating_count=current_rating_count,
        delta_interval_days=interval_days,
        rating_count_delta=delta,
        observed_rating_delta_per_day=delta / interval_days,
    )


def _publication(row: AnalystListingRow) -> tuple[datetime | None, str | None]:
    resolved = row.first_published_at
    if resolved.value is None:
        return None, None
    if not isinstance(resolved.value, str):
        raise ThesisIntelligenceError(
            f"first_published_at for {row.platform_listing_id} is not a timestamp string"
        )
    if resolved.evidence is None:
        raise ThesisIntelligenceError(
            f"observed first_published_at lacks evidence for {row.platform_listing_id}"
        )
    return _parse_aware_timestamp(resolved.value), resolved.evidence.observation_id


def _rating_observation(
    row: AnalystListingRow,
) -> tuple[int | None, str | None, datetime | None]:
    resolved = row.rating_count
    if resolved.value is None:
        return None, None, None
    count = _integral_non_negative(
        resolved,
        field_name="rating_count",
        listing_id=row.platform_listing_id,
    )
    if resolved.evidence is None:
        raise ThesisIntelligenceError(
            f"observed rating_count lacks evidence for {row.platform_listing_id}"
        )
    observed_at = _parse_aware_timestamp(resolved.evidence.observed_at)
    return count, resolved.evidence.observation_id, observed_at


def _resolved_string(
    resolved: AnalystResolvedValue,
    *,
    field_name: str,
    listing_id: str,
) -> str | None:
    if resolved.value is None:
        return None
    if not isinstance(resolved.value, str):
        raise ThesisIntelligenceError(f"{field_name} for {listing_id} is not a string")
    return resolved.value


def _integral_non_negative(
    resolved: AnalystResolvedValue,
    *,
    field_name: str,
    listing_id: str,
) -> int:
    value = resolved.value
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ThesisIntelligenceError(f"{field_name} for {listing_id} is not numeric")
    number = float(value)
    if not math.isfinite(number) or not number.is_integer() or number < 0:
        raise ThesisIntelligenceError(
            f"{field_name} for {listing_id} must be a finite non-negative integer"
        )
    return int(number)


def _listing_age_days(
    first_published_at: datetime | None,
    reference_time: datetime,
) -> float | None:
    if first_published_at is None:
        return None
    reference = _utc(reference_time)
    published = _utc(first_published_at)
    age = (reference - published).total_seconds() / 86_400
    if age < 0:
        raise ThesisIntelligenceError("first_published_at cannot be after traction reference_time")
    return age


def _age_bucket(age_days: float | None) -> AgeBucketV1 | None:
    if age_days is None:
        return None
    if not math.isfinite(age_days) or age_days < 0:
        raise ThesisIntelligenceError("listing age must be finite and non-negative")
    if age_days < 7:
        return "lt_7_days"
    if age_days < 31:
        return "7_30_days"
    if age_days < 91:
        return "31_90_days"
    if age_days < 181:
        return "91_180_days"
    if age_days < 366:
        return "181_365_days"
    return "over_365_days"


def _lifetime_pace(
    age_days: float | None,
    rating_count: int | None,
) -> tuple[float | None, LifetimePaceStatusV1]:
    if age_days is None:
        return None, "missing_first_published"
    if age_days < 1.0:
        return None, "too_young"
    if rating_count is None:
        return None, "missing_rating_count"
    return rating_count / age_days, "observed"


def _rows_by_id(market_export: AnalystMarketExportReport) -> dict[str, AnalystListingRow]:
    rows = {item.platform_listing_id: item for item in market_export.listings}
    if len(rows) != len(market_export.listings):
        raise ThesisIntelligenceError("market export contains duplicate listing rows")
    return rows


def _parse_aware_timestamp(value: str) -> datetime:
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ThesisIntelligenceError(f"invalid timestamp: {value}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ThesisIntelligenceError(f"timestamp must be timezone-aware: {value}")
    return parsed.astimezone(UTC)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ThesisIntelligenceError("traction timestamps must be timezone-aware")
    return value.astimezone(UTC)


def _required_int(value: int | None) -> int:
    if value is None:
        raise ThesisIntelligenceError("required integer is missing")
    return value


def _required_float(value: float | None) -> float:
    if value is None:
        raise ThesisIntelligenceError("required float is missing")
    return value
