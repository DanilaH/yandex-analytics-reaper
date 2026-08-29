from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from yandex_analytics_reaper.analyst import (
    AnalystComparableSetReference,
    AnalystExportError,
    AnalystMarketExporter,
    AnalystRawSnapshotReference,
    AnalystSnapshotBuilder,
    AnalystSnapshotDeclaration,
    validate_analyst_market_export,
    write_analyst_export_csv,
)
from yandex_analytics_reaper.comparables import YandexSearchComparableSetBuilder
from yandex_analytics_reaper.domain import (
    ProbeContext,
    ProbeKind,
    ProbePage,
    ProbeRunStatus,
    QueryFamilyMember,
    QueryFamilyVersion,
    QueryVariantKind,
)
from yandex_analytics_reaper.ingestion import YandexNormalizationPersistence
from yandex_analytics_reaper.sources.capabilities import CollectedResponse
from yandex_analytics_reaper.sources.yandex.parsers import YandexGetGamesParser
from yandex_analytics_reaper.storage import (
    FilesystemRawSnapshotStore,
    SQLiteComparableSetStore,
    SQLiteProbeRunStore,
    SQLiteQueryFamilyStore,
)

_BASE = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)


def _stores(tmp_path: Path) -> tuple[FilesystemRawSnapshotStore, SQLiteProbeRunStore]:
    return (
        FilesystemRawSnapshotStore(tmp_path / "raw"),
        SQLiteProbeRunStore(tmp_path / "market.sqlite3"),
    )


def _persist_search_comparable(tmp_path: Path) -> tuple[str, int, ProbeContext]:
    raw_store, probe_store = _stores(tmp_path)
    context = ProbeContext(profile_age_days=0)
    family = QueryFamilyVersion(
        family_id="merge-family",
        version=1,
        label="merge games",
        source_id="yandex_public",
        language="ru",
        created_at=_BASE - timedelta(minutes=5),
        members=(QueryFamilyMember(query_text="merge", kind=QueryVariantKind.SEED),),
    )
    SQLiteQueryFamilyStore(tmp_path / "market.sqlite3").persist(family)
    run = probe_store.create_run(
        source_id="yandex_public",
        request_key="catalogue.search",
        kind=ProbeKind.SEARCH,
        context=context,
        query_text="merge",
        requested_page_limit=1,
        started_at=_BASE,
    )
    body = json.dumps(
        {
            "feed": [
                {
                    "items": [
                        {"appID": 10},
                        {"appID": 20},
                        {"appID": 9999, "source": "direct"},
                    ]
                }
            ],
            "totalGamesCount": 42,
            "pageInfo": {
                "hasNextPage": False,
                "nextPageId": None,
                "rtxReqId": None,
            },
        }
    ).encode()
    metadata = raw_store.persist(
        CollectedResponse(
            source_id="yandex_public",
            request_key="catalogue.search",
            method="GET",
            url="https://yandex.ru/games/api/catalogue/v2/search",
            status_code=200,
            headers={"content-type": "application/json"},
            body=body,
            retrieved_at=_BASE + timedelta(seconds=1),
            request_context={
                "probe_context": context.model_dump(mode="json"),
                "query": "merge",
                "params": {"query": "merge", "lang": "ru"},
            },
        )
    )
    probe_store.append_page(
        ProbePage(
            run_id=run.id,
            page_index=0,
            raw_snapshot_id=metadata.id,
            retrieved_at=metadata.retrieved_at,
            has_next_page=False,
        )
    )
    probe_store.finish_run(
        run.id,
        status=ProbeRunStatus.COMPLETED,
        completed_at=_BASE + timedelta(seconds=2),
    )
    comparable = YandexSearchComparableSetBuilder(
        raw_store=raw_store,
        probe_store=probe_store,
    ).build(
        family,
        (run.id,),
        set_id="merge-search",
        version=1,
        created_at=_BASE + timedelta(seconds=3),
    )
    SQLiteComparableSetStore(tmp_path / "market.sqlite3").persist(comparable)
    return comparable.set_id, comparable.version, context


