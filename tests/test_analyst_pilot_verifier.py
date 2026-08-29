from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

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
    AnalystMarketFeatureBuilder,
    AnalystMarketFeaturesReport,
    AnalystResolvedValue,
    AnalystRichMetadataBinding,
    AnalystSearchExposure,
    AnalystSearchSupplyObservation,
    AnalystSnapshotPayload,
    AnalystSnapshotReport,
)
from yandex_analytics_reaper.analyst.pilot import (
    AnalystPilotError,
    AnalystPilotVerifier,
    validate_analyst_pilot_verification,
)
from yandex_analytics_reaper.domain import ProbeContext
from yandex_analytics_reaper.sources.capabilities import CollectedResponse
from yandex_analytics_reaper.storage import FilesystemRawSnapshotStore

_BASE = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
_CONTEXT_ID = "ctx:pilot"


def _hash_model(model: BaseModel) -> str:
    encoded = json.dumps(
        model.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _persist_raw(
    store: FilesystemRawSnapshotStore,
    *,
    request_key: str,
    body: bytes,
    retrieved_at: datetime,
) -> tuple[str, str]:
    metadata = store.persist(
        CollectedResponse(
            source_id="yandex_public",
            request_key=request_key,
            method="GET",
            url=f"https://example.test/{request_key}",
            status_code=200,
            headers={"content-type": "application/json"},
            body=body,
            retrieved_at=retrieved_at,
            request_context={},
        )
    )
    return metadata.id, metadata.content_hash


def _evidence(raw_id: str, listing_id: str, field: str) -> AnalystEvidenceReference:
    instant = (_BASE - timedelta(minutes=2)).isoformat().replace("+00:00", "Z")
    return AnalystEvidenceReference(
        observation_id=f"state:{listing_id.rsplit(':', 1)[-1]}:{field}",
        observed_at=instant,
        retrieved_at=instant,
        raw_snapshot_ids=(raw_id,),
        source_field_paths=(f"$.games[0].{field}",),
        normalizer_name="YandexGameNormalizer",
        normalizer_version="4",
    )


def _observed(
    raw_id: str,
    listing_id: str,
    field: str,
    value: str | int | float,
) -> AnalystResolvedValue:
    return AnalystResolvedValue(
        value=value,
        evidence=_evidence(raw_id, listing_id, field),
    )


def _missing() -> AnalystResolvedValue:
    return AnalystResolvedValue(missing_reason="not_observed")


def _listing(
    raw_id: str,
    listing_id: str,
    set_id: str,
    *,
    gq_rating: int,
    player_rating: float,
    rating_count: int,
    published_days_ago: int,
    developer_id: str,
) -> AnalystListingRow:
    external_id = listing_id.rsplit(":", 1)[-1]
    missing = _missing()
    return AnalystListingRow(
        platform_listing_id=listing_id,
        platform="yandex_games",
        external_app_id=external_id,
        canonical_url=f"https://yandex.ru/games/app/{external_id}",
        comparable_set_ids=(set_id,),
        title=_observed(raw_id, listing_id, "title", f"Game {external_id}"),
        developer_id=_observed(raw_id, listing_id, "developer.id", developer_id),
        developer_name=_observed(raw_id, listing_id, "developer.name", developer_id),
        first_published_at=_observed(
            raw_id,
            listing_id,
            "firstPublished",
            (_BASE - timedelta(days=published_days_ago)).isoformat().replace("+00:00", "Z"),
        ),
        app_version=missing,
        published_at=missing,
        languages=missing,
        supported_platforms=missing,
        orientation=missing,
        cloud_save=missing,
        leaderboards=missing,
        purchases_enabled=missing,
        has_products=missing,
        rewarded_ads=missing,
        fullscreen_ads=missing,
        sticky_ads=missing,
        yandex_games_rating=_observed(raw_id, listing_id, "gqRating", gq_rating),
        player_rating=_observed(raw_id, listing_id, "rating", player_rating),
        rating_count=_observed(raw_id, listing_id, "ratingCount", rating_count),
    )


def _pilot_artifacts(
    root: Path,
    *,
    same_query_family: bool = False,
) -> tuple[
    FilesystemRawSnapshotStore,
    AnalystSnapshotReport,
    AnalystMarketExportReport,
    AnalystMarketFeaturesReport,
]:
    store = FilesystemRawSnapshotStore(root)
    search_one_id, _ = _persist_raw(
        store,
        request_key="catalogue.search",
        body=b'{"totalGamesCount": 20}',
        retrieved_at=_BASE - timedelta(minutes=10),
    )
    search_two_id, _ = _persist_raw(
        store,
        request_key="catalogue.search",
        body=b'{"totalGamesCount": 30}',
        retrieved_at=_BASE - timedelta(minutes=9),
    )
    feed_id, _ = _persist_raw(
        store,
        request_key="catalogue.feed",
        body=b'{"feed": []}',
        retrieved_at=_BASE - timedelta(minutes=8),
    )
    rich_id, rich_hash = _persist_raw(
        store,
        request_key="catalogue.get_games",
        body=b'{"games": [{"appID": 1}, {"appID": 2}]}',
        retrieved_at=_BASE - timedelta(minutes=2),
    )

    context = ProbeContext(profile_age_days=0)
    second_family = "merge-family" if same_query_family else "obby-family"
    comparable_sets = (
        AnalystComparableSetBinding(
            set_id="merge-search",
            version=1,
            query_family_id="merge-family",
            query_family_version=1,
            construction_method="yandex_search_union_v1",
            context_id=_CONTEXT_ID,
            requested_page_limit=1,
            observed_from=_BASE - timedelta(minutes=10),
            observed_to=_BASE - timedelta(minutes=10),
            search_run_ids=("probe:merge",),
            member_listing_ids=("yandex_games:1",),
        ),
        AnalystComparableSetBinding(
            set_id="obby-search",
            version=1,
            query_family_id=second_family,
            query_family_version=1,
            construction_method="yandex_search_union_v1",
            context_id=_CONTEXT_ID,
            requested_page_limit=1,
            observed_from=_BASE - timedelta(minutes=9),
            observed_to=_BASE - timedelta(minutes=9),
            search_run_ids=("probe:obby",),
            member_listing_ids=("yandex_games:2",),
        ),
    )
    feed_runs = (
        AnalystFeedRunBinding(
            run_id="probe:feed",
            context_id=_CONTEXT_ID,
            requested_page_limit=1,
            started_at=_BASE - timedelta(minutes=8),
            completed_at=_BASE - timedelta(minutes=7),
            raw_snapshot_ids=(feed_id,),
            parser_name="YandexFeedParser",
            parser_version="2",
        ),
    )
    rich = (
        AnalystRichMetadataBinding(
            source_id="yandex_public",
            request_key="catalogue.get_games",
            raw_snapshot_id=rich_id,
            retrieved_at=_BASE - timedelta(minutes=2),
            content_hash=rich_hash,
            parser_name="YandexGetGamesParser",
            parser_version="4",
            parsed_listing_ids=("yandex_games:1", "yandex_games:2"),
            relevant_listing_ids=("yandex_games:1", "yandex_games:2"),
        ),
    )
    snapshot_payload = AnalystSnapshotPayload(
        spec_version="analyst-snapshot-v1",
        snapshot_id="pilot:real-readiness:v1",
        created_at=_BASE,
        collection_parameters_status="provisional_uncalibrated",
        effective_context=context,
        search_page_limit=1,
        comparable_sets=comparable_sets,
        feed_runs=feed_runs,
        rich_metadata=rich,
    )
    snapshot = AnalystSnapshotReport.model_validate(
        {
            **snapshot_payload.model_dump(mode="python"),
            "content_hash": _hash_model(snapshot_payload),
        }
    )

    listings = (
        _listing(
            rich_id,
            "yandex_games:1",
            "merge-search",
            gq_rating=80,
            player_rating=4.2,
            rating_count=100,
            published_days_ago=90,
            developer_id="dev:a",
        ),
        _listing(
            rich_id,
            "yandex_games:2",
            "obby-search",
            gq_rating=70,
            player_rating=4.0,
            rating_count=50,
            published_days_ago=180,
            developer_id="dev:b",
        ),
    )
    memberships = (
        AnalystComparableMembership(
            set_id="merge-search",
            set_version=1,
            member_ordinal=0,
            platform_listing_id="yandex_games:1",
            query_family_id="merge-family",
            query_family_version=1,
            source_queries=("merge",),
            probe_run_ids=("probe:merge",),
            raw_snapshot_ids=(search_one_id,),
            source_object_paths=("$.feed[0].items[0]",),
        ),
        AnalystComparableMembership(
            set_id="obby-search",
            set_version=1,
            member_ordinal=0,
            platform_listing_id="yandex_games:2",
            query_family_id=second_family,
            query_family_version=1,
            source_queries=("obby",),
            probe_run_ids=("probe:obby",),
            raw_snapshot_ids=(search_two_id,),
            source_object_paths=("$.feed[0].items[0]",),
        ),
    )
    search_supply = (
        AnalystSearchSupplyObservation(
            set_id="merge-search",
            set_version=1,
            query_text="merge",
            probe_run_id="probe:merge",
            page_index=0,
            raw_snapshot_id=search_one_id,
            source_field_path="$.totalGamesCount",
            total_games_count=20,
        ),
        AnalystSearchSupplyObservation(
            set_id="obby-search",
            set_version=1,
            query_text="obby",
            probe_run_id="probe:obby",
            page_index=0,
            raw_snapshot_id=search_two_id,
            source_field_path="$.totalGamesCount",
            total_games_count=30,
        ),
    )
    search_exposures = (
        AnalystSearchExposure(
            set_id="merge-search",
            set_version=1,
            platform_listing_id="yandex_games:1",
            query_text="merge",
            probe_run_id="probe:merge",
            page_index=0,
            raw_snapshot_id=search_one_id,
            source_object_path="$.feed[0].items[0]",
            exposure_kind="organic_search",
        ),
        AnalystSearchExposure(
            set_id="obby-search",
            set_version=1,
            platform_listing_id="yandex_games:2",
            query_text="obby",
            probe_run_id="probe:obby",
            page_index=0,
            raw_snapshot_id=search_two_id,
            source_object_path="$.feed[0].items[0]",
            exposure_kind="organic_search",
        ),
    )
    feed_exposures = (
        AnalystFeedExposure(
            platform_listing_id="yandex_games:1",
            probe_run_id="probe:feed",
            page_index=0,
            raw_snapshot_id=feed_id,
            source_object_path="$.feed[0].items[0]",
            exposure_kind="organic_feed",
            row=0,
            column=0,
        ),
    )
    export_payload = AnalystMarketExportPayload(
        spec_version="analyst-market-export-v1",
        snapshot_id=snapshot.snapshot_id,
        snapshot_content_hash=snapshot.content_hash,
        collection_parameters_status=snapshot.collection_parameters_status,
        effective_context=snapshot.effective_context.model_dump(mode="json"),
        search_page_limit=snapshot.search_page_limit,
        rich_metadata_raw_snapshot_ids=(rich_id,),
        listings=listings,
        comparable_memberships=memberships,
        update_observations=(),
        search_supply=search_supply,
        search_exposures=search_exposures,
        feed_exposures=feed_exposures,
    )
    market_export = AnalystMarketExportReport.model_validate(
        {
            **export_payload.model_dump(mode="python"),
            "content_hash": _hash_model(export_payload),
        }
    )
    features = AnalystMarketFeatureBuilder().build(snapshot, market_export)
    return store, snapshot, market_export, features


def test_pilot_verifier_replays_raw_and_traces_representative_medians(tmp_path: Path) -> None:
    store, snapshot, market_export, features = _pilot_artifacts(tmp_path / "raw")

    report = AnalystPilotVerifier(raw_store=store).build(snapshot, market_export, features)

    assert validate_analyst_pilot_verification(report) == report
    assert report.comparable_set_count == 2
    assert report.query_family_ids == ("merge-family", "obby-family")
    assert report.raw_evidence.referenced_raw_snapshot_count == 4
    assert report.raw_evidence.verified_raw_snapshot_count == 4
    assert len(report.representative_traces) == 2
    assert all(trace.feature_name == "rating_count" for trace in report.representative_traces)
    assert all(trace.contributions for trace in report.representative_traces)
    assert any("provisional_uncalibrated" in item for item in report.machine_detected_limitations)


def test_pilot_verifier_rejects_same_query_family_for_two_sets(tmp_path: Path) -> None:
    store, snapshot, market_export, features = _pilot_artifacts(
        tmp_path / "raw",
        same_query_family=True,
    )

    with pytest.raises(AnalystPilotError, match="distinct query families"):
        AnalystPilotVerifier(raw_store=store).build(snapshot, market_export, features)


def test_pilot_verifier_fails_when_referenced_raw_body_disappears(tmp_path: Path) -> None:
    store, snapshot, market_export, features = _pilot_artifacts(tmp_path / "raw")
    raw_id = market_export.search_supply[0].raw_snapshot_id
    metadata = store.get_metadata("yandex_public", raw_id)
    (store.root / metadata.content_path).unlink()

    with pytest.raises(AnalystPilotError, match="raw evidence replay failed"):
        AnalystPilotVerifier(raw_store=store).build(snapshot, market_export, features)
