from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, Self
from zipfile import BadZipFile, ZipFile

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError, model_validator

from yandex_analytics_reaper.point_observation import (
    ListingObservationError,
    ListingObservationReport,
    verify_listing_observation_artifact,
)

LISTING_LONGITUDINAL_COMPARISON_SPEC_VERSION: Literal[
    "listing-longitudinal-comparison-v1"
] = "listing-longitudinal-comparison-v1"


class ObservationArtifactIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_sha256: str
    manifest_content_hash: str
    source_snapshot_id: str
    source_content_hash: str
    observed_at: AwareDatetime
    parser_version: str

    @model_validator(mode="after")
    def validate_hashes(self) -> Self:
        _require_sha256(self.artifact_sha256)
        _require_sha256(self.manifest_content_hash)
        _require_sha256(self.source_content_hash)
        return self


class ListingLongitudinalFact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    app_id: int = Field(gt=0)
    previous_presence: Literal["observed", "missing"]
    current_presence: Literal["observed", "missing"]
    rating_count_previous: int | None = Field(default=None, ge=0)
    rating_count_current: int | None = Field(default=None, ge=0)
    rating_count_delta: int | None = None
    observed_rating_delta_per_day: float | None = None
    measurement_status: Literal[
        "comparable",
        "missing_previous",
        "missing_current",
        "missing_both",
        "metric_missing_previous",
        "metric_missing_current",
        "metric_missing_both",
    ]
    revision_status: Literal[
        "increase",
        "unchanged",
        "revision_decrease",
        "unavailable",
    ]

    @model_validator(mode="after")
    def validate_derived_fields(self) -> Self:
        comparable = self.measurement_status == "comparable"
        if comparable:
            if self.previous_presence != "observed" or self.current_presence != "observed":
                raise ValueError("comparable metric requires both observations to be present")
            if self.rating_count_previous is None or self.rating_count_current is None:
                raise ValueError("comparable metric requires both rating counts")
            expected_delta = self.rating_count_current - self.rating_count_previous
            if self.rating_count_delta != expected_delta:
                raise ValueError("rating_count_delta does not match endpoint values")
            if self.observed_rating_delta_per_day is None:
                raise ValueError("comparable metric requires observed_rating_delta_per_day")
            expected_revision = _revision_status(expected_delta)
            if self.revision_status != expected_revision:
                raise ValueError("revision_status does not match rating_count_delta")
        else:
            if self.rating_count_delta is not None or self.observed_rating_delta_per_day is not None:
                raise ValueError("unavailable metric comparison must not invent a delta")
            if self.revision_status != "unavailable":
                raise ValueError("unavailable metric comparison requires revision_status=unavailable")
        return self


