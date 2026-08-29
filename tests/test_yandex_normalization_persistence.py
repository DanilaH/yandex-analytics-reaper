from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from yandex_analytics_reaper.domain import GameMetricName, ListingStatusReason
from yandex_analytics_reaper.ingestion import YandexNormalizationPersistence
from yandex_analytics_reaper.sources.capabilities import CollectedResponse
from yandex_analytics_reaper.sources.yandex.parsers import (
    YandexGetGamesParser,
    YandexPlayPageParser,
)
from yandex_analytics_reaper.storage import (
    FilesystemRawSnapshotStore,
    SQLiteLineageStore,
    SQLiteListingHistoryStore,
    SQLiteListingStateStore,
    SQLiteMetricStore,
)


def _response(
    *,
    request_key: str,
    body: bytes,
    retrieved_at: datetime,
    content_type: str,
) -> CollectedResponse:
    return CollectedResponse(
        source_id="yandex_public",
        request_key=request_key,
        method="GET" if request_key == "game.page" else "POST",
        url="https://yandex.test/source",
        status_code=200,
        headers={"content-type": content_type},
        body=body,
        retrieved_at=retrieved_at,
        request_context={},
    )


def test_get_games_normalization_persists_state_metrics_histories_and_raw_lineage(
    tmp_path: Path,
) -> None:
    retrieved_at = datetime(2026, 8, 29, 10, 0, tzinfo=UTC)
    body = json.dumps(
        {
            "games": [
                {
                    "appID": 438560,
                    "title": "Example Merge",
                    "developer": {"id": 77, "name": "Example Dev"},
                    "gqRating": 86,
                    "ratingCount": 6,
                    "features": {
                        "languages": ["ru", "en"],
                        "platforms": ["desktop", "mobile"],
                    },
                    "extraFeatures": {"leaderboards": False},
                    "media": {"cover": "one"},
                }
            ]
        }
    ).encode()
    raw_store = FilesystemRawSnapshotStore(tmp_path / "raw")
    metadata = raw_store.persist(
        _response(
            request_key="catalogue.get_games",
            body=body,
            retrieved_at=retrieved_at,
            content_type="application/json",
        )
    )
    details = YandexGetGamesParser().parse(body).games[0]
    database_path = tmp_path / "market.sqlite3"
    persistence = YandexNormalizationPersistence(database_path)

    first = persistence.persist_details(details, metadata)
    second = persistence.persist_details(details, metadata)

    assert first == second
    assert first.platform_listing_id == "yandex_games:438560"
    assert first.listing_state_observation_id.startswith("state:")
    assert len(first.metric_observation_ids) == 2
    assert len(first.history_observation_ids) == 2

    state_store = SQLiteListingStateStore(database_path)
    states = state_store.states_for_raw_snapshots(
        (metadata.id,),
        listing_ids=(first.platform_listing_id,),
    )
    assert len(states) == 1
    assert states[0].observation_id == first.listing_state_observation_id
    assert states[0].observation.title == "Example Merge"
    assert states[0].observation.developer_id == "yandex_games:77"
    assert states[0].observation.languages == ("ru", "en")
    assert states[0].observation.leaderboards is False

    metric_store = SQLiteMetricStore(database_path)
    rating = metric_store.metric_history(
        first.platform_listing_id,
        GameMetricName.YANDEX_GAMES_RATING,
    )
    rating_count = metric_store.metric_history(
        first.platform_listing_id,
        GameMetricName.RATING_COUNT,
    )
    assert rating[0].metric.value == 86
    assert rating_count[0].metric.value == 6

    history_store = SQLiteListingHistoryStore(database_path)
    statuses = history_store.status_history(first.platform_listing_id)
    media = history_store.media_history(first.platform_listing_id)
    assert (
        statuses[0].observation.reason
        is ListingStatusReason.OBSERVED_IN_CATALOGUE_METADATA
    )
    assert len(media[0].observation.manifest_hash) == 64

    lineage_store = SQLiteLineageStore(database_path)
    observation_ids = (
        first.listing_state_observation_id,
        *first.metric_observation_ids,
        *first.history_observation_ids,
    )
    for observation_id in observation_ids:
        lineage = lineage_store.for_observation(observation_id)
        assert lineage
        assert {item.raw_snapshot_id for item in lineage} == {metadata.id}
        resolved = raw_store.get_metadata("yandex_public", metadata.id)
        assert resolved.content_hash == metadata.content_hash
        assert raw_store.get_body("yandex_public", metadata.id) == body


def test_play_page_normalization_persists_state_and_update_from_same_raw_snapshot(
    tmp_path: Path,
) -> None:
    retrieved_at = datetime(2026, 8, 29, 11, 0, tzinfo=UTC)
    payload = {
        "gameData": {
            "appID": 438560,
            "appVersion": "1.2.3",
            "publishedTime": 1_756_000_100,
            "gqRating": 86,
            "extraFeatures": {"hasProducts": False},
            "advUsedBlocks": {"fullscreen": False},
        }
    }
    body = (
        '<html><script id="__playPageData__" type="application/json">'
        + json.dumps(payload)
        + "</script></html>"
    ).encode()
    raw_store = FilesystemRawSnapshotStore(tmp_path / "raw")
    metadata = raw_store.persist(
        _response(
            request_key="game.page",
            body=body,
            retrieved_at=retrieved_at,
            content_type="text/html",
        )
    )
    page = YandexPlayPageParser().parse(body)
    database_path = tmp_path / "market.sqlite3"

    persisted = YandexNormalizationPersistence(database_path).persist_play_page(
        page,
        metadata,
    )

    states = SQLiteListingStateStore(database_path).states_for_raw_snapshots(
        (metadata.id,),
        listing_ids=(persisted.platform_listing_id,),
    )
    assert len(states) == 1
    assert states[0].observation.app_version == "1.2.3"
    assert states[0].observation.has_products is False
    assert states[0].observation.fullscreen_ads is False

    updates = SQLiteListingHistoryStore(database_path).update_history(
        persisted.platform_listing_id
    )
    assert len(updates) == 1
    assert updates[0].observation.app_version == "1.2.3"
    assert updates[0].evidence.retrieved_at == retrieved_at
    update_lineage = SQLiteLineageStore(database_path).for_observation(
        updates[0].observation_id
    )
    assert {item.raw_snapshot_id for item in update_lineage} == {metadata.id}
