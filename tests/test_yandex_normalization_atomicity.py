from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from yandex_analytics_reaper.domain import GameMetricName
from yandex_analytics_reaper.ingestion import YandexNormalizationPersistence
from yandex_analytics_reaper.sources.capabilities import CollectedResponse
from yandex_analytics_reaper.sources.yandex.parsers import YandexGetGamesParser
from yandex_analytics_reaper.storage import FilesystemRawSnapshotStore


def test_normalization_rolls_back_all_sqlite_writes_on_metric_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    retrieved_at = datetime(2026, 8, 31, 8, 0, tzinfo=UTC)
    body = json.dumps(
        {
            "games": [
                {
                    "appID": 438560,
                    "title": "Atomic Example",
                    "developer": {"id": 77, "name": "Example Dev"},
                    "gqRating": 86,
                    "ratingCount": 6,
                    "media": {"cover": "one"},
                }
            ]
        }
    ).encode()
    response = CollectedResponse(
        source_id="yandex_public",
        request_key="catalogue.get_games",
        method="POST",
        url="https://yandex.test/source",
        status_code=200,
        headers={"content-type": "application/json"},
        body=body,
        retrieved_at=retrieved_at,
        request_context={},
    )
    raw_store = FilesystemRawSnapshotStore(tmp_path / "raw")
    metadata = raw_store.persist(response)
    details = YandexGetGamesParser().parse(body).games[0]
    persistence = YandexNormalizationPersistence(tmp_path / "market.sqlite3")

    original_persist_metric = persistence.atomic_store.metric_store._persist_metric

    def fail_after_metric_write(connection: object, write: object) -> str:
        observation_id = original_persist_metric(connection, write)  # type: ignore[arg-type]
        raise RuntimeError(f"injected failure after {observation_id}")

    monkeypatch.setattr(
        persistence.atomic_store.metric_store,
        "_persist_metric",
        fail_after_metric_write,
    )

    with pytest.raises(RuntimeError, match="injected failure"):
        persistence.persist_details(details, metadata)

    listing_id = "yandex_games:438560"
    assert persistence.identity_store.get_listing(listing_id) is None
    assert persistence.state_store.state_history(listing_id) == ()
    assert (
        persistence.metric_store.metric_history(
            listing_id,
            GameMetricName.YANDEX_GAMES_RATING,
        )
        == ()
    )
    assert persistence.history_store.status_history(listing_id) == ()
    assert persistence.history_store.media_history(listing_id) == ()

    assert raw_store.get_metadata("yandex_public", metadata.id) == metadata
    assert raw_store.get_body("yandex_public", metadata.id) == body