class ListingLongitudinalComparison(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: Literal["listing-longitudinal-comparison-v1"] = (
        LISTING_LONGITUDINAL_COMPARISON_SPEC_VERSION
    )
    provenance_channel: Literal["point_observed"] = "point_observed"
    comparison_kind: Literal["known_id_longitudinal"] = "known_id_longitudinal"
    observation_set_id: str
    observation_set_version: int = Field(ge=1)
    declaration_content_hash: str
    requested_app_ids: tuple[int, ...]
    previous: ObservationArtifactIdentity
    current: ObservationArtifactIdentity
    elapsed_seconds: float = Field(gt=0)
    elapsed_days: float = Field(gt=0)
    facts: tuple[ListingLongitudinalFact, ...]
    interpretation_boundary: Literal[
        "point_velocity_not_search_visibility_dau_installs_revenue_or_retention"
    ] = "point_velocity_not_search_visibility_dau_installs_revenue_or_retention"

    @model_validator(mode="after")
    def validate_comparison(self) -> Self:
        _require_sha256(self.declaration_content_hash)
        if tuple(fact.app_id for fact in self.facts) != self.requested_app_ids:
            raise ValueError("fact order must equal requested_app_ids order")
        if self.current.observed_at <= self.previous.observed_at:
            raise ValueError("current observation must be later than previous observation")
        return self


def compare_listing_observation_artifacts(
    previous_artifact: Path,
    current_artifact: Path,
    output_path: Path,
) -> ListingLongitudinalComparison:
    if output_path.exists():
        raise ListingObservationError(
            f"refusing to overwrite existing longitudinal comparison: {output_path}"
        )

    previous_verification = verify_listing_observation_artifact(previous_artifact)
    current_verification = verify_listing_observation_artifact(current_artifact)
    previous_report = _load_report(previous_artifact)
    current_report = _load_report(current_artifact)

    _require_compatible_reports(previous_report, current_report)
    elapsed_seconds = (current_report.observed_at - previous_report.observed_at).total_seconds()
    if elapsed_seconds <= 0:
        raise ListingObservationError("current observation must be later than previous observation")
    elapsed_days = elapsed_seconds / 86_400.0

    previous_by_id = {item.app_id: item for item in previous_report.listings}
    current_by_id = {item.app_id: item for item in current_report.listings}
    facts = tuple(
        _build_fact(
            app_id,
            previous=previous_by_id.get(app_id),
            current=current_by_id.get(app_id),
            elapsed_days=elapsed_days,
        )
        for app_id in previous_report.requested_app_ids
    )

    comparison = ListingLongitudinalComparison(
        observation_set_id=previous_report.observation_set_id,
        observation_set_version=previous_report.observation_set_version,
        declaration_content_hash=previous_report.declaration_content_hash,
        requested_app_ids=previous_report.requested_app_ids,
        previous=ObservationArtifactIdentity(
            artifact_sha256=previous_verification.artifact_sha256,
            manifest_content_hash=previous_verification.manifest_content_hash,
            source_snapshot_id=previous_report.source_snapshot_id,
            source_content_hash=previous_report.source_content_hash,
            observed_at=previous_report.observed_at,
            parser_version=previous_report.parser_version,
        ),
        current=ObservationArtifactIdentity(
            artifact_sha256=current_verification.artifact_sha256,
            manifest_content_hash=current_verification.manifest_content_hash,
            source_snapshot_id=current_report.source_snapshot_id,
            source_content_hash=current_report.source_content_hash,
            observed_at=current_report.observed_at,
            parser_version=current_report.parser_version,
        ),
        elapsed_seconds=elapsed_seconds,
        elapsed_days=elapsed_days,
        facts=facts,
    )
    _write_create_only_json(output_path, comparison)
    return comparison


def _load_report(artifact_path: Path) -> ListingObservationReport:
    try:
        with ZipFile(artifact_path, mode="r") as archive:
            payload = archive.read("reports/observation.json")
    except (BadZipFile, OSError, KeyError) as exc:
        raise ListingObservationError(f"cannot read observation report: {exc}") from exc
    try:
        return ListingObservationReport.model_validate_json(payload)
    except ValidationError as exc:
        raise ListingObservationError(f"observation report validation failed: {exc}") from exc


def _require_compatible_reports(
    previous: ListingObservationReport,
    current: ListingObservationReport,
) -> None:
    previous_identity = (
        previous.observation_set_id,
        previous.observation_set_version,
        previous.declaration_content_hash,
        previous.requested_app_ids,
        previous.source_id,
        previous.source_request_key,
        previous.parser_name,
        previous.parser_version,
    )
    current_identity = (
        current.observation_set_id,
        current.observation_set_version,
        current.declaration_content_hash,
        current.requested_app_ids,
        current.source_id,
        current.source_request_key,
        current.parser_name,
        current.parser_version,
    )
    if current_identity != previous_identity:
        raise ListingObservationError(
            "point-observation artifacts are not compatible for v1 longitudinal comparison"
        )


def _build_fact(
    app_id: int,
    *,
    previous: object | None,
    current: object | None,
    elapsed_days: float,
) -> ListingLongitudinalFact:
    from yandex_analytics_reaper.point_observation import PointListingObservation

    previous_listing = previous if isinstance(previous, PointListingObservation) else None
    current_listing = current if isinstance(current, PointListingObservation) else None
    previous_presence: Literal["observed", "missing"] = (
        "observed" if previous_listing is not None else "missing"
    )
    current_presence: Literal["observed", "missing"] = (
        "observed" if current_listing is not None else "missing"
    )
    previous_count = previous_listing.rating_count if previous_listing is not None else None
    current_count = current_listing.rating_count if current_listing is not None else None

    status = _measurement_status(
        previous_presence,
        current_presence,
        previous_count,
        current_count,
    )
    if status != "comparable":
        return ListingLongitudinalFact(
            app_id=app_id,
            previous_presence=previous_presence,
            current_presence=current_presence,
            rating_count_previous=previous_count,
            rating_count_current=current_count,
            measurement_status=status,
            revision_status="unavailable",
        )

    assert previous_count is not None
    assert current_count is not None
    delta = current_count - previous_count
    return ListingLongitudinalFact(
        app_id=app_id,
        previous_presence=previous_presence,
        current_presence=current_presence,
        rating_count_previous=previous_count,
        rating_count_current=current_count,
        rating_count_delta=delta,
        observed_rating_delta_per_day=delta / elapsed_days,
        measurement_status="comparable",
        revision_status=_revision_status(delta),
    )


def _measurement_status(
    previous_presence: Literal["observed", "missing"],
    current_presence: Literal["observed", "missing"],
    previous_count: int | None,
    current_count: int | None,
) -> Literal[
    "comparable",
    "missing_previous",
    "missing_current",
    "missing_both",
    "metric_missing_previous",
    "metric_missing_current",
    "metric_missing_both",
]:
    if previous_presence == "missing" and current_presence == "missing":
        return "missing_both"
    if previous_presence == "missing":
        return "missing_previous"
    if current_presence == "missing":
        return "missing_current"
    if previous_count is None and current_count is None:
        return "metric_missing_both"
    if previous_count is None:
        return "metric_missing_previous"
    if current_count is None:
        return "metric_missing_current"
    return "comparable"


def _revision_status(
    delta: int,
) -> Literal["increase", "unchanged", "revision_decrease"]:
    if delta > 0:
        return "increase"
    if delta < 0:
        return "revision_decrease"
    return "unchanged"


def _write_create_only_json(path: Path, model: BaseModel) -> None:
    payload = json.dumps(
        model.model_dump(mode="json"),
        sort_keys=True,
        indent=2,
        ensure_ascii=False,
    ) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
    except FileExistsError as exc:
        raise ListingObservationError(
            f"refusing to overwrite existing longitudinal comparison: {path}"
        ) from exc
    except OSError as exc:
        raise ListingObservationError(str(exc)) from exc


def _require_sha256(value: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError("expected lowercase SHA-256 hex digest")
