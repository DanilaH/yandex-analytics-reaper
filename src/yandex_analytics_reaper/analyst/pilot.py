from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from statistics import median
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
    AnalystComparableSetFeatures,
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


class AnalystPilotTraceContribution(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    platform_listing_id: str
    source_value: str | int | float
    numeric_value: float
    observation_id: str
    raw_snapshot_ids: tuple[str, ...] = Field(min_length=1)
    source_field_paths: tuple[str, ...] = Field(min_length=1)
    normalizer_name: str
    normalizer_version: str


class AnalystPilotRepresentativeTrace(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    set_id: str
    set_version: int = Field(ge=1)
    feature_name: Literal[
        "rating_count",
        "yandex_games_rating",
        "player_rating",
        "first_published_age_days",
    ]
    coverage: AnalystCoverage
    reported_median: float
    recomputed_median: float
    contributions: tuple[AnalystPilotTraceContribution, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_trace(self) -> Self:
        if len(self.contributions) != self.coverage.observed_count:
            raise ValueError("trace contribution count must match observed coverage")
        expected = float(median(item.numeric_value for item in self.contributions))
        if not math.isclose(self.recomputed_median, expected, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError("recomputed_median does not match trace contributions")
        if not math.isclose(
            self.reported_median,
            self.recomputed_median,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("reported feature median does not match trace median")
        return self


class AnalystRawEvidenceVerification(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

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
    query_family_ids: tuple[str, ...] = Field(min_length=2)
    representative_traces: tuple[AnalystPilotRepresentativeTrace, ...] = Field(min_length=2)
    raw_evidence: AnalystRawEvidenceVerification
    machine_detected_limitations: tuple[str, ...] = Field(min_length=1)

    @field_validator(
        "snapshot_content_hash",
        "market_export_content_hash",
        "market_features_content_hash",
    )
    @classmethod
    def validate_hash(cls, value: str) -> str:
        invalid = any(character not in "0123456789abcdef" for character in value)
        if len(value) != 64 or invalid:
            raise ValueError("pilot input hashes must be lowercase SHA-256 hex digests")
        return value

    @model_validator(mode="after")
    def validate_scope(self) -> Self:
        if len(set(self.query_family_ids)) != len(self.query_family_ids):
            raise ValueError("pilot query_family_ids must be unique")
        if self.comparable_set_count != len(self.representative_traces):
            raise ValueError("pilot requires one representative trace per comparable set")
        trace_keys = [(item.set_id, item.set_version) for item in self.representative_traces]
        if len(set(trace_keys)) != len(trace_keys):
            raise ValueError("pilot representative trace identities must be unique")
        return self


class AnalystPilotVerificationReport(AnalystPilotVerificationPayload):
    content_hash: str

    @field_validator("content_hash")
    @classmethod
    def validate_content_hash(cls, value: str) -> str:
        invalid = any(character not in "0123456789abcdef" for character in value)
        if len(value) != 64 or invalid:
            raise ValueError("pilot content_hash must be a lowercase SHA-256 hex digest")
        return value


class AnalystPilotVerifier:
    """Verify a real M1 pilot down to one representative aggregate and raw replay."""

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
        query_family_ids = tuple(
            dict.fromkeys(item.query_family_id for item in snapshot.comparable_sets)
        )
        if len(query_family_ids) < 2:
            raise AnalystPilotError(
                "real analyst pilot requires at least two distinct query families"
            )

        recomputed_features = AnalystMarketFeatureBuilder().build(snapshot, market_export)
        if recomputed_features != market_features:
            raise AnalystPilotError(
                "market feature artifact does not match a fresh derivation from snapshot/export"
            )

        rows_by_id = {item.platform_listing_id: item for item in market_export.listings}
        traces: list[AnalystPilotRepresentativeTrace] = []
        for binding, features in zip(
            snapshot.comparable_sets,
            market_features.comparable_sets,
            strict=True,
        ):
            if (binding.set_id, binding.version) != (features.set_id, features.set_version):
                raise AnalystPilotError("snapshot/features comparable-set order or identity changed")
            rows = tuple(rows_by_id[listing_id] for listing_id in binding.member_listing_ids)
            traces.append(
                _representative_trace(
                    rows,
                    features,
                    snapshot.created_at,
                )
            )

        expected_request_keys = _expected_raw_request_keys(snapshot, market_export)
        raw_ids = tuple(sorted(expected_request_keys))
        _verify_raw_evidence(self.raw_store, snapshot, expected_request_keys)
        raw_evidence = AnalystRawEvidenceVerification(
            referenced_raw_snapshot_count=len(raw_ids),
            verified_raw_snapshot_count=len(raw_ids),
            raw_snapshot_ids=raw_ids,
        )

        payload = AnalystPilotVerificationPayload(
            spec_version=ANALYST_PILOT_VERIFICATION_SPEC_VERSION,
            snapshot_id=snapshot.snapshot_id,
            snapshot_content_hash=snapshot.content_hash,
            market_export_content_hash=market_export.content_hash,
            market_features_content_hash=market_features.content_hash,
            collection_parameters_status=snapshot.collection_parameters_status,
            comparable_set_count=len(snapshot.comparable_sets),
            query_family_ids=query_family_ids,
            representative_traces=tuple(traces),
            raw_evidence=raw_evidence,
            machine_detected_limitations=_machine_detected_limitations(
                snapshot,
                market_features,
            ),
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


def _representative_trace(
    rows: Sequence[AnalystListingRow],
    features: AnalystComparableSetFeatures,
    reference_time: datetime,
) -> AnalystPilotRepresentativeTrace:
    numeric_candidates: tuple[
        tuple[
            Literal["rating_count", "yandex_games_rating", "player_rating"],
            Callable[[AnalystListingRow], AnalystResolvedValue],
            AnalystNumericDistribution,
        ],
        ...,
    ] = (
        ("rating_count", lambda row: row.rating_count, features.rating_count),
        (
            "yandex_games_rating",
            lambda row: row.yandex_games_rating,
            features.yandex_games_rating,
        ),
        ("player_rating", lambda row: row.player_rating, features.player_rating),
    )
    for feature_name, selector, distribution in numeric_candidates:
        if distribution.coverage.observed_count:
            return _numeric_trace(
                rows,
                features.set_id,
                features.set_version,
                feature_name,
                selector,
                distribution,
            )

    if features.first_published.age_days.coverage.observed_count:
        return _release_trace(
            rows,
            features,
            reference_time,
        )
    raise AnalystPilotError(
        f"comparable set {features.set_id}@{features.set_version} has no traceable "
        "quantitative rich-metadata feature"
    )


def _numeric_trace(
    rows: Sequence[AnalystListingRow],
    set_id: str,
    set_version: int,
    feature_name: Literal["rating_count", "yandex_games_rating", "player_rating"],
    selector: Callable[[AnalystListingRow], AnalystResolvedValue],
    distribution: AnalystNumericDistribution,
) -> AnalystPilotRepresentativeTrace:
    contributions: list[AnalystPilotTraceContribution] = []
    for row in rows:
        resolved = selector(row)
        if resolved.value is None:
            continue
        if isinstance(resolved.value, bool) or not isinstance(resolved.value, (int, float)):
            raise AnalystPilotError(
                f"{feature_name} for {row.platform_listing_id} is not numeric"
            )
        evidence = _required_evidence(resolved, feature_name, row.platform_listing_id)
        contributions.append(
            _contribution(
                row.platform_listing_id,
                resolved.value,
                float(resolved.value),
                evidence,
            )
        )
    return _trace_from_contributions(
        set_id,
        set_version,
        feature_name,
        distribution,
        contributions,
    )


def _release_trace(
    rows: Sequence[AnalystListingRow],
    features: AnalystComparableSetFeatures,
    reference_time: datetime,
) -> AnalystPilotRepresentativeTrace:
    reference = _utc(reference_time)
    contributions: list[AnalystPilotTraceContribution] = []
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
            _contribution(
                row.platform_listing_id,
                resolved.value,
                age_days,
                evidence,
            )
        )
    return _trace_from_contributions(
        features.set_id,
        features.set_version,
        "first_published_age_days",
        features.first_published.age_days,
        contributions,
    )


def _trace_from_contributions(
    set_id: str,
    set_version: int,
    feature_name: Literal[
        "rating_count",
        "yandex_games_rating",
        "player_rating",
        "first_published_age_days",
    ],
    distribution: AnalystNumericDistribution,
    contributions: Sequence[AnalystPilotTraceContribution],
) -> AnalystPilotRepresentativeTrace:
    if not contributions:
        raise AnalystPilotError(f"{feature_name} has observed coverage but no trace contributions")
    if distribution.coverage.observed_count != len(contributions):
        raise AnalystPilotError(f"{feature_name} coverage does not match trace contributions")
    reported_median = _required_float(distribution.median)
    recomputed_median = float(median(item.numeric_value for item in contributions))
    if not math.isclose(reported_median, recomputed_median, rel_tol=0.0, abs_tol=1e-12):
        raise AnalystPilotError(f"{feature_name} median does not match trace contributions")
    return AnalystPilotRepresentativeTrace(
        set_id=set_id,
        set_version=set_version,
        feature_name=feature_name,
        coverage=distribution.coverage,
        reported_median=reported_median,
        recomputed_median=recomputed_median,
        contributions=tuple(contributions),
    )


def _contribution(
    platform_listing_id: str,
    source_value: str | int | float,
    numeric_value: float,
    evidence: AnalystEvidenceReference,
) -> AnalystPilotTraceContribution:
    return AnalystPilotTraceContribution(
        platform_listing_id=platform_listing_id,
        source_value=source_value,
        numeric_value=numeric_value,
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


def _expected_raw_request_keys(
    snapshot: AnalystSnapshotReport,
    market_export: AnalystMarketExportReport,
) -> dict[str, str]:
    expected: dict[str, str] = {}
    rich_ids = {item.raw_snapshot_id for item in snapshot.rich_metadata}

    for rich in snapshot.rich_metadata:
        _bind_raw_request_key(expected, rich.raw_snapshot_id, rich.request_key)
    for feed_run in snapshot.feed_runs:
        for raw_id in feed_run.raw_snapshot_ids:
            _bind_raw_request_key(expected, raw_id, "catalogue.feed")
    for membership in market_export.comparable_memberships:
        for raw_id in membership.raw_snapshot_ids:
            _bind_raw_request_key(expected, raw_id, "catalogue.search")
    for supply in market_export.search_supply:
        _bind_raw_request_key(expected, supply.raw_snapshot_id, "catalogue.search")
    for exposure in market_export.search_exposures:
        _bind_raw_request_key(expected, exposure.raw_snapshot_id, "catalogue.search")
    for exposure in market_export.feed_exposures:
        _bind_raw_request_key(expected, exposure.raw_snapshot_id, "catalogue.feed")

    for update in market_export.update_observations:
        _require_rich_raw_refs(update.raw_snapshot_ids, rich_ids, "update observation")
    for listing in market_export.listings:
        for resolved in _listing_resolved_values(listing):
            if resolved.evidence is not None:
                _require_rich_raw_refs(
                    resolved.evidence.raw_snapshot_ids,
                    rich_ids,
                    f"listing evidence for {listing.platform_listing_id}",
                )
    if not expected:
        raise AnalystPilotError("pilot artifacts contain no raw evidence references")
    return expected


def _bind_raw_request_key(expected: dict[str, str], raw_id: str, request_key: str) -> None:
    previous = expected.get(raw_id)
    if previous is not None and previous != request_key:
        raise AnalystPilotError(
            f"raw snapshot {raw_id} is claimed by incompatible request keys: "
            f"{previous} vs {request_key}"
        )
    expected[raw_id] = request_key


def _require_rich_raw_refs(
    raw_ids: Sequence[str],
    rich_ids: set[str],
    label: str,
) -> None:
    escaped = sorted(set(raw_ids) - rich_ids)
    if escaped:
        raise AnalystPilotError(
            f"{label} references raw snapshots outside frozen rich metadata: {escaped}"
        )


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
    expected_request_keys: dict[str, str],
) -> None:
    rich_by_id = {item.raw_snapshot_id: item for item in snapshot.rich_metadata}
    for raw_id, expected_request_key in sorted(expected_request_keys.items()):
        try:
            metadata = raw_store.get_metadata(_YANDEX_SOURCE_ID, raw_id)
            raw_store.get_body(_YANDEX_SOURCE_ID, raw_id)
        except (OSError, ValueError) as exc:
            raise AnalystPilotError(f"raw evidence replay failed for {raw_id}: {exc}") from exc
        if metadata.request_key != expected_request_key:
            raise AnalystPilotError(
                f"raw request_key changed for {raw_id}: "
                f"expected {expected_request_key}, got {metadata.request_key}"
            )
        rich = rich_by_id.get(raw_id)
        if rich is None:
            continue
        if metadata.content_hash != rich.content_hash:
            raise AnalystPilotError(f"rich raw content_hash changed for {raw_id}")
        if metadata.retrieved_at != rich.retrieved_at:
            raise AnalystPilotError(f"rich raw retrieved_at changed for {raw_id}")


def _machine_detected_limitations(
    snapshot: AnalystSnapshotReport,
    market_features: AnalystMarketFeaturesReport,
) -> tuple[str, ...]:
    limitations: list[str] = [
        "collection parameters remain provisional_uncalibrated until calibration tracks finish",
        (
            "search-derived comparable sets remain provisional candidate peer sets "
            "until taxonomy validation"
        ),
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
        raise AnalystPilotError("traceable distribution is missing a median")
    return value


def _payload_hash(payload: AnalystPilotVerificationPayload) -> str:
    encoded = json.dumps(
        payload.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()