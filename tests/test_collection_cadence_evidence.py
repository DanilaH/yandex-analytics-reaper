from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from yandex_analytics_reaper.domain import (
    Platform,
    PlatformListing,
    QueryFamilyMember,
    QueryFamilyVersion,
    QueryVariantKind,
)
from yandex_analytics_reaper.experiments import (
    CadenceCheckpointInput,
    CollectionCadenceExperiment,
    CollectionCadenceManifest,
    CollectionCadencePlanDeclaration,
    CollectionCadencePlanFreezer,
)
from yandex_analytics_reaper.ingestion import YandexNormalizationPersistence
from yandex_analytics_reaper.sources.capabilities import CollectedResponse
from yandex_analytics_reaper.sources.yandex.parsers import YandexGetGamesParser
from yandex_analytics_reaper.storage import (
    FilesystemRawSnapshotStore,
    SQLiteIdentityStore,
    SQLiteQueryFamilyStore,
)


def test_cadence_report_records_exact_state_observation_and_raw_snapshot_ids(
    tmp_path: Path,
) -> None:
    raw_store = FilesystemRawSnapshotStore(tmp_path / "raw")
    database_path = tmp_path / "market.sqlite3"
    now = datetime.now(UTC)
    cohort_at = now - timedelta(days=1)
    identity_store = SQLiteIdentityStore(database_path)
    for app_id in range(1, 21):
        identity_store.persist_listing_identity(
            PlatformListing(
                id=f"yandex_games:{app_id}",
                platform=Platform.YANDEX_GAMES,
                external_app_id=str(app_id),
            ),
            None,
            cohort_at,
        )
    SQLiteQueryFamilyStore(database_path).persist(
        QueryFamilyVersion(
            family_id="merge-intent",
            version=1,
            label="Merge intent",
            source_id="yandex_public",
            language="ru",
            created_at=cohort_at,
            members=(
                QueryFamilyMember(query_text="merge", kind=QueryVariantKind.SEED),
            ),
        )
    )

    first_checkpoint = now + timedelta(days=1)
    checkpoint_times = tuple(
        first_checkpoint + timedelta(days=index) for index in range(28)
    )
    plan = CollectionCadencePlanFreezer(database_path).freeze(
        CollectionCadencePlanDeclaration(
            plan_id="cadence:merge:v1",
            listing_ids=tuple(f"yandex_games:{index}" for index in range(1, 21)),
            query_family_id="merge-intent",
            query_family_version=1,
            checkpoint_at=checkpoint_times,
        )
    )

    persistence = YandexNormalizationPersistence(database_path)
    raw_ids: list[str] = []
    checkpoints: list[CadenceCheckpointInput] = []
    for index, checkpoint_at in enumerate(plan.checkpoint_at):
        retrieved_at = checkpoint_at - timedelta(hours=1)
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
                checkpoint_at=checkpoint_at,
                feed_run_id=f"probe:missing-feed:{index}",
                search_run_ids=(f"probe:missing-search:{index}",),
            )
        )

    manifest = CollectionCadenceManifest(
        plan_id=plan.plan_id,
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
    assert report.plan_id == plan.plan_id
    assert report.plan_hash == plan.content_hash
    assert report.frozen_at == plan.frozen_at
    assert len(series.points) == 28
    assert tuple(point.raw_snapshot_ids[0] for point in series.points) == tuple(raw_ids)
    assert len({point.observation_id for point in series.points}) == 28
    assert all(raw_store.get_body("yandex_public", raw_id) for raw_id in raw_ids)
    assert any(
        item.series_id == "ranking:feed:depth1" for item in report.rejected_series
    )
    assert any(
        item.series_id.startswith("ranking:search:") for item in report.rejected_series
    )
    assert report.analysis.state_capability_reports[0].recommended_interval_days is None
