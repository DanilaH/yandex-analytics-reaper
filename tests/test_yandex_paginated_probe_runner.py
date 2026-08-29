from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from yandex_analytics_reaper.domain import ProbeContext, ProbeRunStatus
from yandex_analytics_reaper.ingestion import ProbeCollectionError, YandexPaginatedProbeRunner
from yandex_analytics_reaper.schema_drift import SQLiteSchemaDriftRegistry
from yandex_analytics_reaper.sources.capabilities import CollectedResponse
from yandex_analytics_reaper.storage import FilesystemRawSnapshotStore, SQLiteProbeRunStore


class FakeYandexClient:
    source_id = "yandex_public"

    def __init__(
        self,
        *,
        feed_responses: list[tuple[int, dict[str, object]]] | None = None,
        search_responses: list[tuple[int, dict[str, object]]] | None = None,
    ) -> None:
        self.feed_responses = list(feed_responses or [])
        self.search_responses = list(search_responses or [])
        self.feed_calls: list[tuple[str | None, str | None]] = []
        self.search_calls: list[tuple[str, str | None, str | None]] = []
        self.base_time = datetime(2026, 8, 29, 9, 0, 1, tzinfo=UTC)
        self.response_index = 0

    def collect_feed(
        self,
        context: ProbeContext,
        *,
        count: int = 20,
        page_id: str | None = None,
        rtx_reqid: str | None = None,
    ) -> CollectedResponse:
        self.feed_calls.append((page_id, rtx_reqid))
        status, payload = self.feed_responses.pop(0)
        params: dict[str, str | int] = {
            "games_count": count,
            "with_promos": "false",
            "lang": context.language,
            "device-type": context.device_type,
            "platform": context.platform,
        }
        if page_id is not None:
            params["page_id"] = page_id
        if rtx_reqid is not None:
            params["rtx-reqid"] = rtx_reqid
        return self._response(
            status=status,
            payload=payload,
            request_key="catalogue.feed",
            request_context={"probe_context": context.model_dump(mode="json"), "params": params},
        )

    def collect_search(
        self,
        query: str,
        context: ProbeContext,
        *,
        page_id: str | None = None,
        rtx_reqid: str | None = None,
    ) -> CollectedResponse:
        self.search_calls.append((query, page_id, rtx_reqid))
        status, payload = self.search_responses.pop(0)
        params: dict[str, str] = {"query": query, "lang": context.language}
        if page_id is not None:
            params["page_id"] = page_id
        if rtx_reqid is not None:
            params["rtx-reqid"] = rtx_reqid
        return self._response(
            status=status,
            payload=payload,
            request_key="catalogue.search",
            request_context={
                "probe_context": context.model_dump(mode="json"),
                "query": query,
                "params": params,
            },
        )

    def _response(
        self,
        *,
        status: int,
        payload: dict[str, object],
        request_key: str,
        request_context: dict[str, object],
    ) -> CollectedResponse:
        retrieved_at = self.base_time + timedelta(seconds=self.response_index)
        self.response_index += 1
        return CollectedResponse(
            source_id=self.source_id,
            request_key=request_key,
            method="GET",
            url=f"https://yandex.ru/games/{request_key}",
            status_code=status,
            headers={"content-type": "application/json"},
            body=json.dumps(payload).encode(),
            retrieved_at=retrieved_at,
            request_context=request_context,
        )


def _page(
    app_id: int,
    *,
    has_next: bool,
    next_page_id: str | None = None,
    rtx_reqid: str | None = None,
) -> dict[str, object]:
    return {
        "feed": [{"items": [{"appID": app_id}]}],
        "pageInfo": {
            "hasNextPage": has_next,
            "nextPageId": next_page_id,
            "rtxReqId": rtx_reqid,
        },
    }


def _runner(
    tmp_path: Path,
    client: FakeYandexClient,
) -> tuple[YandexPaginatedProbeRunner, SQLiteProbeRunStore]:
    raw_store = FilesystemRawSnapshotStore(tmp_path / "raw")
    probe_store = SQLiteProbeRunStore(tmp_path / "market.sqlite3")
    runner = YandexPaginatedProbeRunner(
        client=client,
        raw_store=raw_store,
        probe_store=probe_store,
        schema_registry=SQLiteSchemaDriftRegistry(tmp_path / "market.sqlite3"),
        clock=lambda: datetime(2026, 8, 29, 9, 0, tzinfo=UTC),
    )
    return runner, probe_store


def test_feed_runner_groups_cursor_chain_and_completes_on_source_exhaustion(
    tmp_path: Path,
) -> None:
    client = FakeYandexClient(
        feed_responses=[
            (200, _page(1, has_next=True, next_page_id="page-1", rtx_reqid="req-1")),
            (200, _page(2, has_next=False)),
        ]
    )
    runner, probe_store = _runner(tmp_path, client)

    result = runner.run_feed(ProbeContext(), page_limit=3, count=20)

    assert result.record.run.status is ProbeRunStatus.COMPLETED
    assert len(result.record.pages) == 2
    assert [page.page_index for page in result.record.pages] == [0, 1]
    assert client.feed_calls == [(None, None), ("page-1", "req-1")]
    assert [page.games[0].app_id for page in result.parsed_pages] == [1, 2]
    reloaded = probe_store.get_run(result.record.run.id)
    assert reloaded == result.record


