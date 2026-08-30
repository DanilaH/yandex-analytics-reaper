from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from yandex_analytics_reaper.domain import Platform, PlatformListing
from yandex_analytics_reaper.evidence import (
    EvidenceEnvelope,
    MeasurementKind,
    Provenance,
)
from yandex_analytics_reaper.normalizers import (
    NormalizationContext,
    YandexListingHistoryNormalizer,
)
from yandex_analytics_reaper.sources.yandex.parsers import PlayPageData
from yandex_analytics_reaper.storage import (
    ListingHistoryObservationWrite,
    ListingHistoryWrite,
    SQLiteIdentityStore,
    SQLiteListingHistoryStore,
)


def _fixture(
    path: Path,
) -> tuple[SQLiteListingHistoryStore, ListingHistoryWrite]:
    observed_at = datetime(2026, 8, 29, 13, 0, tzinfo=UTC)
    context = NormalizationContext(
        raw_snapshot_id="raw:provenance",
        observed_at=observed_at,
        available_at=observed_at,
        retrieved_at=observed_at + timedelta(seconds=1),
    )
    histories = YandexListingHistoryNormalizer().normalize_play_page(
        PlayPageData(app_id=1, app_version="3.0.0"),
        context,
    )
    observations = tuple(
        ListingHistoryObservationWrite(
            observation=item.observation,
            lineage=item.lineage,
        )
        for item in (histories.update, histories.status, histories.media)
        if item is not None
    )
    SQLiteIdentityStore(path).persist_listing_identity(
        PlatformListing(
            id="yandex_games:1",
            platform=Platform.YANDEX_GAMES,
            external_app_id="1",
        ),
        None,
        observed_at,
    )
    write = ListingHistoryWrite(
        observations=observations,
        evidence=EvidenceEnvelope(
            source_id="yandex_public",
            observed_at=observed_at,
            available_at=observed_at,
            retrieved_at=observed_at + timedelta(seconds=1),
            provenance=Provenance.FIRST_PARTY,
            measurement_kind=MeasurementKind.OBSERVED,
        ),
        normalizer_name=YandexListingHistoryNormalizer.__name__,
        normalizer_version=YandexListingHistoryNormalizer.version,
    )
    return SQLiteListingHistoryStore(path), write


def test_history_write_requires_normalizer_and_lineage_version_agreement(
    tmp_path: Path,
) -> None:
    _, write = _fixture(tmp_path / "market.sqlite3")

    with pytest.raises(ValidationError, match="transformation_version"):
        ListingHistoryWrite(
            observations=write.observations,
            evidence=write.evidence,
            normalizer_name=write.normalizer_name,
            normalizer_version="999",
        )


def test_history_write_rejects_duplicate_type_and_mixed_listing(tmp_path: Path) -> None:
    _, write = _fixture(tmp_path / "market.sqlite3")

    with pytest.raises(ValidationError, match="cannot repeat one observation type"):
        ListingHistoryWrite(
            observations=(*write.observations, write.observations[0]),
            evidence=write.evidence,
            normalizer_name=write.normalizer_name,
            normalizer_version=write.normalizer_version,
        )

    second = write.observations[1]
    mixed = second.model_copy(
        update={
            "observation": second.observation.model_copy(
                update={"platform_listing_id": "yandex_games:2"}
            )
        }
    )
    with pytest.raises(ValidationError, match="exactly one listing"):
        ListingHistoryWrite(
            observations=(write.observations[0], mixed),
            evidence=write.evidence,
            normalizer_name=write.normalizer_name,
            normalizer_version=write.normalizer_version,
        )


def test_store_revalidates_model_copy_before_persistence(tmp_path: Path) -> None:
    store, write = _fixture(tmp_path / "market.sqlite3")
    tampered = write.model_copy(update={"normalizer_version": "999"})

    with pytest.raises(ValidationError, match="transformation_version"):
        store.persist(tampered)


def test_history_reader_fails_closed_when_field_lineage_is_missing(tmp_path: Path) -> None:
    store, write = _fixture(tmp_path / "market.sqlite3")
    persisted_ids = store.persist(write)
    status_id = persisted_ids[1]

    with store.database.connect() as connection:
        connection.execute(
            "DELETE FROM observation_lineage WHERE normalized_observation_id = ?",
            (status_id,),
        )

    with pytest.raises(RuntimeError, match="missing field lineage"):
        store.status_history("yandex_games:1")


def test_history_reader_fails_closed_when_evidence_is_missing(tmp_path: Path) -> None:
    store, write = _fixture(tmp_path / "market.sqlite3")
    persisted_ids = store.persist(write)
    status_id = persisted_ids[1]

    with store.database.connect() as connection:
        connection.execute(
            "DELETE FROM listing_history_evidence WHERE observation_id = ?",
            (status_id,),
        )

    with pytest.raises(RuntimeError, match="missing evidence"):
        store.status_history("yandex_games:1")


def test_history_reader_fails_closed_on_lineage_normalizer_mismatch(
    tmp_path: Path,
) -> None:
    store, write = _fixture(tmp_path / "market.sqlite3")
    persisted_ids = store.persist(write)
    status_id = persisted_ids[1]

    with store.database.connect() as connection:
        connection.execute(
            """
            UPDATE observation_lineage
            SET transformation_version = '999'
            WHERE normalized_observation_id = ?
            """,
            (status_id,),
        )

    with pytest.raises(RuntimeError, match="lineage provenance is invalid"):
        store.status_history("yandex_games:1")
