from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from yandex_analytics_reaper.domain import (
    ProbeContext,
    ProbeKind,
    ProbePage,
    ProbeRunStatus,
)
from yandex_analytics_reaper.sources.capabilities import CollectedResponse
from yandex_analytics_reaper.storage import FilesystemRawSnapshotStore, SQLiteProbeRunStore
from yandex_analytics_reaper.taxonomy import (
    TaxonomySampleCandidate,
    TaxonomySampleEvidence,
    TaxonomySampleManifest,
    TaxonomySamplingError,
    YandexTaxonomyDiversitySampler,
    select_taxonomy_diversity_candidates,
)


def _evidence(run_id: str = "run") -> tuple[TaxonomySampleEvidence, ...]:
    return (
        TaxonomySampleEvidence(
            probe_run_id=run_id,
            raw_snapshot_id=f"raw-{run_id}",
            page_index=0,
            source_object_path="$.feed[0].items[0]",
            origin_key="feed",
        ),
    )


def _candidate(
    app_id: int,
    *,
    categories: tuple[int, ...] = (),
    tags: tuple[int, ...] = (),
    developer: str | None = None,
    origin: str = "feed",
) -> TaxonomySampleCandidate:
    evidence = _evidence(str(app_id))[0].model_copy(update={"origin_key": origin})
    return TaxonomySampleCandidate(
        platform_listing_id=f"yandex_games:{app_id}",
        app_id=app_id,
        developer_keys=(() if developer is None else (developer,)),
        category_ids=categories,
        tag_ids=tags,
        origin_keys=(origin,),
        evidence=(evidence,),
    )


def test_selector_prioritizes_rare_features_and_is_input_order_independent() -> None:
    common_a = _candidate(1, categories=(10,))
    common_b = _candidate(2, categories=(10,))
    rare = _candidate(3, categories=(99,))

    first = select_taxonomy_diversity_candidates(
        (common_a, rare, common_b),
        target_size=2,
        max_per_developer=2,
    )
    second = select_taxonomy_diversity_candidates(
        (common_b, common_a, rare),
        target_size=2,
        max_per_developer=2,
    )

    assert first == second
    assert first[0].platform_listing_id == "yandex_games:3"


def test_selector_enforces_known_developer_cap() -> None:
    candidates = (
        _candidate(1, categories=(1,), developer="id:studio"),
        _candidate(2, categories=(2,), developer="id:studio"),
        _candidate(3, categories=(3,), developer="id:studio"),
        _candidate(4, categories=(4,), developer="id:other"),
    )

    selected = select_taxonomy_diversity_candidates(
        candidates,
        target_size=3,
        max_per_developer=2,
    )
    assert sum("id:studio" in item.developer_keys for item in selected) == 2

    with pytest.raises(ValueError, match="developer diversity cap"):
        select_taxonomy_diversity_candidates(
            candidates[:3],
            target_size=3,
            max_per_developer=2,
        )


def test_manifest_freezes_developer_cap_to_two() -> None:
    with pytest.raises(ValidationError):
        TaxonomySampleManifest.model_validate(
            {
                "sample_id": "bad-cap",
                "target_size": 100,
                "max_per_developer": 3,
                "run_ids": ["probe:one"],
            }
        )


