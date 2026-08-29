from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from yandex_analytics_reaper.domain import GameMetricName
from yandex_analytics_reaper.evidence import (
    CoverageStatus,
    EvidenceEnvelope,
    HistoricalAvailability,
    MeasurementKind,
    Provenance,
    RevisionStatus,
    SemanticConfidence,
)
from yandex_analytics_reaper.normalizers import NormalizationContext, YandexGameNormalizer
from yandex_analytics_reaper.sources.capabilities import CollectedResponse
from yandex_analytics_reaper.sources.yandex.parsers import YandexGetGamesParser
from yandex_analytics_reaper.storage import (
    FilesystemRawSnapshotStore,
    MetricWrite,
    SQLiteIdentityStore,
    SQLiteLineageStore,
    SQLiteMetricStore,
)


def test_get_games_metric_traces_back_to_exact_raw_snapshot_and_field(tmp_path: Path) -> None:
    payload = {
        "games": [
            {"appID": 111, "gqRating": 70},
            {
                "appID": 438560,
                "developer": {"id": 10, "name": "Dev"},
                "gqRating": 86,
                "rating": 4.3,
                "ratingCount": 6,
            },
        ]
    }
    observed_at = datetime(2026, 8, 29, 4, 0, tzinfo=UTC)
    retrieved_at = observed_at + timedelta(seconds=1)
    body = json.dumps(payload).encode()
    response = CollectedResponse(
        source_id="yandex_public",
        request_key="catalogue.get_games",
        method="POST",
        url="https://yandex.ru/games/api/catalogue/v2/get_games",
        status_code=200,
        headers={"content-type": "application/json"},
        body=body,
        retrieved_at=retrieved_at,
        request_context={"app_ids": [111, 438560], "format": "long"},
    )
    raw_store = FilesystemRawSnapshotStore(tmp_path / "raw")
    raw_metadata = raw_store.persist(response)

    details = YandexGetGamesParser().parse(response.body).games[1]
    normalized = YandexGameNormalizer().normalize_details(
        details,
        NormalizationContext(
            raw_snapshot_id=raw_metadata.id,
            observed_at=observed_at,
            available_at=observed_at,
            retrieved_at=retrieved_at,
        ),
    )

    path = tmp_path / "market.sqlite3"
    SQLiteIdentityStore(path).persist_listing_identity(
        normalized.listing,
        normalized.developer,
        observed_at,
    )

    metric_item = next(
        item
        for item in normalized.metrics
        if item.metric.metric_name is GameMetricName.YANDEX_GAMES_RATING
    )
    observation_id = SQLiteMetricStore(path).persist_metric(
        MetricWrite(
            metric=metric_item.metric,
            evidence=EvidenceEnvelope(
                source_id="yandex_public",
                observed_at=observed_at,
                available_at=observed_at,
                retrieved_at=retrieved_at,
                provenance=Provenance.FIRST_PARTY,
                measurement_kind=MeasurementKind.OBSERVED,
                semantic_confidence=SemanticConfidence.HIGH,
                coverage_status=CoverageStatus.COMPLETE,
                historical_availability=HistoricalAvailability.POINT_IN_TIME,
                revision_status=RevisionStatus.IMMUTABLE,
            ),
            normalizer_name=YandexGameNormalizer.__name__,
            normalizer_version=YandexGameNormalizer.version,
            lineage=metric_item.lineage,
        )
    )

    persisted_metric = SQLiteMetricStore(path).metric_history(
        normalized.listing.id,
        GameMetricName.YANDEX_GAMES_RATING,
    )[0]
    persisted_lineage = SQLiteLineageStore(path).for_observation(observation_id)
    resolved_raw = raw_store.get_metadata("yandex_public", persisted_lineage[0].raw_snapshot_id)

    assert persisted_metric.metric.value == 86
    assert persisted_metric.normalizer_version == YandexGameNormalizer.version
    assert len(persisted_lineage) == 1
    assert persisted_lineage[0].raw_snapshot_id == raw_metadata.id
    assert persisted_lineage[0].source_field_path == "$.games[1].gqRating"
    assert persisted_lineage[0].target_field_path == "game_metric_observations.value_numeric"
    assert resolved_raw == raw_metadata
    assert (raw_store.root / resolved_raw.content_path).read_bytes() == body
