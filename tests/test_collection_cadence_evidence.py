from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from yandex_analytics_reaper.domain import (
    QueryFamilyMember,
    QueryFamilyVersion,
    QueryVariantKind,
)
from yandex_analytics_reaper.experiments import (
    CadenceCheckpointInput,
    CollectionCadenceExperiment,
    CollectionCadenceManifest,
)
from yandex_analytics_reaper.ingestion import YandexNormalizationPersistence
from yandex_analytics_reaper.sources.capabilities import CollectedResponse
from yandex_analytics_reaper.sources.yandex.parsers import YandexGetGamesParser
from yandex_analytics_reaper.storage import (
    FilesystemRawSnapshotStore,
    SQLiteQueryFamilyStore,
)


def test_cadence_report_records_exact_state_observation_and_raw_snapshot_ids(
    tmp_path: Path,
) -> None:
    raw_store = FilesystemRawSnapshotStore(tmp_path / "raw")
    database_path = tmp_path / "market.sqlite3"
    SQLiteQueryFamilyStore(database_path).persist(
        QueryFamilyVersion(
            family_id="merge-intent",
            version=1,
            label="Merge intent",
            source_id="yandex_public",
            language="ru",
            created_at=datetime(2026, 8, 31, 8, 0, tzinfo=UTC),
            members=(
                QueryFamilyMember(
                    query_text="merge",
                    kind=QueryVariantKind.SEED,
                ),
            ),
        )
    )

    persistence = YandexNormalizationPersistence(database_path)
    raw_ids: list[str] = []
    checkpoints: list[CadenceCheckpointInput] = []
    for index in range(28):
        retrieved_at = datetime(2026, 9, 1, 11, 0, tzinfo=UTC) + timedelta(days=index)
        body = json.dumps(
            {
                "games": [
                    {
                        "appID": 1,
                        "gqRating": 80 + (index % 2),
                    }
                ]
            }
        ).encode()
        metadata = raw_store.persist(
            CollectedResponse(
                source_id="yandex_public",
                request_key="catalogue.get_games",
                method="POST",
                url="https://yandex.test/games/api/catalogue/v2/get_games",
                status_code=200,
                headers={"content-type": "application/json"},
                body=body,
                retrieved_at=retrieved_at,
                request_context={"app_ids": [1], "format": "long"},
            )
        )
        details = YandexGetGamesParser().parse(body).games[0]
        persistence.persist_details(details, metadata)
        raw_ids.append(metadata.id)
        checkpoints.append(
            CadenceCheckpointInput(
                checkpoint_at=retrieved_at + timedelta(hours=1),
                feed_run_id=f"probe:missing-feed:{index}",
                search_run_ids=(f"probe:missing-search:{index}",),
            )
        )

    manifest = CollectionCadenceManifest(
        frozen_at=datetime(2026, 9, 1, 9, 0, tzinfo=UTC),
        listing_ids=tuple(f"yandex_games:{index}" for index in range(1, 21)),
        query_family_id="merge-intent",
        query_family_version=1,
        checkpoints=tuple(checkpoints),
    )

    report = CollectionCadenceExperiment(
        raw_store=raw_store,
        database_path=database_path,
    ).analyze(manifest)

    series = next(
        item
        for item in report.state_evidence
        if item.series_id == "state:yandex_games:1:yandex_games_rating"
    )
    assert len(series.points) == 28
    assert tuple(point.raw_snapshot_ids[0] for point in series.points) == tuple(raw_ids)
    assert len({point.observation_id for point in series.points}) == 28
    assert all(
        raw_store.get_body("yandex_public", raw_id)
        for raw_id in raw_ids
    )
    assert any(
        item.series_id == "ranking:feed:depth1"
        for item in report.rejected_series
    )
    assert any(
        item.series_id.startswith("ranking:search:")
        for item in report.rejected_series
    )
    assert report.analysis.state_capability_reports[0].recommended_interval_days is None
