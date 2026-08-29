from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from .export import (
    AnalystListingRow,
    AnalystMarketExportReport,
    AnalystResolvedValue,
    AnalystSearchSupplyObservation,
    validate_analyst_market_export,
)
from .snapshot import (
    AnalystComparableSetBinding,
    AnalystSnapshotReport,
    validate_analyst_snapshot_report,
)

ANALYST_MARKET_FEATURES_SPEC_VERSION: Literal["analyst-market-features-v1"] = (
    "analyst-market-features-v1"
)
_RELEASE_WINDOWS_DAYS = (30, 90, 180, 365)


class AnalystFeatureError(ValueError):
    """Frozen analyst inputs cannot produce an honest deterministic feature report."""


class AnalystCoverage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    total_count: int = Field(ge=1)
    observed_count: int = Field(ge=0)
    missing_count: int = Field(ge=0)
    coverage_ratio: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        if self.observed_count > self.total_count:
            raise ValueError("observed_count cannot exceed total_count")
        if self.missing_count != self.total_count - self.observed_count:
            raise ValueError("missing_count must equal total_count - observed_count")
        expected = self.observed_count / self.total_count
        if not math.isclose(self.coverage_ratio, expected, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError("coverage_ratio does not match coverage counts")
        return self


class AnalystNumericDistribution(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    coverage: AnalystCoverage
    minimum: float | None = None
    p25: float | None = None
    median: float | None = None
    p75: float | None = None
    maximum: float | None = None
    mean: float | None = None

    @model_validator(mode="after")
    def validate_distribution(self) -> Self:
        values = (self.minimum, self.p25, self.median, self.p75, self.maximum, self.mean)
        if self.coverage.observed_count == 0:
            if any(value is not None for value in values):
                raise ValueError("empty distribution cannot contain numeric summaries")
            return self
        if any(value is None for value in values):
            raise ValueError("observed distribution requires all numeric summaries")
        minimum = _required_float(self.minimum)
        p25 = _required_float(self.p25)
        median = _required_float(self.median)
        p75 = _required_float(self.p75)
        maximum = _required_float(self.maximum)
        mean = _required_float(self.mean)
        if not minimum <= p25 <= median <= p75 <= maximum:
            raise ValueError("distribution quantiles are not monotonic")
        if not minimum <= mean <= maximum:
            raise ValueError("distribution mean must lie inside the observed range")
        return self


class AnalystReleaseWindow(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_age_days: int = Field(gt=0)
    listing_count: int = Field(ge=0)
    share_of_observed: float | None = Field(default=None, ge=0.0, le=1.0)


class AnalystReleaseDistribution(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    age_days: AnalystNumericDistribution
    windows: tuple[AnalystReleaseWindow, ...]

    @model_validator(mode="after")
    def validate_windows(self) -> Self:
        if tuple(item.max_age_days for item in self.windows) != _RELEASE_WINDOWS_DAYS:
            raise ValueError("release windows must match the v1 descriptive windows")
        observed = self.age_days.coverage.observed_count
        previous = -1
        for item in self.windows:
            if item.listing_count < previous or item.listing_count > observed:
                raise ValueError("release-window counts must be cumulative and bounded")
            previous = item.listing_count
            if observed == 0:
                if item.share_of_observed is not None:
                    raise ValueError("empty release coverage cannot have window shares")
            else:
                expected = item.listing_count / observed
                if item.share_of_observed is None or not math.isclose(
                    item.share_of_observed,
                    expected,
                    rel_tol=0.0,
                    abs_tol=1e-12,
                ):
                    raise ValueError("release-window share does not match observed count")
        return self


class AnalystQuerySupplyPage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    page_index: int = Field(ge=0)
    raw_snapshot_id: str
    source_field_path: Literal["$.totalGamesCount"] | None = None
    total_games_count: int | None = Field(default=None, ge=0)
    missing_reason: Literal["source_missing"] | None = None

    @model_validator(mode="after")
    def validate_value(self) -> Self:
        if self.total_games_count is None:
            if self.missing_reason != "source_missing" or self.source_field_path is not None:
                raise ValueError("missing query supply requires source_missing and no source path")
        elif self.missing_reason is not None or self.source_field_path != "$.totalGamesCount":
            raise ValueError("observed query supply requires the exact totalGamesCount path")
        return self


class AnalystQuerySupplySummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    query_text: str
    probe_run_id: str
    pages: tuple[AnalystQuerySupplyPage, ...] = Field(min_length=1)
    observed_values: tuple[int, ...]
    distinct_observed_values: tuple[int, ...]
    consistent_across_observed_pages: bool | None

    @model_validator(mode="after")
    def validate_summary(self) -> Self:
        page_indices = tuple(item.page_index for item in self.pages)
        if page_indices != tuple(range(len(self.pages))):
            raise ValueError("query-supply pages must be contiguous from zero")
        expected_values = tuple(
            item.total_games_count
            for item in self.pages
            if item.total_games_count is not None
        )
        if self.observed_values != expected_values:
            raise ValueError("observed query-supply values do not match page observations")
        distinct = tuple(sorted(set(expected_values)))
        if self.distinct_observed_values != distinct:
            raise ValueError("distinct query-supply values do not match page observations")
        expected_consistency = None if not expected_values else len(distinct) == 1
        if self.consistent_across_observed_pages != expected_consistency:
            raise ValueError("query-supply consistency diagnostic does not match observations")
        return self


class AnalystExposureSurfaceSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    evidence_available: bool
    member_count: int = Field(ge=1)
    run_count: int = Field(ge=0)
    exposure_count: int = Field(ge=0)
    exposed_member_count: int = Field(ge=0)
    unexposed_member_count: int = Field(ge=0)
    member_coverage_ratio: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_surface(self) -> Self:
        if self.exposed_member_count > self.member_count:
            raise ValueError("exposed_member_count cannot exceed member_count")
        if self.unexposed_member_count != self.member_count - self.exposed_member_count:
            raise ValueError("unexposed_member_count does not match member coverage")
        if not self.evidence_available:
            if (
                self.run_count != 0
                or self.exposure_count != 0
                or self.exposed_member_count != 0
                or self.member_coverage_ratio is not None
            ):
                raise ValueError("unavailable exposure evidence must not claim observations")
            return self
        if self.run_count < 1:
            raise ValueError("available exposure evidence requires at least one run")
        expected = self.exposed_member_count / self.member_count
        if self.member_coverage_ratio is None or not math.isclose(
            self.member_coverage_ratio,
            expected,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("member_coverage_ratio does not match exposure counts")
        return self


class AnalystOrganicExposureSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    search: AnalystExposureSurfaceSummary
    feed: AnalystExposureSurfaceSummary


class AnalystDeveloperCompositionEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    developer_id: str
    developer_names: tuple[str, ...]
    listing_count: int = Field(ge=1)
    share_of_observed: float = Field(ge=0.0, le=1.0)


class AnalystDeveloperComposition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    coverage: AnalystCoverage
    distinct_developer_count: int = Field(ge=0)
    largest_developer_listing_count: int = Field(ge=0)
    largest_developer_share: float | None = Field(default=None, ge=0.0, le=1.0)
    developers: tuple[AnalystDeveloperCompositionEntry, ...]

    @model_validator(mode="after")
    def validate_composition(self) -> Self:
        observed = self.coverage.observed_count
        if len(self.developers) != self.distinct_developer_count:
            raise ValueError("distinct developer count does not match developer entries")
        if sum(item.listing_count for item in self.developers) != observed:
            raise ValueError("developer entries do not cover all observed developer IDs")
        if observed == 0:
            if (
                self.largest_developer_listing_count != 0
                or self.largest_developer_share is not None
                or self.developers
            ):
                raise ValueError("empty developer coverage cannot contain concentration data")
            return self
        largest = max(item.listing_count for item in self.developers)
        if self.largest_developer_listing_count != largest:
            raise ValueError("largest developer listing count does not match entries")
        expected_share = largest / observed
        if self.largest_developer_share is None or not math.isclose(
            self.largest_developer_share,
            expected_share,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("largest developer share does not match entries")
        for item in self.developers:
            expected = item.listing_count / observed
            if not math.isclose(item.share_of_observed, expected, rel_tol=0.0, abs_tol=1e-12):
                raise ValueError("developer share does not match listing count")
        return self


class AnalystComparableSetFeatures(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    set_id: str
    set_version: int = Field(ge=1)
    query_family_id: str
    query_family_version: int = Field(ge=1)
    member_listing_ids: tuple[str, ...] = Field(min_length=1)
    member_count: int = Field(ge=1)
    query_supply: tuple[AnalystQuerySupplySummary, ...] = Field(min_length=1)
    yandex_games_rating: AnalystNumericDistribution
    player_rating: AnalystNumericDistribution
    rating_count: AnalystNumericDistribution
    first_published: AnalystReleaseDistribution
    organic_exposure: AnalystOrganicExposureSummary
    developer_composition: AnalystDeveloperComposition

    @model_validator(mode="after")
    def validate_member_count(self) -> Self:
        if self.member_count != len(self.member_listing_ids):
            raise ValueError("member_count does not match member_listing_ids")
        if len(set(self.member_listing_ids)) != len(self.member_listing_ids):
            raise ValueError("member_listing_ids must be unique")
        for distribution in (
            self.yandex_games_rating,
            self.player_rating,
            self.rating_count,
            self.first_published.age_days,
        ):
            if distribution.coverage.total_count != self.member_count:
                raise ValueError("feature coverage denominator must equal member_count")
        if self.developer_composition.coverage.total_count != self.member_count:
            raise ValueError("developer coverage denominator must equal member_count")
        if (
            self.organic_exposure.search.member_count != self.member_count
            or self.organic_exposure.feed.member_count != self.member_count
        ):
            raise ValueError("exposure denominator must equal member_count")
        return self


class AnalystMarketFeaturesPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: Literal["analyst-market-features-v1"]
    snapshot_id: str
    snapshot_content_hash: str
    market_export_content_hash: str
    reference_time: AwareDatetime
    collection_parameters_status: Literal["provisional_uncalibrated"]
    comparable_sets: tuple[AnalystComparableSetFeatures, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_set_uniqueness(self) -> Self:
        keys = [(item.set_id, item.set_version) for item in self.comparable_sets]
        if len(set(keys)) != len(keys):
            raise ValueError("feature comparable-set identities must be unique")
        return self


class AnalystMarketFeaturesReport(AnalystMarketFeaturesPayload):
    content_hash: str

    @field_validator("snapshot_content_hash", "market_export_content_hash", "content_hash")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        invalid = any(character not in "0123456789abcdef" for character in value)
        if len(value) != 64 or invalid:
            raise ValueError("feature hashes must be lowercase SHA-256 hex digests")
        return value


class AnalystMarketFeatureBuilder:
    """Compute transparent comparable-market features from two frozen analyst artifacts."""

    def build(
        self,
        snapshot: AnalystSnapshotReport,
        market_export: AnalystMarketExportReport,
    ) -> AnalystMarketFeaturesReport:
        snapshot = validate_analyst_snapshot_report(snapshot)
        market_export = validate_analyst_market_export(market_export)
        _validate_input_pair(snapshot, market_export)
        rows_by_id = _listing_rows_by_id(snapshot, market_export)
        features = tuple(
            _build_set_features(snapshot, market_export, binding, rows_by_id)
            for binding in snapshot.comparable_sets
        )
        payload = AnalystMarketFeaturesPayload(
            spec_version=ANALYST_MARKET_FEATURES_SPEC_VERSION,
            snapshot_id=snapshot.snapshot_id,
            snapshot_content_hash=snapshot.content_hash,
            market_export_content_hash=market_export.content_hash,
            reference_time=snapshot.created_at,
            collection_parameters_status=snapshot.collection_parameters_status,
            comparable_sets=features,
        )
        return AnalystMarketFeaturesReport.model_validate(
            {**payload.model_dump(mode="python"), "content_hash": _payload_hash(payload)}
        )


def validate_analyst_market_features(
    report: AnalystMarketFeaturesReport,
) -> AnalystMarketFeaturesReport:
    validated = AnalystMarketFeaturesReport.model_validate(report.model_dump(mode="python"))
    payload = AnalystMarketFeaturesPayload.model_validate(
        validated.model_dump(mode="python", exclude={"content_hash"})
    )
    if validated.content_hash != _payload_hash(payload):
        raise AnalystFeatureError("analyst market feature content_hash does not match content")
    return validated


def _validate_input_pair(
    snapshot: AnalystSnapshotReport,
    market_export: AnalystMarketExportReport,
) -> None:
    if market_export.snapshot_id != snapshot.snapshot_id:
        raise AnalystFeatureError("market export snapshot_id does not match snapshot report")
    if market_export.snapshot_content_hash != snapshot.content_hash:
        raise AnalystFeatureError("market export is not bound to this snapshot content hash")
    if market_export.collection_parameters_status != snapshot.collection_parameters_status:
        raise AnalystFeatureError("market export collection-parameter status changed")
    if market_export.search_page_limit != snapshot.search_page_limit:
        raise AnalystFeatureError("market export search depth does not match snapshot")
    if market_export.effective_context != snapshot.effective_context.model_dump(mode="json"):
        raise AnalystFeatureError("market export effective context does not match snapshot")
    expected_raw_ids = tuple(item.raw_snapshot_id for item in snapshot.rich_metadata)
    if market_export.rich_metadata_raw_snapshot_ids != expected_raw_ids:
        raise AnalystFeatureError("market export rich-metadata bindings do not match snapshot")
    _validate_export_set_scope(snapshot, market_export)


def _validate_export_set_scope(
    snapshot: AnalystSnapshotReport,
    market_export: AnalystMarketExportReport,
) -> None:
    expected = {(item.set_id, item.version) for item in snapshot.comparable_sets}
    membership_keys = {
        (item.set_id, item.set_version) for item in market_export.comparable_memberships
    }
    supply_keys = {(item.set_id, item.set_version) for item in market_export.search_supply}
    exposure_keys = {
        (item.set_id, item.set_version) for item in market_export.search_exposures
    }
    if membership_keys != expected:
        raise AnalystFeatureError("market export comparable membership scope changed")
    if supply_keys != expected:
        raise AnalystFeatureError("market export query-supply scope changed")
    if exposure_keys != expected:
        raise AnalystFeatureError("market export search-exposure scope changed")


def _listing_rows_by_id(
    snapshot: AnalystSnapshotReport,
    market_export: AnalystMarketExportReport,
) -> dict[str, AnalystListingRow]:
    expected_order: list[str] = []
    expected_sets: dict[str, list[str]] = {}
    for binding in snapshot.comparable_sets:
        for listing_id in binding.member_listing_ids:
            if listing_id not in expected_sets:
                expected_order.append(listing_id)
                expected_sets[listing_id] = []
            expected_sets[listing_id].append(binding.set_id)
    actual_order = [item.platform_listing_id for item in market_export.listings]
    if actual_order != expected_order:
        raise AnalystFeatureError("market export listing order/membership does not match snapshot")
    rows = {item.platform_listing_id: item for item in market_export.listings}
    if len(rows) != len(market_export.listings):
        raise AnalystFeatureError("market export contains duplicate listing rows")
    for listing_id, set_ids in expected_sets.items():
        if rows[listing_id].comparable_set_ids != tuple(set_ids):
            raise AnalystFeatureError(
                f"market export comparable-set IDs changed for {listing_id}"
            )
    return rows


def _build_set_features(
    snapshot: AnalystSnapshotReport,
    market_export: AnalystMarketExportReport,
    binding: AnalystComparableSetBinding,
    rows_by_id: dict[str, AnalystListingRow],
) -> AnalystComparableSetFeatures:
    member_ids = binding.member_listing_ids
    member_set = set(member_ids)
    rows = tuple(rows_by_id[listing_id] for listing_id in member_ids)
    _validate_membership_rows(market_export, binding)
    return AnalystComparableSetFeatures(
        set_id=binding.set_id,
        set_version=binding.version,
        query_family_id=binding.query_family_id,
        query_family_version=binding.query_family_version,
        member_listing_ids=member_ids,
        member_count=len(member_ids),
        query_supply=_query_supply(market_export, binding),
        yandex_games_rating=_numeric_distribution(
            rows,
            lambda row: row.yandex_games_rating,
            "yandex_games_rating",
        ),
        player_rating=_numeric_distribution(
            rows,
            lambda row: row.player_rating,
            "player_rating",
        ),
        rating_count=_numeric_distribution(
            rows,
            lambda row: row.rating_count,
            "rating_count",
        ),
        first_published=_release_distribution(rows, snapshot.created_at),
        organic_exposure=_organic_exposure(snapshot, market_export, binding, member_set),
        developer_composition=_developer_composition(rows),
    )


def _validate_membership_rows(
    market_export: AnalystMarketExportReport,
    binding: AnalystComparableSetBinding,
) -> None:
    memberships = tuple(
        item
        for item in market_export.comparable_memberships
        if item.set_id == binding.set_id and item.set_version == binding.version
    )
    if tuple(item.member_ordinal for item in memberships) != tuple(range(len(memberships))):
        raise AnalystFeatureError(f"membership ordinals changed for {binding.set_id}")
    if tuple(item.platform_listing_id for item in memberships) != binding.member_listing_ids:
        raise AnalystFeatureError(f"membership rows changed for {binding.set_id}")
    if any(
        item.query_family_id != binding.query_family_id
        or item.query_family_version != binding.query_family_version
        for item in memberships
    ):
        raise AnalystFeatureError(f"membership query-family identity changed for {binding.set_id}")


def _query_supply(
    market_export: AnalystMarketExportReport,
    binding: AnalystComparableSetBinding,
) -> tuple[AnalystQuerySupplySummary, ...]:
    rows = tuple(
        item
        for item in market_export.search_supply
        if item.set_id == binding.set_id and item.set_version == binding.version
    )
    rows_by_run: dict[str, list[AnalystSearchSupplyObservation]] = {}
    for item in rows:
        rows_by_run.setdefault(item.probe_run_id, []).append(item)
    if set(rows_by_run) != set(binding.search_run_ids):
        raise AnalystFeatureError(f"query-supply runs changed for {binding.set_id}")
    summaries: list[AnalystQuerySupplySummary] = []
    for run_id in binding.search_run_ids:
        typed_rows = sorted(rows_by_run[run_id], key=lambda item: item.page_index)
        query_texts = {item.query_text for item in typed_rows}
        if len(query_texts) != 1:
            raise AnalystFeatureError(f"query text changed inside search run {run_id}")
        pages = tuple(
            AnalystQuerySupplyPage(
                page_index=item.page_index,
                raw_snapshot_id=item.raw_snapshot_id,
                source_field_path=item.source_field_path,
                total_games_count=item.total_games_count,
                missing_reason=item.missing_reason,
            )
            for item in typed_rows
        )
        observed = tuple(
            item.total_games_count
            for item in pages
            if item.total_games_count is not None
        )
        distinct = tuple(sorted(set(observed)))
        summaries.append(
            AnalystQuerySupplySummary(
                query_text=next(iter(query_texts)),
                probe_run_id=run_id,
                pages=pages,
                observed_values=observed,
                distinct_observed_values=distinct,
                consistent_across_observed_pages=(None if not observed else len(distinct) == 1),
            )
        )
    return tuple(summaries)


def _numeric_distribution(
    rows: Sequence[AnalystListingRow],
    selector: Callable[[AnalystListingRow], AnalystResolvedValue],
    field_name: str,
) -> AnalystNumericDistribution:
    values: list[float] = []
    for row in rows:
        value = selector(row).value
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise AnalystFeatureError(
                f"{field_name} for {row.platform_listing_id} is not numeric"
            )
        number = float(value)
        if not math.isfinite(number):
            raise AnalystFeatureError(
                f"{field_name} for {row.platform_listing_id} is not finite"
            )
        values.append(number)
    return _distribution_from_values(len(rows), values)


def _distribution_from_values(
    total_count: int,
    values: Sequence[float],
) -> AnalystNumericDistribution:
    coverage = _coverage(total_count, len(values))
    if not values:
        return AnalystNumericDistribution(coverage=coverage)
    ordered = sorted(values)
    return AnalystNumericDistribution(
        coverage=coverage,
        minimum=ordered[0],
        p25=_percentile(ordered, 0.25),
        median=_percentile(ordered, 0.50),
        p75=_percentile(ordered, 0.75),
        maximum=ordered[-1],
        mean=math.fsum(ordered) / len(ordered),
    )


def _percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        raise AnalystFeatureError("cannot calculate percentile of empty values")
    index = (len(values) - 1) * fraction
    lower_index = math.floor(index)
    upper_index = math.ceil(index)
    lower = values[lower_index]
    upper = values[upper_index]
    if lower_index == upper_index:
        return lower
    return lower + (upper - lower) * (index - lower_index)


def _release_distribution(
    rows: Sequence[AnalystListingRow],
    reference_time: datetime,
) -> AnalystReleaseDistribution:
    reference = _utc(reference_time)
    ages: list[float] = []
    for row in rows:
        value = row.first_published_at.value
        if value is None:
            continue
        if not isinstance(value, str):
            raise AnalystFeatureError(
                f"first_published_at for {row.platform_listing_id} is not a timestamp string"
            )
        published = _parse_timestamp(value)
        age_days = (reference - published).total_seconds() / 86_400
        if age_days < 0:
            raise AnalystFeatureError(
                f"first_published_at for {row.platform_listing_id} is after snapshot time"
            )
        ages.append(age_days)
    distribution = _distribution_from_values(len(rows), ages)
    observed = distribution.coverage.observed_count
    windows = tuple(
        AnalystReleaseWindow(
            max_age_days=days,
            listing_count=sum(age <= days for age in ages),
            share_of_observed=(
                None if observed == 0 else sum(age <= days for age in ages) / observed
            ),
        )
        for days in _RELEASE_WINDOWS_DAYS
    )
    return AnalystReleaseDistribution(age_days=distribution, windows=windows)


def _organic_exposure(
    snapshot: AnalystSnapshotReport,
    market_export: AnalystMarketExportReport,
    binding: AnalystComparableSetBinding,
    member_ids: set[str],
) -> AnalystOrganicExposureSummary:
    set_search_rows = tuple(
        item
        for item in market_export.search_exposures
        if item.set_id == binding.set_id and item.set_version == binding.version
    )
    if any(item.probe_run_id not in binding.search_run_ids for item in set_search_rows):
        raise AnalystFeatureError(f"search exposure run escaped {binding.set_id} binding")
    search_rows = tuple(
        item for item in set_search_rows if item.exposure_kind == "organic_search"
    )
    if any(item.platform_listing_id not in member_ids for item in search_rows):
        raise AnalystFeatureError(f"organic search exposure escaped {binding.set_id} membership")
    search_exposed = {item.platform_listing_id for item in search_rows}
    if search_exposed != member_ids:
        raise AnalystFeatureError(f"organic search evidence no longer covers {binding.set_id}")
    search = _exposure_summary(
        member_count=len(member_ids),
        evidence_available=True,
        run_count=len(binding.search_run_ids),
        exposure_count=len(search_rows),
        exposed_member_count=len(search_exposed),
    )

    feed_available = bool(snapshot.feed_runs)
    feed_run_ids = {item.run_id for item in snapshot.feed_runs}
    if any(item.probe_run_id not in feed_run_ids for item in market_export.feed_exposures):
        raise AnalystFeatureError("market export contains feed exposure outside snapshot feed runs")
    feed_rows = tuple(
        item
        for item in market_export.feed_exposures
        if item.exposure_kind == "organic_feed" and item.platform_listing_id in member_ids
    )
    feed_exposed = {item.platform_listing_id for item in feed_rows}
    feed = _exposure_summary(
        member_count=len(member_ids),
        evidence_available=feed_available,
        run_count=len(snapshot.feed_runs),
        exposure_count=len(feed_rows),
        exposed_member_count=len(feed_exposed),
    )
    return AnalystOrganicExposureSummary(search=search, feed=feed)


def _exposure_summary(
    *,
    member_count: int,
    evidence_available: bool,
    run_count: int,
    exposure_count: int,
    exposed_member_count: int,
) -> AnalystExposureSurfaceSummary:
    if not evidence_available:
        return AnalystExposureSurfaceSummary(
            evidence_available=False,
            member_count=member_count,
            run_count=0,
            exposure_count=0,
            exposed_member_count=0,
            unexposed_member_count=member_count,
            member_coverage_ratio=None,
        )
    return AnalystExposureSurfaceSummary(
        evidence_available=True,
        member_count=member_count,
        run_count=run_count,
        exposure_count=exposure_count,
        exposed_member_count=exposed_member_count,
        unexposed_member_count=member_count - exposed_member_count,
        member_coverage_ratio=exposed_member_count / member_count,
    )


def _developer_composition(
    rows: Sequence[AnalystListingRow],
) -> AnalystDeveloperComposition:
    groups: dict[str, list[AnalystListingRow]] = {}
    for row in rows:
        value = row.developer_id.value
        if value is None:
            continue
        if not isinstance(value, str):
            raise AnalystFeatureError(
                f"developer_id for {row.platform_listing_id} is not a string"
            )
        groups.setdefault(value, []).append(row)
    coverage = _coverage(len(rows), sum(len(group) for group in groups.values()))
    observed = coverage.observed_count
    if observed == 0:
        return AnalystDeveloperComposition(
            coverage=coverage,
            distinct_developer_count=0,
            largest_developer_listing_count=0,
            largest_developer_share=None,
            developers=(),
        )
    entries: list[AnalystDeveloperCompositionEntry] = []
    for developer_id, group in groups.items():
        names: set[str] = set()
        for row in group:
            name = row.developer_name.value
            if name is None:
                continue
            if not isinstance(name, str):
                raise AnalystFeatureError(
                    f"developer_name for {row.platform_listing_id} is not a string"
                )
            names.add(name)
        entries.append(
            AnalystDeveloperCompositionEntry(
                developer_id=developer_id,
                developer_names=tuple(sorted(names)),
                listing_count=len(group),
                share_of_observed=len(group) / observed,
            )
        )
    entries.sort(key=lambda item: (-item.listing_count, item.developer_id))
    largest = entries[0].listing_count
    return AnalystDeveloperComposition(
        coverage=coverage,
        distinct_developer_count=len(entries),
        largest_developer_listing_count=largest,
        largest_developer_share=largest / observed,
        developers=tuple(entries),
    )


def _coverage(total_count: int, observed_count: int) -> AnalystCoverage:
    return AnalystCoverage(
        total_count=total_count,
        observed_count=observed_count,
        missing_count=total_count - observed_count,
        coverage_ratio=observed_count / total_count,
    )


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AnalystFeatureError(f"invalid exported timestamp: {value}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AnalystFeatureError("exported timestamp must be timezone-aware")
    return parsed.astimezone(UTC)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise AnalystFeatureError("feature reference time must be timezone-aware")
    return value.astimezone(UTC)


def _required_float(value: float | None) -> float:
    if value is None:
        raise ValueError("required distribution value is missing")
    return value


def _payload_hash(payload: AnalystMarketFeaturesPayload) -> str:
    encoded = json.dumps(
        payload.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
