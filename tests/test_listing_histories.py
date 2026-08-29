from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from yandex_analytics_reaper.domain import (
    ListingStatus,
    ListingStatusReason,
    Platform,
    PlatformListing,
)
from yandex_analytics_reaper.evidence import (
    CoverageStatus,
    EvidenceEnvelope,
    HistoricalAvailability,
    MeasurementKind,
    Provenance,
    RevisionStatus,
    SemanticConfidence,
)
from yandex_analytics_reaper.normalizers import (
    NormalizationContext,
    YandexListingHistoryNormalizer,
)
from yandex_analytics_reaper.sources.yandex.parsers import (
    PlayPageData,
    YandexGetGamesParser,
)
from yandex_analytics_reaper.storage import (
    ListingHistoryWrite,
    SQLiteIdentityStore,
    SQLiteLineageStore,
    SQLiteListingHistoryStore,
)


def _context(observed_at: datetime, raw_snapshot_id: str = "raw:history") -> NormalizationContext:
    return NormalizationContext(
        raw_snapshot_id=raw_snapshot_id,
        observed_at=observed_at,
        available_at=observed_at,
        retrieved_at=observed_at + timedelta(seconds=1),
    )


def _evidence(context: NormalizationContext) -> EvidenceEnvelope:
    return EvidenceEnvelope(
        source_id="yandex_public",
        observed_at=context.observed_at,
        available_at=context.available_at,
        retrieved_at=context.retrieved_at,
        provenance=Provenance.FIRST_PARTY,
        measurement_kind=MeasurementKind.OBSERVED,
        semantic_confidence=SemanticConfidence.HIGH,
        coverage_status=CoverageStatus.COMPLETE,
        historical_availability=HistoricalAvailability.POINT_IN_TIME,
        revision_status=RevisionStatus.IMMUTABLE,
    )


def _persist_listing(path: Path, observed_at: datetime) -> None:
    SQLiteIdentityStore(path).persist_listing_identity(
        PlatformListing(
            id="yandex_games:1",
            platform=Platform.YANDEX_GAMES,
            external_app_id="1",
        ),
        None,
        observed_at,
    )


def test_get_games_parser_v4_preserves_missing_vs_empty_media() -> None:
    parser = YandexGetGamesParser()
    payload = {
        "games": [
            {"appID": 1},
            {"appID": 2, "media": {}},
        ]
    }

    parsed = parser.parse(json.dumps(payload).encode())

    assert parser.version == "4"
    assert parsed.games[0].media is None
    assert parsed.games[1].media == {}


def test_history_normalizer_keeps_status_conservative_and_media_canonical() -> None:
    observed_at = datetime(2026, 8, 29, 10, 0, tzinfo=UTC)
    context = _context(observed_at)
    parser = YandexGetGamesParser()
    normalizer = YandexListingHistoryNormalizer()
    first = parser.parse(
        json.dumps({"games": [{"appID": 1, "media": {"b": 2, "a": 1}}]}).encode()
    ).games[0]
    second = parser.parse(
        json.dumps({"games": [{"appID": 1, "media": {"a": 1, "b": 2}}]}).encode()
    ).games[0]

    first_history = normalizer.normalize_details(first, context)
    second_history = normalizer.normalize_details(second, context)
    missing = normalizer.normalize_missing_catalogue_app(1, context)

    assert first_history.status is not None
    assert first_history.status.observation.status is ListingStatus.PUBLISHED
    assert first_history.media is not None
    assert second_history.media is not None
    assert first_history.media.observation.manifest_hash == second_history.media.observation.manifest_hash
    assert missing.status is not None
    assert missing.status.observation.status is ListingStatus.UNKNOWN
    assert missing.status.observation.reason is ListingStatusReason.REQUESTED_BUT_NOT_RETURNED
    assert missing.update is None
    assert missing.media is None


def test_empty_media_manifest_is_observed_but_missing_media_is_not() -> None:
    observed_at = datetime(2026, 8, 29, 10, 0, tzinfo=UTC)
    context = _context(observed_at)
    parser = YandexGetGamesParser()
    normalizer = YandexListingHistoryNormalizer()
    no_media, empty_media = parser.parse(
        json.dumps({"games": [{"appID": 1}, {"appID": 2, "media": {}}]}).encode()
    ).games

    missing_history = normalizer.normalize_details(no_media, context)
    empty_history = normalizer.normalize_details(empty_media, context)

    assert missing_history.media is None
    assert empty_history.media is not None
    assert empty_history.media.observation.manifest_hash == hashlib.sha256(b"{}").hexdigest()


