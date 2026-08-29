from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from yandex_analytics_reaper.analyst_cli import (
    SearchComparableSetDeclaration,
    build_parser,
    main,
)
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


def _family() -> QueryFamilyVersion:
    return QueryFamilyVersion(
        family_id="merge-games",
        version=1,
        label="merge games",
        source_id="yandex_public",
        language="ru",
        created_at=datetime(2026, 8, 29, 17, 0, tzinfo=UTC),
        members=(
            QueryFamilyMember(
                query_text="merge",
                kind=QueryVariantKind.SEED,
            ),
        ),
    )


def _persist_completed_search_run(tmp_path: Path) -> str:
    raw_store = FilesystemRawSnapshotStore(tmp_path / "raw")
    probe_store = SQLiteProbeRunStore(tmp_path / "market.sqlite3")
    context = ProbeContext(profile_age_days=0)
    started_at = datetime(2026, 8, 29, 17, 5, tzinfo=UTC)
    run = probe_store.create_run(
        source_id="yandex_public",
        request_key="catalogue.search",
        kind=ProbeKind.SEARCH,
        context=context,
        query_text="merge",
        requested_page_limit=1,
        started_at=started_at,
    )
    body = json.dumps(
        {
            "feed": [
                {
                    "items": [
                        {"appID": 10},
                        {"appID": 9999, "source": "direct"},
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
            request_key="catalogue.search",
            method="GET",
            url="https://yandex.ru/games/api/catalogue/v2/search",
            status_code=200,
            headers={"content-type": "application/json"},
            body=body,
            retrieved_at=started_at,
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
            request_page_id=None,
            request_rtx_reqid=None,
            response_next_page_id=None,
            response_rtx_reqid=None,
            has_next_page=False,
        )
    )
    probe_store.finish_run(
        run.id,
        status=ProbeRunStatus.COMPLETED,
        completed_at=started_at,
    )
    return run.id


def test_analyst_cli_parses_operator_commands() -> None:
    family = build_parser().parse_args(
        ["persist-query-family", "family.json", "--output", "data/raw"]
    )
    comparable = build_parser().parse_args(
        ["build-search-comparable-set", "set.json", "--output", "data/raw"]
    )

    assert family.command == "persist-query-family"
    assert family.declaration == "family.json"
    assert family.output == "data/raw"
    assert comparable.command == "build-search-comparable-set"
    assert comparable.declaration == "set.json"
    assert comparable.output == "data/raw"


def test_persist_query_family_command_round_trips_to_operational_store(
    tmp_path: Path,
) -> None:
    family = _family()
    declaration = tmp_path / "family.json"
    declaration.write_text(family.model_dump_json(indent=2), encoding="utf-8")

    main(
        [
            "persist-query-family",
            str(declaration),
            "--output",
            str(tmp_path / "raw"),
        ]
    )

    assert SQLiteQueryFamilyStore(tmp_path / "market.sqlite3").get(
        family.family_id,
        family.version,
    ) == family


def test_build_search_comparable_set_command_replays_and_persists_explicit_runs(
    tmp_path: Path,
) -> None:
    family = _family()
    family_path = tmp_path / "family.json"
    family_path.write_text(family.model_dump_json(indent=2), encoding="utf-8")
    main(
        [
            "persist-query-family",
            str(family_path),
            "--output",
            str(tmp_path / "raw"),
        ]
    )
    run_id = _persist_completed_search_run(tmp_path)
    declaration = SearchComparableSetDeclaration(
        set_id="merge-search",
        version=1,
        query_family_id=family.family_id,
        query_family_version=family.version,
        created_at=datetime(2026, 8, 29, 17, 10, tzinfo=UTC),
        run_ids=(run_id,),
    )
    declaration_path = tmp_path / "comparable.json"
    declaration_path.write_text(
        declaration.model_dump_json(indent=2),
        encoding="utf-8",
    )

    main(
        [
            "build-search-comparable-set",
            str(declaration_path),
            "--output",
            str(tmp_path / "raw"),
        ]
    )

    stored = SQLiteComparableSetStore(tmp_path / "market.sqlite3").get(
        declaration.set_id,
        declaration.version,
    )
    assert stored is not None
    assert stored.query_family_id == family.family_id
    assert [run.probe_run_id for run in stored.runs] == [run_id]
    assert [member.platform_listing_id for member in stored.members] == ["yandex_games:10"]


def test_build_search_comparable_set_rejects_missing_query_family(tmp_path: Path) -> None:
    SQLiteProbeRunStore(tmp_path / "market.sqlite3")
    declaration = SearchComparableSetDeclaration(
        set_id="missing-family",
        version=1,
        query_family_id="missing",
        query_family_version=1,
        created_at=datetime(2026, 8, 29, 17, 10, tzinfo=UTC),
        run_ids=("probe:missing",),
    )
    declaration_path = tmp_path / "missing.json"
    declaration_path.write_text(
        declaration.model_dump_json(indent=2),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="query-family version is not persisted"):
        main(
            [
                "build-search-comparable-set",
                str(declaration_path),
                "--output",
                str(tmp_path / "raw"),
            ]
        )