def _persist_feed_run(
    *,
    raw_store: FilesystemRawSnapshotStore,
    probe_store: SQLiteProbeRunStore,
    app_ids: range,
    started_at: datetime,
    raw_language: str = "ru",
) -> str:
    context = ProbeContext(profile_age_days=0)
    run = probe_store.create_run(
        source_id="yandex_public",
        request_key="catalogue.feed",
        kind=ProbeKind.RECOMMENDATION_FEED,
        context=context,
        query_text=None,
        requested_page_limit=1,
        started_at=started_at,
    )
    items = [
        {
            "appID": app_id,
            "title": f"Feed Game {app_id}",
            "developer": {"id": app_id, "name": f"Studio {app_id}"},
            "categoryIDs": [app_id % 9],
            "tagIDs": [100 + app_id % 13],
        }
        for app_id in app_ids
    ]
    items.append({"appID": 999999, "source": "direct"})
    payload = {
        "feed": [{"items": items}],
        "pageInfo": {"hasNextPage": False},
    }
    params: dict[str, object] = {
        "games_count": len(app_ids),
        "with_promos": "false",
        "lang": raw_language,
        "device-type": "desktop",
        "platform": "desktop_other",
    }
    response = CollectedResponse(
        source_id="yandex_public",
        request_key="catalogue.feed",
        method="GET",
        url="https://yandex.ru/games/api/catalogue/v2/feed/",
        status_code=200,
        headers={"content-type": "application/json"},
        body=json.dumps(payload).encode(),
        retrieved_at=started_at + timedelta(seconds=1),
        request_context={
            "probe_context": context.model_dump(mode="json"),
            "params": params,
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
        completed_at=started_at + timedelta(seconds=2),
    )
    return run.id


def _persist_search_run(
    *,
    raw_store: FilesystemRawSnapshotStore,
    probe_store: SQLiteProbeRunStore,
    app_ids: range,
    query: str,
    started_at: datetime,
) -> str:
    context = ProbeContext(profile_age_days=0)
    run = probe_store.create_run(
        source_id="yandex_public",
        request_key="catalogue.search",
        kind=ProbeKind.SEARCH,
        context=context,
        query_text=query,
        requested_page_limit=1,
        started_at=started_at,
    )
    items = [
        {
            "appID": app_id,
            "title": f"Search Game {app_id}",
            "developer": {"id": app_id, "name": f"Studio {app_id}"},
            "categoryIDs": [app_id % 9],
            "tagIDs": [100 + app_id % 13],
        }
        for app_id in app_ids
    ]
    payload = {
        "feed": [{"items": items}],
        "pageInfo": {"hasNextPage": False},
    }
    params: dict[str, object] = {"query": query, "lang": "ru"}
    response = CollectedResponse(
        source_id="yandex_public",
        request_key="catalogue.search",
        method="GET",
        url="https://yandex.ru/games/api/catalogue/v2/search",
        status_code=200,
        headers={"content-type": "application/json"},
        body=json.dumps(payload).encode(),
        retrieved_at=started_at + timedelta(seconds=1),
        request_context={
            "probe_context": context.model_dump(mode="json"),
            "query": query,
            "params": params,
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
        completed_at=started_at + timedelta(seconds=2),
    )
    return run.id


def test_sampler_replays_raw_feed_and_search_and_keeps_provenance(tmp_path: Path) -> None:
    raw_store = FilesystemRawSnapshotStore(tmp_path / "raw")
    probe_store = SQLiteProbeRunStore(tmp_path / "market.sqlite3")
    base = datetime(2026, 8, 29, 10, 0, tzinfo=UTC)
    feed_run = _persist_feed_run(
        raw_store=raw_store,
        probe_store=probe_store,
        app_ids=range(1000, 1060),
        started_at=base,
    )
    search_run = _persist_search_run(
        raw_store=raw_store,
        probe_store=probe_store,
        app_ids=range(2000, 2060),
        query="games",
        started_at=base + timedelta(minutes=1),
    )
    sampler = YandexTaxonomyDiversitySampler(
        raw_store=raw_store,
        probe_store=probe_store,
    )
    manifest = TaxonomySampleManifest(
        sample_id="taxonomy-gold-seed-1",
        target_size=100,
        run_ids=(search_run, feed_run),
    )

    report = sampler.analyze(manifest)
    repeated = sampler.analyze(manifest.model_copy(update={"run_ids": (feed_run, search_run)}))

    assert report == repeated
    assert report.candidate_pool_size == 120
    assert len(report.selected) == 100
    assert report.input_run_ids == tuple(sorted((feed_run, search_run)))
    assert report.selected_origin_keys == ("feed", "search:games")
    assert all(item.app_id != 999999 for item in report.selected)
    assert all(item.evidence for item in report.selected)
    assert len(report.sample_content_hash) == 64
    assert report.selected_category_id_count == report.pool_category_id_count
    assert report.selected_tag_id_count == report.pool_tag_id_count


def test_sampler_rejects_raw_request_context_mismatch(tmp_path: Path) -> None:
    raw_store = FilesystemRawSnapshotStore(tmp_path / "raw")
    probe_store = SQLiteProbeRunStore(tmp_path / "market.sqlite3")
    run_id = _persist_feed_run(
        raw_store=raw_store,
        probe_store=probe_store,
        app_ids=range(3000, 3100),
        started_at=datetime(2026, 8, 29, 11, 0, tzinfo=UTC),
        raw_language="en",
    )

    with pytest.raises(TaxonomySamplingError, match="feed raw param lang"):
        YandexTaxonomyDiversitySampler(
            raw_store=raw_store,
            probe_store=probe_store,
        ).analyze(
            TaxonomySampleManifest(
                sample_id="bad-request",
                target_size=100,
                run_ids=(run_id,),
            )
        )
