from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from yandex_analytics_reaper.domain import GameMetricName, ProbeKind, ProbeRunStatus
from yandex_analytics_reaper.evidence import FieldLineage
from yandex_analytics_reaper.sources.yandex.parsers import YandexFeedParser
from yandex_analytics_reaper.storage import (
    FilesystemRawSnapshotStore,
    PersistedListingState,
    PersistedMetricObservation,
    SQLiteComparableSetStore,
    SQLiteLineageStore,
    SQLiteListingHistoryStore,
    SQLiteListingStateStore,
    SQLiteMetricStore,
    SQLiteProbeRunStore,
)

from .snapshot import AnalystSnapshotReport, validate_analyst_snapshot_report

ANALYST_MARKET_EXPORT_SPEC_VERSION: Literal["analyst-market-export-v1"] = (
    "analyst-market-export-v1"
)
_MISSING_NOT_OBSERVED: Literal["not_observed"] = "not_observed"
_YANDEX_LISTING_PREFIX = "yandex_games:"


class AnalystExportError(ValueError):
    """A frozen snapshot cannot be exported without weakening its evidence boundary."""


class AnalystEvidenceReference(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    observation_id: str
    observed_at: str
    retrieved_at: str
    raw_snapshot_ids: tuple[str, ...] = Field(min_length=1)
    source_field_paths: tuple[str, ...] = Field(min_length=1)
    normalizer_name: str
    normalizer_version: str


class AnalystResolvedValue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    value: str | int | float | bool | tuple[str, ...] | None = None
    missing_reason: Literal["not_observed"] | None = None
    evidence: AnalystEvidenceReference | None = None

    @model_validator(mode="after")
    def validate_resolution(self) -> Self:
        if self.value is None:
            if self.missing_reason != _MISSING_NOT_OBSERVED or self.evidence is not None:
                raise ValueError("missing resolved value requires not_observed and no evidence")
        elif self.missing_reason is not None or self.evidence is None:
            raise ValueError("observed resolved value requires evidence and no missing reason")
        return self


class AnalystListingRow(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    platform_listing_id: str
    platform: Literal["yandex_games"]
    external_app_id: str
    canonical_url: str
    comparable_set_ids: tuple[str, ...] = Field(min_length=1)
    title: AnalystResolvedValue
    developer_id: AnalystResolvedValue
    developer_name: AnalystResolvedValue
    app_version: AnalystResolvedValue
    published_at: AnalystResolvedValue
    languages: AnalystResolvedValue
    supported_platforms: AnalystResolvedValue
    orientation: AnalystResolvedValue
    cloud_save: AnalystResolvedValue
    leaderboards: AnalystResolvedValue
    purchases_enabled: AnalystResolvedValue
    has_products: AnalystResolvedValue
    rewarded_ads: AnalystResolvedValue
    fullscreen_ads: AnalystResolvedValue
    sticky_ads: AnalystResolvedValue
    yandex_games_rating: AnalystResolvedValue
    player_rating: AnalystResolvedValue
    rating_count: AnalystResolvedValue


class AnalystUpdateObservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    platform_listing_id: str
    observation_id: str
    observed_at: str
    app_version: str | None
    source_published_at: str | None
    raw_snapshot_ids: tuple[str, ...] = Field(min_length=1)
    source_field_paths: tuple[str, ...] = Field(min_length=1)


class AnalystSearchSupplyObservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    set_id: str
    set_version: int = Field(ge=1)
    query_text: str
    probe_run_id: str
    page_index: int = Field(ge=0)
    raw_snapshot_id: str
    total_games_count: int | None


class AnalystSearchExposure(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    set_id: str
    set_version: int = Field(ge=1)
    platform_listing_id: str
    query_text: str
    probe_run_id: str
    page_index: int = Field(ge=0)
    raw_snapshot_id: str
    source_object_path: str
    exposure_kind: Literal["organic_search"] = "organic_search"


class AnalystFeedExposure(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    platform_listing_id: str
    probe_run_id: str
    page_index: int = Field(ge=0)
    raw_snapshot_id: str
    source_object_path: str | None
    exposure_kind: Literal["organic_feed", "sponsored_feed"]
    row: int | None
    column: int | None


class AnalystComparableMembership(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    set_id: str
    set_version: int = Field(ge=1)
    member_ordinal: int = Field(ge=0)
    platform_listing_id: str
    query_family_id: str
    query_family_version: int = Field(ge=1)


class AnalystMarketExportPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: Literal["analyst-market-export-v1"]
    snapshot_id: str
    snapshot_content_hash: str
    collection_parameters_status: Literal["provisional_uncalibrated"]
    effective_context: dict[str, object]
    search_page_limit: int = Field(ge=1)
    rich_metadata_raw_snapshot_ids: tuple[str, ...] = Field(min_length=1)
    listings: tuple[AnalystListingRow, ...] = Field(min_length=1)
    comparable_memberships: tuple[AnalystComparableMembership, ...] = Field(min_length=1)
    update_observations: tuple[AnalystUpdateObservation, ...]
    search_supply: tuple[AnalystSearchSupplyObservation, ...]
    search_exposures: tuple[AnalystSearchExposure, ...] = Field(min_length=1)
    feed_exposures: tuple[AnalystFeedExposure, ...]


class AnalystMarketExportReport(AnalystMarketExportPayload):
    content_hash: str

    @field_validator("snapshot_content_hash", "content_hash")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise ValueError("export hashes must be lowercase SHA-256 hex digests")
        return value


class AnalystMarketExporter:
    """Build deterministic analyst-readable rows from one validated frozen snapshot."""

    def __init__(self, *, raw_store: FilesystemRawSnapshotStore, database_path: Path) -> None:
        self.raw_store = raw_store
        self.database_path = database_path
        self.state_store = SQLiteListingStateStore(database_path)
        self.metric_store = SQLiteMetricStore(database_path)
        self.history_store = SQLiteListingHistoryStore(database_path)
        self.lineage_store = SQLiteLineageStore(database_path)
        self.comparable_store = SQLiteComparableSetStore(database_path)
        self.probe_store = SQLiteProbeRunStore(database_path)

    def build(self, snapshot: AnalystSnapshotReport) -> AnalystMarketExportReport:
        snapshot = validate_analyst_snapshot_report(snapshot)
        rich_raw_ids = tuple(item.raw_snapshot_id for item in snapshot.rich_metadata)
        rich_raw_set = set(rich_raw_ids)
        for binding in snapshot.rich_metadata:
            metadata = self.raw_store.get_metadata(binding.source_id, binding.raw_snapshot_id)
            self.raw_store.get_body(binding.source_id, binding.raw_snapshot_id)
            if metadata.content_hash != binding.content_hash:
                raise AnalystExportError(
                    f"rich snapshot {binding.raw_snapshot_id} content hash changed"
                )

        listing_order, set_memberships = self._listing_order_and_memberships(snapshot)
        states = self.state_store.states_for_raw_snapshots(
            rich_raw_ids,
            listing_ids=listing_order,
        )
        states_by_listing = _group_states(states)
        listings = tuple(
            self._listing_row(
                listing_id,
                set_memberships[listing_id],
                states_by_listing.get(listing_id, ()),
                rich_raw_set,
            )
            for listing_id in listing_order
        )
        comparable_memberships, search_exposures, search_supply = self._search_rows(snapshot)
        update_observations = self._update_rows(listing_order, rich_raw_set)
        feed_exposures = self._feed_rows(snapshot)

        payload = AnalystMarketExportPayload(
            spec_version=ANALYST_MARKET_EXPORT_SPEC_VERSION,
            snapshot_id=snapshot.snapshot_id,
            snapshot_content_hash=snapshot.content_hash,
            collection_parameters_status=snapshot.collection_parameters_status,
            effective_context=snapshot.effective_context.model_dump(mode="json"),
            search_page_limit=snapshot.search_page_limit,
            rich_metadata_raw_snapshot_ids=rich_raw_ids,
            listings=listings,
            comparable_memberships=comparable_memberships,
            update_observations=update_observations,
            search_supply=search_supply,
            search_exposures=search_exposures,
            feed_exposures=feed_exposures,
        )
        return AnalystMarketExportReport.model_validate(
            {**payload.model_dump(mode="python"), "content_hash": _payload_hash(payload)}
        )

    def _listing_order_and_memberships(
        self,
        snapshot: AnalystSnapshotReport,
    ) -> tuple[tuple[str, ...], dict[str, tuple[str, ...]]]:
        listing_order: list[str] = []
        memberships: dict[str, list[str]] = {}
        for binding in snapshot.comparable_sets:
            for listing_id in binding.member_listing_ids:
                if listing_id not in memberships:
                    listing_order.append(listing_id)
                    memberships[listing_id] = []
                memberships[listing_id].append(binding.set_id)
        if not listing_order:
            raise AnalystExportError("snapshot contains no comparable members")
        return tuple(listing_order), {
            listing_id: tuple(set_ids) for listing_id, set_ids in memberships.items()
        }

    def _listing_row(
        self,
        listing_id: str,
        set_ids: tuple[str, ...],
        states: tuple[PersistedListingState, ...],
        rich_raw_ids: set[str],
    ) -> AnalystListingRow:
        external_app_id = _external_app_id(listing_id)
        state_fields = {
            field: _resolve_state_value(states, field, rich_raw_ids)
            for field in (
                "title",
                "developer_id",
                "developer_name",
                "app_version",
                "published_at",
                "languages",
                "supported_platforms",
                "orientation",
                "cloud_save",
                "leaderboards",
                "purchases_enabled",
                "has_products",
                "rewarded_ads",
                "fullscreen_ads",
                "sticky_ads",
            )
        }
        metrics = {
            metric_name: self._resolve_metric(listing_id, metric_name, rich_raw_ids)
            for metric_name in (
                GameMetricName.YANDEX_GAMES_RATING,
                GameMetricName.PLAYER_RATING,
                GameMetricName.RATING_COUNT,
            )
        }
        return AnalystListingRow(
            platform_listing_id=listing_id,
            platform="yandex_games",
            external_app_id=external_app_id,
            canonical_url=f"https://yandex.ru/games/app/{external_app_id}",
            comparable_set_ids=set_ids,
            title=state_fields["title"],
            developer_id=state_fields["developer_id"],
            developer_name=state_fields["developer_name"],
            app_version=state_fields["app_version"],
            published_at=state_fields["published_at"],
            languages=state_fields["languages"],
            supported_platforms=state_fields["supported_platforms"],
            orientation=state_fields["orientation"],
            cloud_save=state_fields["cloud_save"],
            leaderboards=state_fields["leaderboards"],
            purchases_enabled=state_fields["purchases_enabled"],
            has_products=state_fields["has_products"],
            rewarded_ads=state_fields["rewarded_ads"],
            fullscreen_ads=state_fields["fullscreen_ads"],
            sticky_ads=state_fields["sticky_ads"],
            yandex_games_rating=metrics[GameMetricName.YANDEX_GAMES_RATING],
            player_rating=metrics[GameMetricName.PLAYER_RATING],
            rating_count=metrics[GameMetricName.RATING_COUNT],
        )

    def _resolve_metric(
        self,
        listing_id: str,
        metric_name: GameMetricName,
        rich_raw_ids: set[str],
    ) -> AnalystResolvedValue:
        scoped: list[tuple[PersistedMetricObservation, tuple[FieldLineage, ...]]] = []
        for observation in self.metric_store.metric_history(listing_id, metric_name):
            lineage = self.lineage_store.for_observation(observation.observation_id)
            relevant = tuple(item for item in lineage if item.raw_snapshot_id in rich_raw_ids)
            if relevant:
                scoped.append((observation, relevant))
        if not scoped:
            return _missing()
        observation, lineage = scoped[-1]
        return AnalystResolvedValue(
            value=observation.metric.value,
            evidence=_evidence_reference(
                observation.observation_id,
                observation.evidence.observed_at,
                observation.evidence.retrieved_at,
                observation.normalizer_name,
                observation.normalizer_version,
                lineage,
            ),
        )

    def _update_rows(
        self,
        listing_ids: Sequence[str],
        rich_raw_ids: set[str],
    ) -> tuple[AnalystUpdateObservation, ...]:
        rows: list[AnalystUpdateObservation] = []
        for listing_id in listing_ids:
            for update in self.history_store.update_history(listing_id):
                lineage = self.lineage_store.for_observation(update.observation_id)
                relevant = tuple(
                    item for item in lineage if item.raw_snapshot_id in rich_raw_ids
                )
                if not relevant:
                    continue
                rows.append(
                    AnalystUpdateObservation(
                        platform_listing_id=listing_id,
                        observation_id=update.observation_id,
                        observed_at=_iso(update.observation.observed_at),
                        app_version=update.observation.app_version,
                        source_published_at=(
                            None
                            if update.observation.source_published_at is None
                            else _iso(update.observation.source_published_at)
                        ),
                        raw_snapshot_ids=_ordered_unique(
                            item.raw_snapshot_id for item in relevant
                        ),
                        source_field_paths=_ordered_unique(
                            item.source_field_path for item in relevant
                        ),
                    )
                )
        return tuple(rows)

    def _search_rows(
        self,
        snapshot: AnalystSnapshotReport,
    ) -> tuple[
        tuple[AnalystComparableMembership, ...],
        tuple[AnalystSearchExposure, ...],
        tuple[AnalystSearchSupplyObservation, ...],
    ]:
        parser = YandexFeedParser()
        memberships: list[AnalystComparableMembership] = []
        exposures: list[AnalystSearchExposure] = []
        supplies: list[AnalystSearchSupplyObservation] = []
        for binding in snapshot.comparable_sets:
            comparable = self.comparable_store.get(binding.set_id, binding.version)
            if comparable is None:
                raise AnalystExportError(
                    f"comparable set disappeared: {binding.set_id}@{binding.version}"
                )
            if (
                tuple(item.probe_run_id for item in comparable.runs)
                != binding.search_run_ids
                or tuple(item.platform_listing_id for item in comparable.members)
                != binding.member_listing_ids
                or comparable.context_id != binding.context_id
                or comparable.requested_page_limit != binding.requested_page_limit
            ):
                raise AnalystExportError(
                    f"comparable set changed since snapshot: {binding.set_id}@{binding.version}"
                )
            if comparable.parser_version != parser.version:
                raise AnalystExportError(
                    f"current feed parser v{parser.version} cannot replay comparable parser "
                    f"v{comparable.parser_version}"
                )
            query_by_run = {item.probe_run_id: item.query_text for item in comparable.runs}
            for member in comparable.members:
                memberships.append(
                    AnalystComparableMembership(
                        set_id=comparable.set_id,
                        set_version=comparable.version,
                        member_ordinal=member.ordinal,
                        platform_listing_id=member.platform_listing_id,
                        query_family_id=comparable.query_family_id,
                        query_family_version=comparable.query_family_version,
                    )
                )
            for evidence in comparable.evidence:
                exposures.append(
                    AnalystSearchExposure(
                        set_id=comparable.set_id,
                        set_version=comparable.version,
                        platform_listing_id=evidence.platform_listing_id,
                        query_text=query_by_run[evidence.probe_run_id],
                        probe_run_id=evidence.probe_run_id,
                        page_index=evidence.page_index,
                        raw_snapshot_id=evidence.raw_snapshot_id,
                        source_object_path=evidence.source_object_path,
                    )
                )
            for run in comparable.runs:
                record = self.probe_store.get_run(run.probe_run_id)
                if record is None or record.run.status is not ProbeRunStatus.COMPLETED:
                    raise AnalystExportError(f"search run unavailable: {run.probe_run_id}")
                for page in record.pages:
                    body = self.raw_store.get_body(record.run.source_id, page.raw_snapshot_id)
                    parsed = parser.parse(body)
                    supplies.append(
                        AnalystSearchSupplyObservation(
                            set_id=comparable.set_id,
                            set_version=comparable.version,
                            query_text=run.query_text,
                            probe_run_id=run.probe_run_id,
                            page_index=page.page_index,
                            raw_snapshot_id=page.raw_snapshot_id,
                            total_games_count=parsed.total_games_count,
                        )
                    )
        return tuple(memberships), tuple(exposures), tuple(supplies)

    def _feed_rows(
        self,
        snapshot: AnalystSnapshotReport,
    ) -> tuple[AnalystFeedExposure, ...]:
        parser = YandexFeedParser()
        rows: list[AnalystFeedExposure] = []
        for binding in snapshot.feed_runs:
            if binding.parser_version != parser.version:
                raise AnalystExportError(
                    f"current feed parser v{parser.version} cannot replay feed parser "
                    f"v{binding.parser_version}"
                )
            record = self.probe_store.get_run(binding.run_id)
            if (
                record is None
                or record.run.kind is not ProbeKind.RECOMMENDATION_FEED
                or record.run.status is not ProbeRunStatus.COMPLETED
                or tuple(page.raw_snapshot_id for page in record.pages)
                != binding.raw_snapshot_ids
            ):
                raise AnalystExportError(f"feed run changed since snapshot: {binding.run_id}")
            for page in record.pages:
                body = self.raw_store.get_body(record.run.source_id, page.raw_snapshot_id)
                parsed = parser.parse(body)
                for game in parsed.games:
                    rows.append(
                        AnalystFeedExposure(
                            platform_listing_id=f"yandex_games:{game.app_id}",
                            probe_run_id=binding.run_id,
                            page_index=page.page_index,
                            raw_snapshot_id=page.raw_snapshot_id,
                            source_object_path=game.source_object_path,
                            exposure_kind=(
                                "sponsored_feed" if game.sponsored else "organic_feed"
                            ),
                            row=game.row,
                            column=game.column,
                        )
                    )
        return tuple(rows)


def validate_analyst_market_export(
    report: AnalystMarketExportReport,
) -> AnalystMarketExportReport:
    validated = AnalystMarketExportReport.model_validate(report.model_dump())
    payload = AnalystMarketExportPayload.model_validate(
        validated.model_dump(exclude={"content_hash"})
    )
    if validated.content_hash != _payload_hash(payload):
        raise AnalystExportError("analyst market export content_hash does not match content")
    return validated


def write_analyst_export_csv(report: AnalystMarketExportReport, directory: Path) -> None:
    report = validate_analyst_market_export(report)
    try:
        directory.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise AnalystExportError(f"CSV export directory already exists: {directory}") from exc
    _write_listings_csv(report, directory / "listings.csv")
    _write_models_csv(report.comparable_memberships, directory / "comparable_memberships.csv")
    _write_models_csv(report.update_observations, directory / "update_observations.csv")
    _write_models_csv(report.search_supply, directory / "search_supply.csv")
    _write_models_csv(report.search_exposures, directory / "search_exposures.csv")
    _write_models_csv(report.feed_exposures, directory / "feed_exposures.csv")


def _resolve_state_value(
    states: Sequence[PersistedListingState],
    field: str,
    rich_raw_ids: set[str],
) -> AnalystResolvedValue:
    target = f"listing_state_observations.{field}"
    for state in reversed(states):
        value = getattr(state.observation, field)
        if value is None:
            continue
        lineage = tuple(
            item
            for item in state.lineage
            if item.target_field_path == target and item.raw_snapshot_id in rich_raw_ids
        )
        if not lineage:
            continue
        if isinstance(value, datetime):
            exported: str | int | float | bool | tuple[str, ...] = _iso(value)
        else:
            exported = value
        return AnalystResolvedValue(
            value=exported,
            evidence=_evidence_reference(
                state.observation_id,
                state.evidence.observed_at,
                state.evidence.retrieved_at,
                state.normalizer_name,
                state.normalizer_version,
                lineage,
            ),
        )
    return _missing()


def _evidence_reference(
    observation_id: str,
    observed_at: datetime,
    retrieved_at: datetime | None,
    normalizer_name: str,
    normalizer_version: str,
    lineage: Sequence[FieldLineage],
) -> AnalystEvidenceReference:
    if retrieved_at is None:
        raise AnalystExportError(f"observation {observation_id} has no retrieved_at")
    return AnalystEvidenceReference(
        observation_id=observation_id,
        observed_at=_iso(observed_at),
        retrieved_at=_iso(retrieved_at),
        raw_snapshot_ids=_ordered_unique(item.raw_snapshot_id for item in lineage),
        source_field_paths=_ordered_unique(item.source_field_path for item in lineage),
        normalizer_name=normalizer_name,
        normalizer_version=normalizer_version,
    )


def _missing() -> AnalystResolvedValue:
    return AnalystResolvedValue(value=None, missing_reason=_MISSING_NOT_OBSERVED)


def _group_states(
    states: Sequence[PersistedListingState],
) -> dict[str, tuple[PersistedListingState, ...]]:
    grouped: dict[str, list[PersistedListingState]] = {}
    for state in states:
        grouped.setdefault(state.observation.platform_listing_id, []).append(state)
    return {listing_id: tuple(items) for listing_id, items in grouped.items()}


def _external_app_id(listing_id: str) -> str:
    if not listing_id.startswith(_YANDEX_LISTING_PREFIX):
        raise AnalystExportError(f"unsupported comparable listing identity: {listing_id}")
    external = listing_id.removeprefix(_YANDEX_LISTING_PREFIX)
    if not external:
        raise AnalystExportError("Yandex listing identity has empty external app ID")
    return external


def _ordered_unique(values: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    if not result:
        raise AnalystExportError("evidence reference cannot be empty")
    return tuple(result)


def _iso(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise AnalystExportError("export timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _payload_hash(payload: AnalystMarketExportPayload) -> str:
    encoded = json.dumps(
        payload.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_listings_csv(report: AnalystMarketExportReport, path: Path) -> None:
    fieldnames = [
        "platform_listing_id",
        "external_app_id",
        "canonical_url",
        "comparable_set_ids",
        "title",
        "developer_id",
        "developer_name",
        "app_version",
        "published_at",
        "languages",
        "supported_platforms",
        "orientation",
        "cloud_save",
        "leaderboards",
        "purchases_enabled",
        "has_products",
        "rewarded_ads",
        "fullscreen_ads",
        "sticky_ads",
        "yandex_games_rating",
        "player_rating",
        "rating_count",
        "missing_fields",
    ]
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in report.listings:
            resolved_names = fieldnames[4:-1]
            resolved = {name: getattr(row, name) for name in resolved_names}
            writer.writerow(
                {
                    "platform_listing_id": row.platform_listing_id,
                    "external_app_id": row.external_app_id,
                    "canonical_url": row.canonical_url,
                    "comparable_set_ids": "|".join(row.comparable_set_ids),
                    **{name: _csv_value(item.value) for name, item in resolved.items()},
                    "missing_fields": "|".join(
                        name for name, item in resolved.items() if item.value is None
                    ),
                }
            )


def _write_models_csv(rows: Sequence[BaseModel], path: Path) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].model_dump(mode="json").keys())
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: _csv_value(value)
                    for key, value in row.model_dump(mode="json").items()
                }
            )


def _csv_value(value: object) -> object:
    if isinstance(value, (list, tuple, dict)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return value