def _persist_feed_run(tmp_path: Path, context: ProbeContext) -> str:
    raw_store, probe_store = _stores(tmp_path)
    run = probe_store.create_run(
        source_id="yandex_public",
        request_key="catalogue.feed",
        kind=ProbeKind.RECOMMENDATION_FEED,
        context=context,
        requested_page_limit=1,
        started_at=_BASE + timedelta(seconds=4),
    )
    body = json.dumps(
        {
            "feed": [
                {
                    "items": [
                        {"appID": 10, "row": 1, "column": 2},
                        {"appID": 777, "source": "direct"},
                    ]
                }
            ],
            "pageInfo": {
                "hasNextPage": False,
                "nextPageId": None,
                "rtxReqId": None,
            },
        }
    ).encode()
    metadata = raw_store.persist(
        CollectedResponse(
            source_id="yandex_public",
            request_key="catalogue.feed",
            method="GET",
            url="https://yandex.ru/games/api/catalogue/v2/feed/",
            status_code=200,
            headers={"content-type": "application/json"},
            body=body,
            retrieved_at=_BASE + timedelta(seconds=5),
            request_context={
                "probe_context": context.model_dump(mode="json"),
                "params": {"games_count": 20, "lang": "ru"},
            },
        )
    )
    probe_store.append_page(
        ProbePage(
            run_id=run.id,
            page_index=0,
            raw_snapshot_id=metadata.id,
            retrieved_at=metadata.retrieved_at,
            has_next_page=False,
        )
    )
    probe_store.finish_run(
        run.id,
        status=ProbeRunStatus.COMPLETED,
        completed_at=_BASE + timedelta(seconds=6),
    )
    return run.id


def _persist_and_normalize_details(
    tmp_path: Path,
    *,
    retrieved_at: datetime,
    title: str,
    developer_name: str,
    gq_rating: int,
) -> str:
    raw_store = FilesystemRawSnapshotStore(tmp_path / "raw")
    body = json.dumps(
        {
            "games": [
                {
                    "appID": 10,
                    "title": title,
                    "developer": {"id": 501, "name": developer_name},
                    "gqRating": gq_rating,
                    "rating": 4.25,
                    "ratingCount": 120,
                    "firstPublished": 1_756_000_000,
                    "features": {
                        "languages": ["ru", "en"],
                        "platforms": ["desktop", "mobile"],
                        "orientation": "any",
                        "cloud_save": True,
                    },
                    "extraFeatures": {
                        "leaderboards": False,
                        "purchases": True,
                        "hasProducts": False,
                    },
                }
            ]
        }
    ).encode()
    metadata = raw_store.persist(
        CollectedResponse(
            source_id="yandex_public",
            request_key="catalogue.get_games",
            method="POST",
            url="https://yandex.ru/games/api/catalogue/v2/get_games",
            status_code=200,
            headers={"content-type": "application/json"},
            body=body,
            retrieved_at=retrieved_at,
            request_context={"app_ids": [10]},
        )
    )
    details = YandexGetGamesParser().parse(body).games[0]
    YandexNormalizationPersistence(tmp_path / "market.sqlite3").persist_details(
        details,
        metadata,
    )
    return metadata.id


def _snapshot(
    tmp_path: Path,
    *,
    set_id: str,
    set_version: int,
    rich_raw_id: str,
    feed_run_id: str | None = None,
):
    declaration = AnalystSnapshotDeclaration(
        spec_version="analyst-snapshot-v1",
        snapshot_id="pilot:merge:v1",
        created_at=_BASE + timedelta(seconds=20),
        collection_parameters_status="provisional_uncalibrated",
        comparable_sets=(
            AnalystComparableSetReference(set_id=set_id, version=set_version),
        ),
        feed_run_ids=() if feed_run_id is None else (feed_run_id,),
        rich_metadata_snapshots=(
            AnalystRawSnapshotReference(
                source_id="yandex_public",
                raw_snapshot_id=rich_raw_id,
                request_key="catalogue.get_games",
            ),
        ),
    )
    return AnalystSnapshotBuilder(
        raw_store=FilesystemRawSnapshotStore(tmp_path / "raw"),
        database_path=tmp_path / "market.sqlite3",
    ).build(declaration)


