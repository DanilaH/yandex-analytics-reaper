from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from yandex_analytics_reaper.analyst import (
    AnalystComparableSetReference,
    AnalystRawSnapshotReference,
    AnalystSnapshotBuilder,
    AnalystSnapshotDeclaration,
    AnalystSnapshotError,
    validate_analyst_snapshot_report,
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
from yandex_analytics_reaper.sources.capabilities import CollectedResponse
from yandex_analytics_reaper.storage import (
    FilesystemRawSnapshotStore,
    SQLiteComparableSetStore,
    SQLiteProbeRunStore,
    SQLiteQueryFamilyStore,
)

_BASE = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)


def _persist_search_comparable(
    tmp_path: Path,
    *,
    context: ProbeContext | None = None,
    page_limit: int = 1,
    suffix: str = "merge",
) -> tuple[str, int, ProbeContext]:
    raw_store = FilesystemRawSnapshotStore(tmp_path / "raw")
    database_path = tmp_path / "market.sqlite3"
    probe_store = SQLiteProbeRunStore(database_path)
    effective_context = context or ProbeContext(profile_age_days=0)
    query = suffix
    family = QueryFamilyVersion(
        family_id=f"{suffix}-family",
        version=1,
        label=f"{suffix} games",
        source_id="yandex_public",
        language=effective_context.language,
        created_at=_BASE - timedelta(minutes=5),
        members=(QueryFamilyMember(query_text=query, kind=QueryVariantKind.SEED),),
    )
    SQLiteQueryFamilyStore(database_path).persist(family)
    run = probe_store.create_run(
        source_id="yandex_public",
        request_key="catalogue.search",
        kind=ProbeKind.SEARCH,
        context=effective_context,
        query_text=query,
        requested_page_limit=page_limit,
        started_at=_BASE,
    )
    response = CollectedResponse(
        source_id="yandex_public",
        request_key="catalogue.search",
        method="GET",
        url="https://yandex.ru/games/api/catalogue/v2/search",
        status_code=200,
        headers={"content-type": "application/json"},
        body=json.dumps(
            {
                "feed": [{"items": [{"appID": 10}, {"appID": 20}]}],
                "pageInfo": {
                    "hasNextPage": False,
                    "nextPageId": None,
                    "rtxReqId": None,
                },
            }
        ).encode(),
        retrieved_at=_BASE + timedelta(seconds=1),
        request_context={
            "probe_context": effective_context.model_dump(mode="json"),
            "query": query,
            "params": {"query": query, "lang": effective_context.language},
        },
    )
    metadata = raw_store.persist(response)
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
        set_id=f"{suffix}-search",
        version=1,
        created_at=_BASE + timedelta(seconds=3),
    )
    SQLiteComparableSetStore(database_path).persist(comparable)
    return comparable.set_id, comparable.version, effective_context


def _persist_feed_run(
    tmp_path: Path,
    context: ProbeContext,
    *,
    status: ProbeRunStatus = ProbeRunStatus.COMPLETED,
) -> str:
    raw_store = FilesystemRawSnapshotStore(tmp_path / "raw")
    probe_store = SQLiteProbeRunStore(tmp_path / "market.sqlite3")
    run = probe_store.create_run(
        source_id="yandex_public",
        request_key="catalogue.feed",
        kind=ProbeKind.RECOMMENDATION_FEED,
        context=context,
        requested_page_limit=1,
        started_at=_BASE + timedelta(seconds=4),
    )
    response = CollectedResponse(
        source_id="yandex_public",
        request_key="catalogue.feed",
        method="GET",
        url="https://yandex.ru/games/api/catalogue/v2/feed/",
        status_code=200,
        headers={"content-type": "application/json"},
        body=json.dumps(
            {
                "feed": [{"items": [{"appID": 10}]}],
                "pageInfo": {
                    "hasNextPage": False,
                    "nextPageId": None,
                    "rtxReqId": None,
                },
            }
        ).encode(),
        retrieved_at=_BASE + timedelta(seconds=5),
        request_context={
            "probe_context": context.model_dump(mode="json"),
            "params": {"games_count": 20, "lang": context.language},
        },
    )
    metadata = raw_store.persist(response)
    probe_store.append_page(
        ProbePage(
            run_id=run.id,
            page_index=0,
            raw_snapshot_id=metadata.id,
            retrieved_at=metadata.retrieved_at,
            has_next_page=False,
        )
    )
    if status is ProbeRunStatus.COMPLETED:
        probe_store.finish_run(
            run.id,
            status=status,
            completed_at=_BASE + timedelta(seconds=6),
        )
    else:
        probe_store.finish_run(
            run.id,
            status=status,
            completed_at=_BASE + timedelta(seconds=6),
            error="synthetic terminal failure",
            error_raw_snapshot_id=metadata.id,
        )
    return run.id


def _persist_get_games_snapshot(tmp_path: Path, *app_ids: int) -> str:
    raw_store = FilesystemRawSnapshotStore(tmp_path / "raw")
    response = CollectedResponse(
        source_id="yandex_public",
        request_key="catalogue.get_games",
        method="POST",
        url="https://yandex.ru/games/api/catalogue/v2/get_games",
        status_code=200,
        headers={"content-type": "application/json"},
        body=json.dumps(
            {
                "games": [
                    {
                        "appID": app_id,
                        "title": f"Game {app_id}",
                        "gqRating": 70 + index,
                        "rating": 4.2,
                        "ratingCount": 100 + index,
                    }
                    for index, app_id in enumerate(app_ids)
                ]
            }
        ).encode(),
        retrieved_at=_BASE + timedelta(seconds=7),
        request_context={"app_ids": list(app_ids)},
    )
    return raw_store.persist(response).id