def test_feed_runner_completes_at_requested_limit_even_if_more_pages_exist(
    tmp_path: Path,
) -> None:
    client = FakeYandexClient(
        feed_responses=[
            (200, _page(1, has_next=True, next_page_id="page-1", rtx_reqid="req-1")),
        ]
    )
    runner, _ = _runner(tmp_path, client)

    result = runner.run_feed(ProbeContext(), page_limit=1)

    assert result.record.run.status is ProbeRunStatus.COMPLETED
    assert len(result.record.pages) == 1
    assert result.record.pages[0].has_next_page is True
    assert client.feed_calls == [(None, None)]


def test_mid_run_http_failure_marks_run_partial_and_preserves_prior_pages(tmp_path: Path) -> None:
    client = FakeYandexClient(
        feed_responses=[
            (200, _page(1, has_next=True, next_page_id="page-1", rtx_reqid="req-1")),
            (503, {"error": "temporarily unavailable"}),
        ]
    )
    runner, probe_store = _runner(tmp_path, client)

    with pytest.raises(ProbeCollectionError, match="HTTP 503"):
        runner.run_feed(ProbeContext(), page_limit=3)

    with probe_store.database.connect() as connection:
        run_id = str(connection.execute("SELECT id FROM probe_runs").fetchone()["id"])
    record = probe_store.get_run(run_id)
    assert record is not None
    assert record.run.status is ProbeRunStatus.PARTIAL
    assert len(record.pages) == 1
    assert record.run.error is not None and "HTTP 503" in record.run.error
    assert record.run.error_raw_snapshot_id is not None
    assert record.run.error_raw_snapshot_id != record.pages[0].raw_snapshot_id
    error_snapshot = FilesystemRawSnapshotStore(tmp_path / "raw").get_metadata(
        client.source_id,
        record.run.error_raw_snapshot_id,
    )
    assert error_snapshot.http_status == 503


def test_first_page_breaking_schema_marks_run_failed(tmp_path: Path) -> None:
    client = FakeYandexClient(feed_responses=[(200, {"unexpected": []})])
    runner, probe_store = _runner(tmp_path, client)

    with pytest.raises(ProbeCollectionError, match="breaking source-schema drift"):
        runner.run_feed(ProbeContext(), page_limit=2)

    with probe_store.database.connect() as connection:
        run_id = str(connection.execute("SELECT id FROM probe_runs").fetchone()["id"])
    record = probe_store.get_run(run_id)
    assert record is not None
    assert record.run.status is ProbeRunStatus.FAILED
    assert record.pages == ()
    assert record.run.error_raw_snapshot_id is not None
    error_snapshot = FilesystemRawSnapshotStore(tmp_path / "raw").get_metadata(
        client.source_id,
        record.run.error_raw_snapshot_id,
    )
    assert error_snapshot.http_status == 200


def test_missing_continuation_token_keeps_valid_page_and_marks_partial(tmp_path: Path) -> None:
    client = FakeYandexClient(feed_responses=[(200, _page(1, has_next=True))])
    runner, probe_store = _runner(tmp_path, client)

    with pytest.raises(ProbeCollectionError, match="nextPageId"):
        runner.run_feed(ProbeContext(), page_limit=2)

    with probe_store.database.connect() as connection:
        run_id = str(connection.execute("SELECT id FROM probe_runs").fetchone()["id"])
    record = probe_store.get_run(run_id)
    assert record is not None
    assert record.run.status is ProbeRunStatus.PARTIAL
    assert len(record.pages) == 1
    assert record.run.error_raw_snapshot_id == record.pages[-1].raw_snapshot_id


def test_terminal_persistence_failure_does_not_mask_source_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeYandexClient(feed_responses=[(503, {"error": "temporarily unavailable"})])
    runner, probe_store = _runner(tmp_path, client)

    def fail_finish(*args: object, **kwargs: object) -> None:
        raise RuntimeError("terminal write failed")

    monkeypatch.setattr(probe_store, "finish_run", fail_finish)

    with pytest.raises(ProbeCollectionError, match="HTTP 503") as exc_info:
        runner.run_feed(ProbeContext(), page_limit=1)

    notes = getattr(exc_info.value, "__notes__", [])
    assert any("terminal write failed" in note for note in notes)


def test_search_runner_preserves_query_and_follows_same_cursor_chain(tmp_path: Path) -> None:
    client = FakeYandexClient(
        search_responses=[
            (200, _page(10, has_next=True, next_page_id="search-1", rtx_reqid="sreq-1")),
            (200, _page(11, has_next=False)),
        ]
    )
    runner, _ = _runner(tmp_path, client)

    result = runner.run_search(" merge ", ProbeContext(language="ru"), page_limit=2)

    assert result.record.run.query_text == "merge"
    assert result.record.run.status is ProbeRunStatus.COMPLETED
    assert client.search_calls == [
        ("merge", None, None),
        ("merge", "search-1", "sreq-1"),
    ]
