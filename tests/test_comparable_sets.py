from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from yandex_analytics_reaper.comparables import (
    ComparableSetConstructionError,
    YandexSearchComparableSetBuilder,
)
from yandex_analytics_reaper.domain import (
    ComparableSetMemberEvidence,
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


def _family() -> QueryFamilyVersion:
    return QueryFamilyVersion(
        family_id="merge-games",
        version=1,
        label="merge games",
        source_id="yandex_public",
        language="ru",
        created_at=datetime(2026, 8, 29, 8, 0, tzinfo=UTC),
        members=(
            QueryFamilyMember(query_text="merge", kind=QueryVariantKind.SEED),
            QueryFamilyMember(query_text="слияние", kind=QueryVariantKind.SYNONYM),
        ),
    )


def _persist_search_run(
    *,
    raw_store: FilesystemRawSnapshotStore,
    probe_store: SQLiteProbeRunStore,
    query: str,
    started_at: datetime,
    pages: tuple[tuple[int, ...], ...],
    raw_query: str | None = None,
    requested_page_limit: int = 2,
) -> str:
    context = ProbeContext(profile_age_days=0)
    run = probe_store.create_run(
        source_id="yandex_public",
        request_key="catalogue.search",
        kind=ProbeKind.SEARCH,
        context=context,
        query_text=query,
        requested_page_limit=requested_page_limit,
        started_at=started_at,
    )

    for index, app_ids in enumerate(pages):
        has_next = index < len(pages) - 1
        next_page_id = f"page-{index + 1}" if has_next else None
        next_rtx = f"req-{index + 1}" if has_next else None
        items: list[dict[str, object]] = [{"appID": app_id} for app_id in app_ids]
        if index == 0:
            items.append({"appID": 9999, "source": "direct"})
        payload = {
            "feed": [{"items": items}],
            "pageInfo": {
                "hasNextPage": has_next,
                "nextPageId": next_page_id,
                "rtxReqId": next_rtx,
            },
        }
        effective_raw_query = raw_query if raw_query is not None else query
        params: dict[str, object] = {
            "query": effective_raw_query,
            "lang": "ru",
        }
        if index > 0:
            params["page_id"] = f"page-{index}"
            params["rtx-reqid"] = f"req-{index}"
        response = CollectedResponse(
            source_id="yandex_public",
            request_key="catalogue.search",
            method="GET",
            url="https://yandex.ru/games/api/catalogue/v2/search",
            status_code=200,
            headers={"content-type": "application/json"},
            body=json.dumps(payload).encode(),
            retrieved_at=started_at + timedelta(seconds=index + 1),
            request_context={
                "probe_context": context.model_dump(mode="json"),
                "query": effective_raw_query,
                "params": params,
            },
        )
        metadata = raw_store.persist(response)
        probe_store.append_page(
            ProbePage(
                run_id=run.id,
                page_index=index,
                raw_snapshot_id=metadata.id,
                retrieved_at=metadata.retrieved_at,
                request_page_id=(None if index == 0 else f"page-{index}"),
                request_rtx_reqid=(None if index == 0 else f"req-{index}"),
                response_next_page_id=next_page_id,
                response_rtx_reqid=next_rtx,
                has_next_page=has_next,
            )
        )

    probe_store.finish_run(
        run.id,
        status=ProbeRunStatus.COMPLETED,
        completed_at=started_at + timedelta(seconds=10),
    )
    return run.id


def _build_fixture(
    tmp_path: Path,
) -> tuple[
    QueryFamilyVersion,
    object,
    FilesystemRawSnapshotStore,
    SQLiteProbeRunStore,
]:
    raw_store = FilesystemRawSnapshotStore(tmp_path / "raw")
    database_path = tmp_path / "market.sqlite3"
    probe_store = SQLiteProbeRunStore(database_path)
    family = _family()
    SQLiteQueryFamilyStore(database_path).persist(family)
    base = datetime(2026, 8, 29, 9, 0, tzinfo=UTC)
    merge_run = _persist_search_run(
        raw_store=raw_store,
        probe_store=probe_store,
        query="merge",
        started_at=base,
        pages=((10, 20), (20, 30)),
    )
    synonym_run = _persist_search_run(
        raw_store=raw_store,
        probe_store=probe_store,
        query="слияние",
        started_at=base + timedelta(minutes=2),
        pages=((20, 40), (50,)),
    )
    comparable_set = YandexSearchComparableSetBuilder(
        raw_store=raw_store,
        probe_store=probe_store,
    ).build(
        family,
        [synonym_run, merge_run],
        set_id="merge-games-search",
        version=1,
        created_at=base + timedelta(minutes=10),
    )
    return family, comparable_set, raw_store, probe_store


def test_builder_uses_family_order_unions_organic_results_and_keeps_evidence(
    tmp_path: Path,
) -> None:
    _, comparable_set, _, _ = _build_fixture(tmp_path)

    assert [run.query_text for run in comparable_set.runs] == ["merge", "слияние"]
    assert [member.platform_listing_id for member in comparable_set.members] == [
        "yandex_games:10",
        "yandex_games:20",
        "yandex_games:30",
        "yandex_games:40",
        "yandex_games:50",
    ]
    assert len(comparable_set.evidence) == 7
    assert all(
        item.platform_listing_id != "yandex_games:9999"
        for item in comparable_set.evidence
    )
    duplicate_evidence = [
        item for item in comparable_set.evidence if item.platform_listing_id == "yandex_games:20"
    ]
    assert len(duplicate_evidence) == 3


def test_builder_rejects_raw_query_that_disagrees_with_probe_run(tmp_path: Path) -> None:
    raw_store = FilesystemRawSnapshotStore(tmp_path / "raw")
    probe_store = SQLiteProbeRunStore(tmp_path / "market.sqlite3")
    family = QueryFamilyVersion(
        family_id="single",
        version=1,
        label="single",
        source_id="yandex_public",
        language="ru",
        created_at=datetime(2026, 8, 29, 8, 0, tzinfo=UTC),
        members=(QueryFamilyMember(query_text="merge", kind=QueryVariantKind.SEED),),
    )
    run_id = _persist_search_run(
        raw_store=raw_store,
        probe_store=probe_store,
        query="merge",
        raw_query="different",
        started_at=datetime(2026, 8, 29, 9, 0, tzinfo=UTC),
        pages=((10,),),
        requested_page_limit=1,
    )

    with pytest.raises(ComparableSetConstructionError, match="raw query"):
        YandexSearchComparableSetBuilder(
            raw_store=raw_store,
            probe_store=probe_store,
        ).build(
            family,
            [run_id],
            set_id="single-search",
            version=1,
            created_at=datetime(2026, 8, 29, 9, 1, tzinfo=UTC),
        )


def test_store_round_trips_idempotently_and_rejects_conflicting_version(tmp_path: Path) -> None:
    _, comparable_set, _, probe_store = _build_fixture(tmp_path)
    store = SQLiteComparableSetStore(probe_store.path)

    assert store.persist(comparable_set) == comparable_set
    assert store.persist(comparable_set) == comparable_set
    assert store.get(comparable_set.set_id, 1) == comparable_set
    assert store.latest(comparable_set.set_id) == comparable_set

    changed = comparable_set.model_copy(update={"parser_version": "999"})
    with pytest.raises(ValueError, match="conflicting comparable-set content"):
        store.persist(changed)


def test_store_rejects_family_membership_or_raw_page_provenance_mismatch(tmp_path: Path) -> None:
    _, comparable_set, _, probe_store = _build_fixture(tmp_path)
    store = SQLiteComparableSetStore(probe_store.path)

    wrong_runs = comparable_set.model_copy(
        update={
            "runs": (
                comparable_set.runs[0].model_copy(update={"query_text": "not-the-family-query"}),
                comparable_set.runs[1],
            )
        }
    )
    with pytest.raises(ValueError, match="persisted query-family membership"):
        store.persist(wrong_runs)

    first = comparable_set.evidence[0]
    wrong_evidence = first.model_copy(update={"raw_snapshot_id": "raw:wrong"})
    changed_evidence: tuple[ComparableSetMemberEvidence, ...] = (
        wrong_evidence,
        *comparable_set.evidence[1:],
    )
    wrong_raw = comparable_set.model_copy(update={"evidence": changed_evidence})
    with pytest.raises(ValueError, match="raw snapshot disagrees"):
        store.persist(wrong_raw)


def test_store_fails_closed_on_corrupt_evidence_order(tmp_path: Path) -> None:
    _, comparable_set, _, probe_store = _build_fixture(tmp_path)
    store = SQLiteComparableSetStore(probe_store.path)
    store.persist(comparable_set)

    with store.database.connect() as connection:
        connection.execute(
            """
            UPDATE comparable_set_member_evidence
            SET evidence_ordinal = 99
            WHERE set_id = ? AND version = ? AND evidence_ordinal = 0
            """,
            (comparable_set.set_id, comparable_set.version),
        )

    with pytest.raises(RuntimeError, match="evidence ordinals are not contiguous"):
        store.get(comparable_set.set_id, comparable_set.version)
