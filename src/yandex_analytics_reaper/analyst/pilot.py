from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from yandex_analytics_reaper.storage import FilesystemRawSnapshotStore

from .export import (
    AnalystEvidenceReference,
    AnalystListingRow,
    AnalystMarketExportReport,
    AnalystResolvedValue,
    validate_analyst_market_export,
)
from .features import (
    AnalystCoverage,
    AnalystMarketFeatureBuilder,
    AnalystMarketFeaturesReport,
    AnalystNumericDistribution,
    validate_analyst_market_features,
)
from .snapshot import AnalystSnapshotReport, validate_analyst_snapshot_report

ANALYST_PILOT_VERIFICATION_SPEC_VERSION: Literal["analyst-pilot-verification-v1"] = (
    "analyst-pilot-verification-v1"
)
_YANDEX_SOURCE_ID = "yandex_public"


class AnalystPilotError(ValueError):
    """The real analyst pilot cannot be verified without weakening its evidence contract."""


class AnalystTraceContribution(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    platform_listing_id: str
    source_value: str | int | float
    derived_numeric_value: float
    observation_id: str
    raw_snapshot_ids: tuple[str, ...] = Field(min_length=1)
    source_field_paths: tuple[str, ...] = Field(min_length=1)
    normalizer_name: str
    normalizer_version: str


class AnalystNumericFeatureTrace(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    feature_name: Literal[
        "yandex_games_rating",
        "player_rating",
        "rating_count",
        "first_published_age_days",
    ]
    coverage: AnalystCoverage
    minimum: float
    p25: float
    median: float
    p75: float
    maximum: float
    mean: float
    contributions: tuple[AnalystTraceContribution, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_trace(self) -> Self:
        if len(self.contributions) != self.coverage.observed_count:
            raise ValueError("trace contribution count must match observed coverage")
        if self.coverage.observed_count < 1:
            raise ValueError("numeric feature trace requires at least one observed value")
        values = sorted(item.derived_numeric_value for item in self.contributions)
        expected = _numeric_summary(values)
        actual = (self.minimum, self.p25, self.median, self.p75, self.maximum, self.mean)
        for expected_value, actual_value in zip(expected, actual, strict=True):
            if not math.isclose(expected_value, actual_value, rel_tol=0.0, abs_tol=1e-12):
                raise ValueError("trace numeric summary does not match contributions")
        return self


class AnalystPilotSetVerification(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    set_id: str
    set_version: int = Field(ge=1)
    member_count: int = Field(ge=1)
    traces: tuple[AnalystNumericFeatureTrace, ...] = Field(min_length=1)


class AnalystRawEvidenceVerification(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    raw_root: str
    referenced_raw_snapshot_count: int = Field(ge=1)
    verified_raw_snapshot_count: int = Field(ge=1)
    raw_snapshot_ids: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        if self.referenced_raw_snapshot_count != len(self.raw_snapshot_ids):
            raise ValueError("referenced raw count does not match raw_snapshot_ids")
        if self.verified_raw_snapshot_count != self.referenced_raw_snapshot_count:
            raise ValueError("every referenced raw snapshot must be verified")
        if len(set(self.raw_snapshot_ids)) != len(self.raw_snapshot_ids):
            raise ValueError("raw_snapshot_ids must be unique")
        return self


class AnalystPilotVerificationPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: Literal["analyst-pilot-verification-v1"]
    snapshot_id: str
    snapshot_content_hash: str
    market_export_content_hash: str
    market_features_content_hash: str
    collection_parameters_status: Literal["provisional_uncalibrated"]
    comparable_set_count: int = Field(ge=2)
    comparable_sets: tuple[AnalystPilotSetVerification, ...] = Field(min_length=2)
    raw_evidence: AnalystRawEvidenceVerification
    machine_detected_limitations: tuple[str, ...] = Field(min_length=1)

    @field_validator(
        "snapshot_content_hash",
        "market_export_content_hash",
        "market_features_content_hash",
    )
    @classmethod
    def validate_hash(cls, value: str) -> str:
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise ValueError("pilot input hashes must be lowercase SHA-256 hex digests")
        return value

    @model_validator(mode="after")
    def validate_set_count(self) -> Self:
        if self.comparable_set_count != len(self.comparable_sets):
            raise ValueError("comparable_set_count does not match comparable_sets")
        keys = [(item.set_id, item.set_version) for item in self.comparable_sets]
        if len(set(keys)) != len(keys):
            raise ValueError("pilot comparable-set identities must be unique")
        return self


class AnalystPilotVerificationReport(AnalystPilotVerificationPayload):
    content_hash: str

    @field_validator("content_hash")
    @classmethod
    def validate_content_hash(cls, value: str) -> str:
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise ValueError("pilot content_hash must be a lowercase SHA-256 hex digest")
        return value


class AnalystPilotVerifier:
    """Verify that a real M1 pilot remains reproducible down to immutable raw evidence."""

    def __init__(self, *, raw_store: FilesystemRawSnapshotStore) -> None:
        self.raw_store = raw_store

    def build(
        self,
        snapshot: AnalystSnapshotReport,
        market_export: AnalystMarketExportReport,
        market_features: AnalystMarketFeaturesReport,
    ) -> AnalystPilotVerificationReport:
        snapshot = validate_analyst_snapshot_report(snapshot)
        market_export = validate_analyst_market_export(market_export)
        market_features = validate_analyst_market_features(market_features)
        _validate_artifact_chain(snapshot, market_export, market_features)

        if len(snapshot.comparable_sets) < 2:
            raise AnalystPilotError("real analyst pilot requires at least two comparable sets")

        recomputed_features = AnalystMarketFeatureBuilder().build(snapshot, market_export)
        if recomputed_features != market_features:
            raise AnalystPilotError(
                "market feature artifact does not match a fresh derivation from snapshot/export"
            )

        rows_by_id = {item.platform_listing_id: item for item in market_export.listings}
        set_reports: list[AnalystPilotSetVerification] = []
        for binding, features in zip(
            snapshot.comparable_sets,
            market_features.comparable_sets,
            strict=True,
        ):
            if (binding.set_id, binding.version) != (features.set_id, features.set_version):
                raise AnalystPilotError("snapshot/features comparable-set order or identity changed")
            rows = tuple(rows_by_id[listing_id] for listing_id in binding.member_listing_ids)
            traces = _build_traces(rows, features, snapshot.created_at)
            if not traces:
                raise AnalystPilotError(
                    f"comparable set {binding.set_id}@{binding.version} has no traceable "
                    "quantitative rich-metadata feature"
                )
            set_reports.append(
                AnalystPilotSetVerification(
                    set_id=binding.set_id,
                    set_version=binding.version,
                    member_count=len(binding.member_listing_ids),
                    traces=traces,
                )
            )

        raw_ids = _referenced_raw_snapshot_ids(snapshot, market_export)
        _verify_raw_evidence(self.raw_store, snapshot, raw_ids)
        raw_evidence = AnalystRawEvidenceVerification(
            raw_root=str(Path(self.raw_store.root)),
            referenced_raw_snapshot_count=len(raw_ids),
            verified_raw_snapshot_count=len(raw_ids),
            raw_snapshot_ids=raw_ids,
        )
        limitations = _machine_detected_limitations(snapshot, market_features)

        payload = AnalystPilotVerificationPayload(
            spec_version=ANALYST_PILOT_VERIFICATION_SPEC_VERSION,
            snapshot_id=snapshot.snapshot_id,
            snapshot_content_hash=snapshot.content_hash,
            market_export_content_hash=market_export.content_hash,
            market_features_content_hash=market_features.content_hash,
            collection_parameters_status=snapshot.collection_parameters_status,
            comparable_set_count=len(set_reports),
            comparable_sets=tuple(set_reports),
            raw_evidence=raw_evidence,
            machine_detected_limitations=limitations,
        )
        return AnalystPilotVerificationReport.model_validate(
            {**payload.model_dump(mode="python"), "content_hash": _payload_hash(payload)}
        )


def validate_analyst_pilot_verification(
    report: AnalystPilotVerificationReport,
) -> AnalystPilotVerificationReport:
    validated = AnalystPilotVerificationReport.model_validate(report.model_dump(mode="python"))
    payload = AnalystPilotVerificationPayload.model_validate(
        validated.model_dump(mode="python", exclude={"content_hash"})
    )
    if validated.content_hash != _payload_hash(payload):
        raise AnalystPilotError("analyst pilot content_hash does not match report content")
    return validated


def _validate_artifact_chain(
    snapshot: AnalystSnapshotReport,
    market_export: AnalystMarketExportReport,
    market_features: AnalystMarketFeaturesReport,
) -> None:
    if market_export.snapshot_id != snapshot.snapshot_id:
        raise AnalystPilotError("market export snapshot_id does not match snapshot")
    if market_export.snapshot_content_hash != snapshot.content_hash:
        raise AnalystPilotError("market export is not bound to the supplied snapshot")
    if market_features.snapshot_id != snapshot.snapshot_id:
        raise AnalystPilotError("market features snapshot_id does not match snapshot")
    if market_features.snapshot_content_hash != snapshot.content_hash:
        raise AnalystPilotError("market features are not bound to the supplied snapshot")
    if market_features.market_export_content_hash != market_export.content_hash:
        raise AnalystPilotError("market features are not bound to the supplied market export")
    if market_features.reference_time != snapshot.created_at:
        raise AnalystPilotError("market feature reference time changed from snapshot.created_at")
    if (
        market_export.collection_parameters_status != snapshot.collection_parameters_status
        or market_features.collection_parameters_status != snapshot.collection_parameters_status
    ):
        raise AnalystPilotError("collection-parameter status changed across pilot artifacts")


def _build_traces(
    rows: Sequence[AnalystListingRow],
    features: object,
    reference_time: datetime,
) -> tuple[AnalystNumericFeatureTrace, ...]:
    from .features import AnalystComparableSetFeatures

    typed_features = AnalystComparableSetFeatures.model_validate(features)
    traces: list[AnalystNumericFeatureTrace] = []
    numeric_specs: tuple[
        tuple[
            Literal["yandex_games_rating", "player_rating", "rating_count"],
            Callable[[AnalystListingRow], AnalystResolvedValue],
            AnalystNumericDistribution,
        ],
        ...,
    ] = (
        (
            "yandex_games_rating",
            lambda row: row.yandex_games_rating,
            typed_features.yandex_games_rating,
        ),
        ("player_rating", lambda row: row.player_rating, typed_features.player_rating),
        ("rating_count", lambda row: row.rating_count, typed_features.rating_count),
    )
    for feature_name, selector, distribution in numeric_specs:
        trace = _trace_numeric_feature(rows, feature_name, selector, distribution)
        if trace is not None:
            traces.append(trace)

    release_trace = _trace_release_feature(
        rows,
        typed_features.first_published.age_days,
        reference_time,
    )
    if release_trace is not None:
        traces.append(release_trace)
    return tuple(traces)


def _trace_numeric_feature(
    rows: Sequence[AnalystListingRow],
    feature_name: Literal["yandex_games_rating", "player_rating", "rating_count"],
    selector: Callable[[AnalystListingRow], AnalystResolvedValue],
    distribution: AnalystNumericDistribution,
) -> AnalystNumericFeatureTrace | None:
    contributions: list[AnalystTraceContribution] = []
    for row in rows:
        resolved = selector(row)
        if resolved.value is None:
            continue
        if isinstance(resolved.value, bool) or not isinstance(resolved.value, (int, float)):
            raise AnalystPilotError(
                f"{feature_name} for {row.platform_listing_id} is not numeric"
            )
        evidence = _required_evidence(resolved, feature_name, row.platform_listing_id)
        number = float(resolved.value)
        contributions.append(
            _trace_contribution(
                row.platform_listing_id,
                resolved.value,
                number,
                evidence,
            )
        )
    if not contributions:
        if distribution.coverage.observed_count != 0:
            raise AnalystPilotError(f"{feature_name} coverage does not match listing evidence")
        return None
    return _make_trace(feature_name, distribution, contributions)


def _trace_release_feature(
    rows: Sequence[AnalystListingRow],
    distribution: AnalystNumericDistribution,
    reference_time: datetime,
) -> AnalystNumericFeatureTrace | None:
    reference = _utc(reference_time)
    contributions: list[AnalystTraceContribution] = []
    for row in rows:
        resolved = row.first_published_at
        if resolved.value is None:
            continue
        if not isinstance(resolved.value, str):
            raise AnalystPilotError(
                f"first_published_at for {row.platform_listing_id} is not a timestamp string"
            )
        evidence = _required_evidence(
            resolved,
            "first_published_at",
            row.platform_listing_id,
        )
        published = _parse_timestamp(resolved.value)
        age_days = (reference - published).total_seconds() / 86_400
        if age_days < 0:
            raise AnalystPilotError(
                f"first_published_at for {row.platform_listing_id} is after snapshot time"
            )
        contributions.append(
            _trace_contribution(
                row.platform_listing_id,
                resolved.value,
                age_days,
                evidence,
            )
        )
    if not contributions:
        if distribution.coverage.observed_count != 0:
            raise AnalystPilotError("first_published coverage does not match listing evidence")
        return None
    return _make_trace("first_published_age_days", distribution, contributions)


def _make_trace(
    feature_name: Literal[
        "yandex_games_rating",
        "player_rating",
        "rating_count",
        "first_published_age_days",
    ],
    distribution: AnalystNumericDistribution,
    contributions: Sequence[AnalystTraceContribution],
) -> AnalystNumericFeatureTrace:
    values = [item.derived_numeric_value for item in contributions]
    summary = _numeric_summary(values)
    reported = (
        _required_float(distribution.minimum),
        _required_float(distribution.p25),
        _required_float(distribution.median),
        _required_float(distribution.p75),
        _required_float(distribution.maximum),
        _required_float(distribution.mean),
    )
    for expected, actual in zip(summary, reported, strict=True):
        if not math.isclose(expected, actual, rel_tol=0.0, abs_tol=1e-12):
            raise AnalystPilotError(f"{feature_name} aggregate does not match traced contributions")
    if distribution.coverage.observed_count != len(contributions):
        raise AnalystPilotError(f"{feature_name} coverage does not match traced contributions")
    return AnalystNumericFeatureTrace(
        feature_name=feature_name,
        coverage=distribution.coverage,
        minimum=summary[0],
        p25=summary[1],
        median=summary[2],
        p75=summary[3],
        maximum=summary[4],
        mean=summary[5],
        contributions=tuple(contributions),
    )


def _trace_contribution(
    platform_listing_id: str,
    source_value: str | int | float,
    derived_numeric_value: float,
    evidence: AnalystEvidenceReference,
) -> AnalystTraceContribution:
    return AnalystTraceContribution(
        platform_listing_id=platform_listing_id,
        source_value=source_value,
        derived_numeric_value=derived_numeric_value,
        observation_id=evidence.observation_id,
        raw_snapshot_ids=evidence.raw_snapshot_ids,
        source_field_paths=evidence.source_field_paths,
        normalizer_name=evidence.normalizer_name,
        normalizer_version=evidence.normalizer_version,
    )


def _required_evidence(
    resolved: AnalystResolvedValue,
    field_name: str,
    listing_id: str,
) -> AnalystEvidenceReference:
    if resolved.evidence is None:
        raise AnalystPilotError(f"observed {field_name} for {listing_id} has no evidence")
    return resolved.evidence


def _referenced_raw_snapshot_ids(
    snapshot: AnalystSnapshotReport,
    market_export: AnalystMarketExportReport,
) -> tuple[str, ...]:
    raw_ids: set[str] = {item.raw_snapshot_id for item in snapshot.rich_metadata}
    for membership in market_export.comparable_memberships:
        raw_ids.update(membership.raw_snapshot_ids)
    for update in market_export.update_observations:
        raw_ids.update(update.raw_snapshot_ids)
    for supply in market_export.search_supply:
        raw_ids.add(supply.raw_snapshot_id)
    for exposure in market_export.search_exposures:
        raw_ids.add(exposure.raw_snapshot_id)
    for exposure in market_export.feed_exposures:
        raw_ids.add(exposure.raw_snapshot_id)
    for listing in market_export.listings:
        for resolved in _listing_resolved_values(listing):
            if resolved.evidence is not None:
                raw_ids.update(resolved.evidence.raw_snapshot_ids)
    if not raw_ids:
        raise AnalystPilotError("pilot artifacts contain no raw evidence references")
    return tuple(sorted(raw_ids))


def _listing_resolved_values(listing: AnalystListingRow) -> tuple[AnalystResolvedValue, ...]:
    return (
        listing.title,
        listing.developer_id,
        listing.developer_name,
        listing.first_published_at,
        listing.app_version,
        listing.published_at,
        listing.languages,
        listing.supported_platforms,
        listing.orientation,
        listing.cloud_save,
        listing.leaderboards,
        listing.purchases_enabled,
        listing.has_products,
        listing.rewarded_ads,
        listing.fullscreen_ads,
        listing.sticky_ads,
        listing.yandex_games_rating,
        listing.player_rating,
        listing.rating_count,
    )


def _verify_raw_evidence(
    raw_store: FilesystemRawSnapshotStore,
    snapshot: AnalystSnapshotReport,
    raw_ids: Sequence[str],
) -> None:
    rich_by_id = {item.raw_snapshot_id: item for item in snapshot.rich_metadata}
    for raw_id in raw_ids:
        try:
            metadata = raw_store.get_metadata(_YANDEX_SOURCE_ID, raw_id)
            raw_store.get_body(_YANDEX_SOURCE_ID, raw_id)
        except (OSError, ValueError) as exc:
            raise AnalystPilotError(f"raw evidence replay failed for {raw_id}: {exc}") from exc
        rich = rich_by_id.get(raw_id)
        if rich is None:
            continue
        if metadata.request_key != rich.request_key:
            raise AnalystPilotError(f"rich raw request_key changed for {raw_id}")
        if metadata.content_hash != rich.content_hash:
            raise AnalystPilotError(f"rich raw content_hash changed for {raw_id}")
        if metadata.retrieved_at != rich.retrieved_at:
            raise AnalystPilotError(f"rich raw retrieved_at changed for {raw_id}")


def _machine_detected_limitations(
    snapshot: AnalystSnapshotReport,
    market_features: AnalystMarketFeaturesReport,
) -> tuple[str, ...]:
    limitations: list[str] = [
        "collection parameters remain provisional_uncalibrated until calibration tracks finish"
    ]
    if not snapshot.feed_runs:
        limitations.append("feed exposure was not collected for this pilot snapshot")
    for features in market_features.comparable_sets:
        label = f"{features.set_id}@{features.set_version}"
        coverage_items = (
            ("gqRating", features.yandex_games_rating.coverage),
            ("player_rating", features.player_rating.coverage),
            ("ratingCount", features.rating_count.coverage),
            ("firstPublished", features.first_published.age_days.coverage),
            ("developer_id", features.developer_composition.coverage),
        )
        for field_name, coverage in coverage_items:
            if coverage.missing_count:
                limitations.append(
                    f"{label} {field_name} missing for "
                    f"{coverage.missing_count}/{coverage.total_count} comparable members"
                )
        for supply in features.query_supply:
            if supply.consistent_across_observed_pages is False:
                limitations.append(
                    f"{label} query {supply.query_text!r} returned inconsistent "
                    "totalGamesCount values across observed pages"
                )
            elif supply.consistent_across_observed_pages is None:
                limitations.append(
                    f"{label} query {supply.query_text!r} had no observed totalGamesCount"
                )
    return tuple(limitations)


def _numeric_summary(values: Sequence[float]) -> tuple[float, float, float, float, float, float]:
    if not values:
        raise AnalystPilotError("cannot summarize an empty trace")
    ordered = sorted(values)
    return (
        ordered[0],
        _percentile(ordered, 0.25),
        _percentile(ordered, 0.50),
        _percentile(ordered, 0.75),
        ordered[-1],
        math.fsum(ordered) / len(ordered),
    )


def _percentile(values: Sequence[float], fraction: float) -> float:
    index = (len(values) - 1) * fraction
    lower_index = math.floor(index)
    upper_index = math.ceil(index)
    lower = values[lower_index]
    upper = values[upper_index]
    if lower_index == upper_index:
        return lower
    return lower + (upper - lower) * (index - lower_index)


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AnalystPilotError(f"invalid exported timestamp: {value}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AnalystPilotError("exported timestamp must be timezone-aware")
    return parsed.astimezone(UTC)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise AnalystPilotError("pilot reference time must be timezone-aware")
    return value.astimezone(UTC)


def _required_float(value: float | None) -> float:
    if value is None:
        raise AnalystPilotError("traceable distribution is missing a numeric summary")
    return value


def _payload_hash(payload: AnalystPilotVerificationPayload) -> str:
    encoded = json.dumps(
        payload.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
