from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from yandex_analytics_reaper.cli import _observe_json_schema
from yandex_analytics_reaper.schema_drift import SQLiteSchemaDriftRegistry
from yandex_analytics_reaper.sources.capabilities import CollectedResponse
from yandex_analytics_reaper.storage import FilesystemRawSnapshotStore


def _response(body: bytes, retrieved_at: datetime) -> CollectedResponse:
    return CollectedResponse(
        source_id="yandex_public",
        request_key="catalogue.get_games",
        method="POST",
        url="https://yandex.ru/games/api/catalogue/v2/get_games",
        status_code=200,
        headers={"content-type": "application/json"},
        body=body,
        retrieved_at=retrieved_at,
        request_context={"app_ids": [1], "format": "long"},
    )


def test_breaking_schema_drift_stops_interpretation_after_raw_persistence(
    tmp_path: Path,
) -> None:
    raw_store = FilesystemRawSnapshotStore(tmp_path / "raw")
    response = _response(
        json.dumps({"unexpected": []}).encode(),
        datetime(2026, 8, 29, 8, 0, tzinfo=UTC),
    )
    metadata = raw_store.persist(response)

    with pytest.raises(SystemExit, match="breaking source-schema drift"):
        _observe_json_schema(raw_store, metadata, response)

    assert (raw_store.root / metadata.content_path).read_bytes() == response.body
    analyses = SQLiteSchemaDriftRegistry(tmp_path / "market.sqlite3").analyses_for_snapshot(
        metadata.id
    )
    assert len(analyses) == 1
    assert analyses[0].events


def test_informational_schema_drift_does_not_block_probe(tmp_path: Path) -> None:
    raw_store = FilesystemRawSnapshotStore(tmp_path / "raw")
    first_time = datetime(2026, 8, 29, 8, 0, tzinfo=UTC)
    first = _response(json.dumps({"games": [{"appID": 1}]}).encode(), first_time)
    first_metadata = raw_store.persist(first)
    _observe_json_schema(raw_store, first_metadata, first)

    second = _response(
        json.dumps({"games": [{"appID": 1, "newOptional": "x"}]}).encode(),
        first_time + timedelta(hours=1),
    )
    second_metadata = raw_store.persist(second)

    _observe_json_schema(raw_store, second_metadata, second)