def test_export_is_snapshot_scoped_and_keeps_missingness(tmp_path: Path) -> None:
    set_id, set_version, _ = _persist_search_comparable(tmp_path)
    old_raw = _persist_and_normalize_details(
        tmp_path,
        retrieved_at=_BASE + timedelta(seconds=7),
        title="Old Merge",
        developer_name="Old Studio",
        gq_rating=81,
    )
    snapshot = _snapshot(
        tmp_path,
        set_id=set_id,
        set_version=set_version,
        rich_raw_id=old_raw,
    )

    _persist_and_normalize_details(
        tmp_path,
        retrieved_at=_BASE + timedelta(seconds=30),
        title="New Merge",
        developer_name="Renamed Studio",
        gq_rating=99,
    )

    export = AnalystMarketExporter(
        raw_store=FilesystemRawSnapshotStore(tmp_path / "raw"),
        database_path=tmp_path / "market.sqlite3",
    ).build(snapshot)

    assert validate_analyst_market_export(export) == export
    assert [row.platform_listing_id for row in export.listings] == [
        "yandex_games:10",
        "yandex_games:20",
    ]
    first, missing = export.listings
    assert first.title.value == "Old Merge"
    assert first.developer_name.value == "Old Studio"
    assert first.yandex_games_rating.value == 81
    assert first.rating_count.value == 120
    assert first.title.evidence is not None
    assert first.title.evidence.raw_snapshot_ids == (old_raw,)
    assert missing.title.value is None
    assert missing.title.missing_reason == "not_observed"
    assert missing.yandex_games_rating.value is None
    assert export.search_supply[0].total_games_count == 42
    assert {row.platform_listing_id for row in export.search_exposures} == {
        "yandex_games:10",
        "yandex_games:20",
    }
    assert all(row.exposure_kind == "organic_search" for row in export.search_exposures)


def test_export_keeps_feed_exposure_separate_from_metrics(tmp_path: Path) -> None:
    set_id, set_version, context = _persist_search_comparable(tmp_path)
    feed_run_id = _persist_feed_run(tmp_path, context)
    rich_raw = _persist_and_normalize_details(
        tmp_path,
        retrieved_at=_BASE + timedelta(seconds=7),
        title="Merge",
        developer_name="Studio",
        gq_rating=80,
    )
    snapshot = _snapshot(
        tmp_path,
        set_id=set_id,
        set_version=set_version,
        rich_raw_id=rich_raw,
        feed_run_id=feed_run_id,
    )

    export = AnalystMarketExporter(
        raw_store=FilesystemRawSnapshotStore(tmp_path / "raw"),
        database_path=tmp_path / "market.sqlite3",
    ).build(snapshot)

    assert [(row.platform_listing_id, row.exposure_kind) for row in export.feed_exposures] == [
        ("yandex_games:10", "organic_feed"),
        ("yandex_games:777", "sponsored_feed"),
    ]
    assert export.listings[0].yandex_games_rating.value == 80


def test_export_csv_is_create_only(tmp_path: Path) -> None:
    set_id, set_version, _ = _persist_search_comparable(tmp_path)
    rich_raw = _persist_and_normalize_details(
        tmp_path,
        retrieved_at=_BASE + timedelta(seconds=7),
        title="Merge",
        developer_name="Studio",
        gq_rating=80,
    )
    snapshot = _snapshot(
        tmp_path,
        set_id=set_id,
        set_version=set_version,
        rich_raw_id=rich_raw,
    )
    export = AnalystMarketExporter(
        raw_store=FilesystemRawSnapshotStore(tmp_path / "raw"),
        database_path=tmp_path / "market.sqlite3",
    ).build(snapshot)
    csv_dir = tmp_path / "csv"

    write_analyst_export_csv(export, csv_dir)

    assert (csv_dir / "listings.csv").is_file()
    assert (csv_dir / "search_supply.csv").is_file()
    assert (csv_dir / "search_exposures.csv").is_file()
    with pytest.raises(AnalystExportError, match="already exists"):
        write_analyst_export_csv(export, csv_dir)


def test_export_hash_detects_tampering(tmp_path: Path) -> None:
    set_id, set_version, _ = _persist_search_comparable(tmp_path)
    rich_raw = _persist_and_normalize_details(
        tmp_path,
        retrieved_at=_BASE + timedelta(seconds=7),
        title="Merge",
        developer_name="Studio",
        gq_rating=80,
    )
    export = AnalystMarketExporter(
        raw_store=FilesystemRawSnapshotStore(tmp_path / "raw"),
        database_path=tmp_path / "market.sqlite3",
    ).build(
        _snapshot(
            tmp_path,
            set_id=set_id,
            set_version=set_version,
            rich_raw_id=rich_raw,
        )
    )

    tampered = export.model_copy(update={"snapshot_id": "tampered"})
    with pytest.raises(AnalystExportError, match="content_hash"):
        validate_analyst_market_export(tampered)
