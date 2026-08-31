from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest

from yandex_analytics_reaper.ingestion import (
    RichMetadataCollectionError,
    YandexNormalizationPersistence,
    YandexRichMetadataCollector,
)
from yandex_analytics_reaper.schema_drift import SQLiteSchemaDriftRegistry
from yandex_analytics_reaper.sources.capabilities import CollectedResponse
from yandex_analytics_reaper.storage import FilesystemRawSnapshotStore


class FakeGamesClient:
    source_id = "yandex_public"

    def __init__(self, response: CollectedResponse) -> None:
        self.response = response
        self.requested: tuple[int, ...] | None = None

    def collect_games(self, app_ids: Sequence[int]) -> CollectedResponse:
        self.requested = tuple(app_ids)
        return self.response


def _response(*, status: int = 200) -> CollectedResponse:
    body = json.dumps(
        {
            "games": [
                {
                    "appID": 438560,
                    "title": "Example",
                    "gqRating": 86,
                    "rating": 4.3,
                    "ratingCount": 6,
                }
            ]
        }
    ).encode()
    return CollectedResponse(
        source_id="yandex_public",
        request_key="catalogue.get_games",
        method="POST",
        url="https://yandex.ru/games/api/catalogue/v2/get_games",
        status_code=status,
        headers={"content-type": "application/json"},
        body=body,
        retrieved_at=datetime(2026, 8, 31, tzinfo=UTC),
        request_context={"app_ids": [438560], "format": "long"},
    )


def _collector(tmp_path: Path, client: FakeGamesClient) -> YandexRichMetadataCollector:
    database_path = tmp_path / "market.sqlite3"
    return YandexRichMetadataCollector(
        client=client,
        raw_store=FilesystemRawSnapshotStore(tmp_path / "raw"),
        schema_registry=SQLiteSchemaDriftRegistry(database_path),
        persistence=YandexNormalizationPersistence(database_path),
    )


def test_rich_metadata_collector_persists_raw_before_normalization(tmp_path: Path) -> None:
    client = FakeGamesClient(_response())
    collector = _collector(tmp_path, client)

    result = collector.collect([438560])

    assert client.requested == (438560,)
    assert result.parsed_listing_ids == ("yandex_games:438560",)
    raw_store = FilesystemRawSnapshotStore(tmp_path / "raw")
    assert raw_store.get_body("yandex_public", result.raw_snapshot.id) == client.response.body


def test_rich_metadata_collector_preserves_non_2xx_raw(tmp_path: Path) -> None:
    client = FakeGamesClient(_response(status=503))
    collector = _collector(tmp_path, client)

    with pytest.raises(RichMetadataCollectionError, match="HTTP 503"):
        collector.collect([438560])

    metadata_files = list((tmp_path / "raw" / "yandex_public").rglob("metadata.json"))
    assert len(metadata_files) == 1