def _declaration(
    set_id: str,
    set_version: int,
    raw_snapshot_id: str,
    *,
    feed_run_ids: tuple[str, ...] = (),
    created_at: datetime = _BASE + timedelta(seconds=20),
) -> AnalystSnapshotDeclaration:
    return AnalystSnapshotDeclaration(
        spec_version="analyst-snapshot-v1",
        snapshot_id="pilot:merge:v1",
        created_at=created_at,
        collection_parameters_status="provisional_uncalibrated",
        comparable_sets=(
            AnalystComparableSetReference(set_id=set_id, version=set_version),
        ),
        feed_run_ids=feed_run_ids,
        rich_metadata_snapshots=(
            AnalystRawSnapshotReference(
                source_id="yandex_public",
                raw_snapshot_id=raw_snapshot_id,
                request_key="catalogue.get_games",
            ),
        ),
    )


def test_builder_binds_replayed_comparable_feed_and_rich_metadata(tmp_path: Path) -> None:
    set_id, set_version, context = _persist_search_comparable(tmp_path)
    feed_run_id = _persist_feed_run(tmp_path, context)
    raw_snapshot_id = _persist_get_games_snapshot(tmp_path, 10)

    report = AnalystSnapshotBuilder(
        raw_store=FilesystemRawSnapshotStore(tmp_path / "raw"),
        database_path=tmp_path / "market.sqlite3",
    ).build(
        _declaration(
            set_id,
            set_version,
            raw_snapshot_id,
            feed_run_ids=(feed_run_id,),
        )
    )

    assert report.collection_parameters_status == "provisional_uncalibrated"
    assert report.search_page_limit == 1
    assert report.effective_context == context
    assert report.comparable_sets[0].member_listing_ids == (
        "yandex_games:10",
        "yandex_games:20",
    )
    assert report.feed_runs[0].run_id == feed_run_id
    assert report.rich_metadata[0].relevant_listing_ids == ("yandex_games:10",)
    assert validate_analyst_snapshot_report(report) == report


def test_builder_rejects_partial_feed_run(tmp_path: Path) -> None:
    set_id, set_version, context = _persist_search_comparable(tmp_path)
    feed_run_id = _persist_feed_run(tmp_path, context, status=ProbeRunStatus.PARTIAL)
    raw_snapshot_id = _persist_get_games_snapshot(tmp_path, 10)

    with pytest.raises(AnalystSnapshotError, match="completed non-empty Yandex feed run"):
        AnalystSnapshotBuilder(
            raw_store=FilesystemRawSnapshotStore(tmp_path / "raw"),
            database_path=tmp_path / "market.sqlite3",
        ).build(
            _declaration(
                set_id,
                set_version,
                raw_snapshot_id,
                feed_run_ids=(feed_run_id,),
            )
        )


def test_builder_rejects_feed_from_different_effective_context(tmp_path: Path) -> None:
    set_id, set_version, _ = _persist_search_comparable(tmp_path)
    different_context = ProbeContext(language="en", profile_age_days=0)
    feed_run_id = _persist_feed_run(tmp_path, different_context)
    raw_snapshot_id = _persist_get_games_snapshot(tmp_path, 10)

    with pytest.raises(AnalystSnapshotError, match="does not match.*effective context"):
        AnalystSnapshotBuilder(
            raw_store=FilesystemRawSnapshotStore(tmp_path / "raw"),
            database_path=tmp_path / "market.sqlite3",
        ).build(
            _declaration(
                set_id,
                set_version,
                raw_snapshot_id,
                feed_run_ids=(feed_run_id,),
            )
        )


def test_builder_rejects_rich_metadata_unrelated_to_comparable_members(tmp_path: Path) -> None:
    set_id, set_version, _ = _persist_search_comparable(tmp_path)
    raw_snapshot_id = _persist_get_games_snapshot(tmp_path, 777)

    with pytest.raises(AnalystSnapshotError, match="contains no listing"):
        AnalystSnapshotBuilder(
            raw_store=FilesystemRawSnapshotStore(tmp_path / "raw"),
            database_path=tmp_path / "market.sqlite3",
        ).build(_declaration(set_id, set_version, raw_snapshot_id))


def test_builder_rejects_created_at_before_bound_evidence(tmp_path: Path) -> None:
    set_id, set_version, _ = _persist_search_comparable(tmp_path)
    raw_snapshot_id = _persist_get_games_snapshot(tmp_path, 10)

    with pytest.raises(AnalystSnapshotError, match="created_at cannot precede evidence"):
        AnalystSnapshotBuilder(
            raw_store=FilesystemRawSnapshotStore(tmp_path / "raw"),
            database_path=tmp_path / "market.sqlite3",
        ).build(
            _declaration(
                set_id,
                set_version,
                raw_snapshot_id,
                created_at=_BASE,
            )
        )


def test_persisted_report_hash_detects_tampering(tmp_path: Path) -> None:
    set_id, set_version, _ = _persist_search_comparable(tmp_path)
    raw_snapshot_id = _persist_get_games_snapshot(tmp_path, 10)
    report = AnalystSnapshotBuilder(
        raw_store=FilesystemRawSnapshotStore(tmp_path / "raw"),
        database_path=tmp_path / "market.sqlite3",
    ).build(_declaration(set_id, set_version, raw_snapshot_id))

    tampered = report.model_copy(update={"snapshot_id": "tampered"})
    with pytest.raises(AnalystSnapshotError, match="content_hash"):
        validate_analyst_snapshot_report(tampered)