def test_play_page_history_persists_idempotently_with_lineage_and_as_of(tmp_path: Path) -> None:
    observed_at = datetime(2026, 8, 29, 11, 0, tzinfo=UTC)
    context = _context(observed_at)
    histories = YandexListingHistoryNormalizer().normalize_play_page(
        PlayPageData(
            app_id=1,
            app_version="1.2.3",
            published_time=1_756_000_100,
        ),
        context,
    )
    path = tmp_path / "market.sqlite3"
    _persist_listing(path, observed_at)
    store = SQLiteListingHistoryStore(path)
    write = ListingHistoryWrite(
        histories=histories,
        evidence=_evidence(context),
        normalizer_name=YandexListingHistoryNormalizer.__name__,
        normalizer_version=YandexListingHistoryNormalizer.version,
    )

    first_ids = store.persist(write)
    second_ids = store.persist(write)

    assert first_ids == second_ids
    assert len(first_ids) == 2
    updates = store.update_history("yandex_games:1")
    statuses = store.status_history("yandex_games:1")
    assert len(updates) == 1
    assert updates[0].observation.app_version == "1.2.3"
    assert len(statuses) == 1
    assert statuses[0].observation.status is ListingStatus.PUBLISHED
    assert store.update_history(
        "yandex_games:1",
        as_of=observed_at - timedelta(microseconds=1),
    ) == ()
    assert store.update_history("yandex_games:1", as_of=observed_at) == updates

    lineage_store = SQLiteLineageStore(path)
    update_lineage = lineage_store.for_observation(first_ids[0])
    status_lineage = lineage_store.for_observation(first_ids[1])
    assert {item.source_field_path for item in update_lineage} == {
        "$.__playPageData__.gameData.appVersion",
        "$.__playPageData__.gameData.publishedTime",
    }
    assert status_lineage[0].source_field_path == "$.__playPageData__.gameData.appID"


def test_conflicting_value_under_same_history_identity_is_rejected(tmp_path: Path) -> None:
    observed_at = datetime(2026, 8, 29, 11, 0, tzinfo=UTC)
    context = _context(observed_at)
    histories = YandexListingHistoryNormalizer().normalize_play_page(
        PlayPageData(app_id=1, app_version="1.2.3"),
        context,
    )
    assert histories.update is not None
    path = tmp_path / "market.sqlite3"
    _persist_listing(path, observed_at)
    store = SQLiteListingHistoryStore(path)
    write = ListingHistoryWrite(
        histories=histories,
        evidence=_evidence(context),
        normalizer_name=YandexListingHistoryNormalizer.__name__,
        normalizer_version=YandexListingHistoryNormalizer.version,
    )
    store.persist(write)

    conflicting_update = histories.update.model_copy(
        update={
            "observation": histories.update.observation.model_copy(
                update={"app_version": "9.9.9"}
            )
        }
    )
    conflicting_histories = histories.model_copy(update={"update": conflicting_update})

    with pytest.raises(ValueError, match="conflicting listing update observation"):
        store.persist(write.model_copy(update={"histories": conflicting_histories}))


def test_lineage_conflict_rolls_back_whole_history_bundle(tmp_path: Path) -> None:
    observed_at = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
    context = _context(observed_at, "raw:rollback")
    histories = YandexListingHistoryNormalizer().normalize_play_page(
        PlayPageData(app_id=1, app_version="2.0.0"),
        context,
    )
    assert histories.status is not None
    duplicated_status = histories.status.model_copy(
        update={"lineage": histories.status.lineage + histories.status.lineage}
    )
    invalid_histories = histories.model_copy(update={"status": duplicated_status})
    path = tmp_path / "market.sqlite3"
    _persist_listing(path, observed_at)
    store = SQLiteListingHistoryStore(path)

    with pytest.raises(ValueError, match="duplicate lineage key"):
        store.persist(
            ListingHistoryWrite(
                histories=invalid_histories,
                evidence=_evidence(context),
                normalizer_name=YandexListingHistoryNormalizer.__name__,
                normalizer_version=YandexListingHistoryNormalizer.version,
            )
        )

    assert store.update_history("yandex_games:1") == ()
    assert store.status_history("yandex_games:1") == ()
