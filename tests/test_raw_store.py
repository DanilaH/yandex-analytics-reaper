from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from yandex_analytics_reaper.sources.capabilities import CollectedResponse
from yandex_analytics_reaper.storage.raw import FilesystemRawSnapshotStore


def _response() -> CollectedResponse:
    return CollectedResponse(
        source_id="fixture",
        request_key="test.json",
        method="GET",
        url="https://example.test/data",
        status_code=200,
        headers={"content-type": "application/json"},
        body=b'{"game":{"appID":1,"title":"A"}}',
        retrieved_at=datetime(2026, 8, 28, 12, 0, tzinfo=UTC),
        request_context={
            "query": "merge",
            "Authorization": "Bearer secret",
            "nested": {"csrf_token": "secret", "safe": "ok"},
        },
    )


def test_raw_store_persists_exact_body_and_redacts_metadata(tmp_path: Path) -> None:
    store = FilesystemRawSnapshotStore(tmp_path)
    metadata = store.persist(_response())

    body_path = tmp_path / metadata.content_path
    meta_path = tmp_path / metadata.metadata_path

    assert body_path.read_bytes() == _response().body
    saved = json.loads(meta_path.read_text(encoding="utf-8"))
    assert saved["request_context"]["Authorization"] == "<redacted>"
    assert saved["request_context"]["nested"]["csrf_token"] == "<redacted>"
    assert saved["request_context"]["nested"]["safe"] == "ok"
    assert metadata.schema_hash is not None


def test_raw_store_is_append_only(tmp_path: Path) -> None:
    store = FilesystemRawSnapshotStore(tmp_path)
    first = store.persist(_response())
    second = store.persist(_response())

    assert first.id != second.id
    assert (tmp_path / first.content_path).exists()
    assert (tmp_path / second.content_path).exists()
