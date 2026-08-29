from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import BaseModel

from yandex_analytics_reaper.analyst import (
    AnalystComparableMembership,
    AnalystComparableSetBinding,
    AnalystEvidenceReference,
    AnalystFeedExposure,
    AnalystFeedRunBinding,
    AnalystListingRow,
    AnalystMarketExportPayload,
    AnalystMarketExportReport,
    AnalystResolvedValue,
    AnalystRichMetadataBinding,
    AnalystSearchExposure,
    AnalystSearchSupplyObservation,
    AnalystSnapshotPayload,
    AnalystSnapshotReport,
)
from yandex_analytics_reaper.analyst.features import (
    AnalystFeatureError,
    AnalystMarketFeatureBuilder,
    validate_analyst_market_features,
)
from yandex_analytics_reaper.domain import ProbeContext

_BASE = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
_CONTEXT_ID = "ctx:test"
_MEMBER_IDS = tuple(f"yandex_games:{value}" for value in range(1, 5))


def _hash_model(model: BaseModel) -> str:
    encoded = json.dumps(
        model.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _snapshot(*, with_feed: bool = True, created_at: datetime = _BASE) -> AnalystSnapshotReport:
    context = ProbeContext(profile_age_days=0)
    comparable = AnalystComparableSetBinding(
        set_id="merge-search",
        version=1,
        query_family_id="merge-family",
        query_family_version=1,
        construction_method="yandex_search_union_v1",
        context_id=_CONTEXT_ID,
        requested_page_limit=2,
        observed_from=created_at - timedelta(minutes=10),
        observed_to=created_at - timedelta(minutes=5),
        search_run_ids=("probe:search",),
        member_listing_ids=_MEMBER_IDS,
    )
    feed_runs = (
        (
            AnalystFeedRunBinding(
                run_id="probe:feed",
                context_id=_CONTEXT_ID,
                requested_page_limit=1,
                started_at=created_at - timedelta(minutes=4),
                completed_at=created_at - timedelta(minutes=3),
                raw_snapshot_ids=("raw:feed",),
                parser_name="YandexFeedParser",
                parser_version="2",
            ),
        )
        if with_feed
        else ()
    )
    rich = AnalystRichMetadataBinding(
        source_id="yandex_public",
        request_key="catalogue.get_games",
        raw_snapshot_id="raw:rich",
        retrieved_at=created_at - timedelta(minutes=2),
        content_hash="a" * 64,
        parser_name="YandexGetGamesParser",
        parser_version="2",
        parsed_listing_ids=_MEMBER_IDS,
        relevant_listing_ids=_MEMBER_IDS,
    )
    payload = AnalystSnapshotPayload(
        spec_version="analyst-snapshot-v1",
        snapshot_id="pilot:merge:v1",
        created_at=created_at,
        collection_parameters_status="provisional_uncalibrated",
        effective_context=context,
        search_page_limit=2,
        comparable_sets=(comparable,),
        feed_runs=feed_runs,
        rich_metadata=(rich,),
    )
    return AnalystSnapshotReport.model_validate(
        {**payload.model_dump(mode="python"), "content_hash": _hash_model(payload)}
    )


def _evidence(field: str, listing_id: str) -> AnalystEvidenceReference:
    suffix = listing_id.rsplit(":", 1)[-1]
    observed_at = (_BASE - timedelta(minutes=2)).isoformat().replace("+00:00", "Z")
    return AnalystEvidenceReference(
        observation_id=f"state:{suffix}",
        observed_at=observed_at,
        retrieved_at=observed_at,
        raw_snapshot_ids=("raw:rich",),
        source_field_paths=(f"$.games[{suffix}].{field}",),
        normalizer_name="YandexGameNormalizer",
        normalizer_version="4",
    )


def _observed(value: object, field: str, listing_id: str) -> AnalystResolvedValue:
    return AnalystResolvedValue(value=value, evidence=_evidence(field, listing_id))


def _missing() -> AnalystResolvedValue:
    return AnalystResolvedValue(missing_reason="not_observed")


def _listing(
    listing_id: str,
    *,
    gq: int | None,
    player: float | None,
    rating_count: int | None,
    published_days_ago: int | None,
    developer_id: str | None,
    developer_name: str | None,
) -> AnalystListingRow:
    external = listing_id.rsplit(":", 1)[-1]
    first_published = (
        _missing()
        if published_days_ago is None
        else _observed(
            (_BASE - timedelta(days=published_days_ago))
            .isoformat()
            .replace("+00:00", "Z"),
            "firstPublished",
            listing_id,
        )
    )
    return AnalystListingRow(
        platform_listing_id=listing_id,
        platform="yandex_games",
        external_app_id=external,
        canonical_url=f"https://yandex.ru/games/app/{external}",
        comparable_set_ids=("merge-search",),
        title=_observed(f"Game {external}", "title", listing_id),
        developer_id=(
            _missing()
            if developer_id is None
            else _observed(developer_id, "developer.id", listing_id)
        ),
        developer_name=(
            _missing()
            if developer_name is None
            else _observed(developer_name, "developer.name", listing_id)
        ),
        first_published_at=first_published,
        app_version=_missing(),
        published_at=_missing(),
        languages=_missing(),
        supported_platforms=_missing(),
        orientation=_missing(),
        cloud_save=_missing(),
        leaderboards=_missing(),
        purchases_enabled=_missing(),
        has_products=_missing(),
        rewarded_ads=_missing(),
        fullscreen_ads=_missing(),
        sticky_ads=_missing(),
        yandex_games_rating=(
            _missing() if gq is None else _observed(gq, "gqRating", listing_id)
        ),
        player_rating=(
            _missing() if player is None else _observed(player, "rating", listing_id)
        ),
        rating_count=(
            _missing()
            if rating_count is None
            else _observed(rating_count, "ratingCount", listing_id)
        ),
    )


def _market_export(
    snapshot: AnalystSnapshotReport,
    *,
    with_feed: bool = True,
) -> AnalystMarketExportReport:
    listings = (
        _listing(
            _MEMBER_IDS[0],
            gq=90,
            player=4.5,
            rating_count=1000,
            published_days_ago=10,
            developer_id="yandex_games:dev-a",
            developer_name="Studio A",
        ),
        _listing(
            _MEMBER_IDS[1],
            gq=80,
            player=4.0,
            rating_count=100,
            published_days_ago=100,
            developer_id="yandex_games:dev-a",
            developer_name="Studio A",
        ),
        _listing(
            _MEMBER_IDS[2],
            gq=70,
            player=None,
            rating_count=10,
            published_days_ago=None,
            developer_id="yandex_games:dev-b",
            developer_name=None,
        ),
        _listing(
            _MEMBER_IDS[3],
            gq=None,
            player=None,
            rating_count=1,
            published_days_ago=400,
            developer_id=None,
            developer_name=None,
        ),
    )
    memberships = tuple(
        AnalystComparableMembership(
            set_id="merge-search",
            set_version=1,
            member_ordinal=index,
            platform_listing_id=listing_id,
            query_family_id="merge-family",
            query_family_version=1,
            source_queries=("merge",),
            probe_run_ids=("probe:search",),
            raw_snapshot_ids=("raw:search-0",),
            source_object_paths=(f"$.feed[0].items[{index}]",),
        )
        for index, listing_id in enumerate(_MEMBER_IDS)
    )
    supply = (
        AnalystSearchSupplyObservation(
            set_id="merge-search",
            set_version=1,
            query_text="merge",
            probe_run_id="probe:search",
            page_index=0,
            raw_snapshot_id="raw:search-0",
            source_field_path="$.totalGamesCount",
            total_games_count=42,
        ),
        AnalystSearchSupplyObservation(
            set_id="merge-search",
            set_version=1,
            query_text="merge",
            probe_run_id="probe:search",
            page_index=1,
            raw_snapshot_id="raw:search-1",
            source_field_path="$.totalGamesCount",
            total_games_count=42,
        ),
    )
    search_exposures = (
        AnalystSearchExposure(
            set_id="merge-search",
            set_version=1,
            platform_listing_id=_MEMBER_IDS[0],
            query_text="merge",
            probe_run_id="probe:search",
            page_index=0,
            raw_snapshot_id="raw:search-0",
            source_object_path="$.feed[0].items[0]",
            exposure_kind="organic_search",
        ),
        AnalystSearchExposure(
            set_id="merge-search",
            set_version=1,
            platform_listing_id=_MEMBER_IDS[0],
            query_text="merge",
            probe_run_id="probe:search",
            page_index=1,
            raw_snapshot_id="raw:search-1",
            source_object_path="$.feed[0].items[0]",
            exposure_kind="organic_search",
        ),
        *tuple(
            AnalystSearchExposure(
                set_id="merge-search",
                set_version=1,
                platform_listing_id=listing_id,
                query_text="merge",
                probe_run_id="probe:search",
                page_index=0,
                raw_snapshot_id="raw:search-0",
                source_object_path=f"$.feed[0].items[{index}]",
                exposure_kind="organic_search",
            )
            for index, listing_id in enumerate(_MEMBER_IDS[1:], start=1)
        ),
        AnalystSearchExposure(
            set_id="merge-search",
            set_version=1,
            platform_listing_id="yandex_games:999",
            query_text="merge",
            probe_run_id="probe:search",
            page_index=0,
            raw_snapshot_id="raw:search-0",
            source_object_path="$.feed[0].items[9]",
            exposure_kind="sponsored_search",
        ),
    )
    feed_exposures = (
        (
            AnalystFeedExposure(
                platform_listing_id=_MEMBER_IDS[0],
                probe_run_id="probe:feed",
                page_index=0,
                raw_snapshot_id="raw:feed",
                source_object_path="$.feed[0].items[0]",
                exposure_kind="organic_feed",
                row=0,
                column=0,
            ),
            AnalystFeedExposure(
                platform_listing_id=_MEMBER_IDS[2],
                probe_run_id="probe:feed",
                page_index=0,
                raw_snapshot_id="raw:feed",
                source_object_path="$.feed[0].items[1]",
                exposure_kind="organic_feed",
                row=0,
                column=1,
            ),
            AnalystFeedExposure(
                platform_listing_id=_MEMBER_IDS[1],
                probe_run_id="probe:feed",
                page_index=0,
                raw_snapshot_id="raw:feed",
                source_object_path="$.feed[0].items[2]",
                exposure_kind="sponsored_feed",
                row=0,
                column=2,
            ),
        )
        if with_feed
        else ()
    )
    payload = AnalystMarketExportPayload(
        spec_version="analyst-market-export-v1",
        snapshot_id=snapshot.snapshot_id,
        snapshot_content_hash=snapshot.content_hash,
        collection_parameters_status=snapshot.collection_parameters_status,
        effective_context=snapshot.effective_context.model_dump(mode="json"),
        search_page_limit=snapshot.search_page_limit,
        rich_metadata_raw_snapshot_ids=tuple(
            item.raw_snapshot_id for item in snapshot.rich_metadata
        ),
        listings=listings,
        comparable_memberships=memberships,
        update_observations=(),
        search_supply=supply,
        search_exposures=search_exposures,
        feed_exposures=feed_exposures,
    )
    return AnalystMarketExportReport.model_validate(
        {**payload.model_dump(mode="python"), "content_hash": _hash_model(payload)}
    )


def test_features_compute_transparent_per_set_aggregates() -> None:
    snapshot = _snapshot()
    market_export = _market_export(snapshot)

    report = AnalystMarketFeatureBuilder().build(snapshot, market_export)

    assert validate_analyst_market_features(report) == report
    assert report.snapshot_content_hash == snapshot.content_hash
    assert report.market_export_content_hash == market_export.content_hash
    features = report.comparable_sets[0]
    assert features.member_count == 4
    assert features.query_supply[0].observed_values == (42, 42)
    assert features.query_supply[0].consistent_across_observed_pages is True

    gq = features.yandex_games_rating
    assert gq.coverage.observed_count == 3
    assert gq.coverage.missing_count == 1
    assert gq.coverage.coverage_ratio == pytest.approx(0.75)
    assert gq.minimum == 70
    assert gq.p25 == 75
    assert gq.median == 80
    assert gq.p75 == 85
    assert gq.maximum == 90
    assert gq.mean == 80

    player = features.player_rating
    assert player.coverage.coverage_ratio == pytest.approx(0.5)
    assert player.median == pytest.approx(4.25)

    release = features.first_published
    assert release.age_days.coverage.observed_count == 3
    assert [item.listing_count for item in release.windows] == [1, 1, 2, 2]

    exposure = features.organic_exposure
    assert exposure.search.exposure_count == 5
    assert exposure.search.exposed_member_count == 4
    assert exposure.search.member_coverage_ratio == pytest.approx(1.0)
    assert exposure.feed.evidence_available is True
    assert exposure.feed.exposure_count == 2
    assert exposure.feed.exposed_member_count == 2
    assert exposure.feed.member_coverage_ratio == pytest.approx(0.5)

    developers = features.developer_composition
    assert developers.coverage.observed_count == 3
    assert developers.distinct_developer_count == 2
    assert developers.largest_developer_listing_count == 2
    assert developers.largest_developer_share == pytest.approx(2 / 3)
    assert developers.developers[0].developer_id == "yandex_games:dev-a"
    assert developers.developers[0].developer_names == ("Studio A",)


def test_features_distinguish_uncollected_feed_from_zero_exposure() -> None:
    snapshot = _snapshot(with_feed=False)
    market_export = _market_export(snapshot, with_feed=False)

    report = AnalystMarketFeatureBuilder().build(snapshot, market_export)

    feed = report.comparable_sets[0].organic_exposure.feed
    assert feed.evidence_available is False
    assert feed.run_count == 0
    assert feed.exposure_count == 0
    assert feed.member_coverage_ratio is None


def test_feature_builder_rejects_market_export_from_another_snapshot() -> None:
    snapshot = _snapshot()
    market_export = _market_export(snapshot)
    other_snapshot = _snapshot(created_at=_BASE + timedelta(hours=1))

    with pytest.raises(AnalystFeatureError, match="content hash"):
        AnalystMarketFeatureBuilder().build(other_snapshot, market_export)


def test_feature_report_hash_detects_tampering() -> None:
    snapshot = _snapshot()
    report = AnalystMarketFeatureBuilder().build(snapshot, _market_export(snapshot))

    tampered = report.model_copy(update={"snapshot_id": "tampered"})
    with pytest.raises(AnalystFeatureError, match="content_hash"):
        validate_analyst_market_features(tampered)
