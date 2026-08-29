from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from yandex_analytics_reaper.sources.capabilities import CollectedResponse
from yandex_analytics_reaper.storage.raw import FilesystemRawSnapshotStore


def _response(*, source_id: str = "fixture") -> CollectedResponse:
    return CollectedResponse(
        source_id=source_id,
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
            "items": [{"Authorization": "also-secret", "safe": "list-ok"}],
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
    assert saved["request_context"]["items"][0]["Authorization"] == "<redacted>"
    assert saved["request_context"]["items"][0]["safe"] == "list-ok"
    assert saved["method"] == "GET"
    assert saved["url"] == "https://example.test/data"
    assert metadata.schema_hash is not None


def test_raw_store_resolves_persisted_metadata_by_source_and_snapshot_id(tmp_path: Path) -> None:
    store = FilesystemRawSnapshotStore(tmp_path)
    metadata = store.persist(_response())

    resolved = store.get_metadata(metadata.source_id, metadata.id)

    assert resolved == metadata
    assert (tmp_path / resolved.content_path).read_bytes() == _response().body


def test_raw_store_rejects_invalid_or_missing_snapshot_identity(tmp_path: Path) -> None:
    store = FilesystemRawSnapshotStore(tmp_path)

    with pytest.raises(ValueError, match="expected generated format"):
        store.get_metadata("fixture", "bad-id")

    with pytest.raises(FileNotFoundError, match="not found"):
        store.get_metadata("fixture", "20260828T120000000000Z-0000000000")


def test_raw_store_rejects_unsafe_path_components(tmp_path: Path) -> None:
    store = FilesystemRawSnapshotStore(tmp_path)

    with pytest.raises(ValueError, match="source_id"):
        store.persist(_response(source_id="../escape"))

    with pytest.raises(ValueError, match="source_id"):
        store.get_metadata("../escape", "20260828T120000000000Z-0000000000")

    with pytest.raises(ValueError, match="expected generated format"):
        store.get_metadata("fixture", "20260828T120000000000Z-../../escape")


def test_raw_store_is_append_only(tmp_path: Path) -> None:
    store = FilesystemRawSnapshotStore(tmp_path)
    first = store.persist(_response())
    second = store.persist(_response())

    assert first.id != second.id
    assert (tmp_path / first.content_path).exists()
    assert (tmp_path / second.content_path).exists()
