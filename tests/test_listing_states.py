from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from yandex_analytics_reaper.domain import ListingStateObservation, Platform, PlatformListing
from yandex_analytics_reaper.evidence import (
    CoverageStatus,
    EvidenceEnvelope,
    FieldLineage,
    HistoricalAvailability,
    MeasurementKind,
    Provenance,
    RevisionStatus,
    SemanticConfidence,
)
from yandex_analytics_reaper.storage import (
    ListingStateWrite,
    SQLiteIdentityStore,
    SQLiteListingStateStore,
)

_BASE = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)


def _listing(listing_id: str = "yandex_games:10") -> PlatformListing:
    return PlatformListing(
        id=listing_id,
        platform=Platform.YANDEX_GAMES,
        external_app_id=listing_id.removeprefix("yandex_games:"),
    )


def _lineage(raw_id: str, *, target: str = "platform_listing_id") -> FieldLineage:
    sources = {
        "platform_listing_id": "appID",
        "developer_id": "developer.id",
        "developer_name": "developer.name",
        "first_published_at": "firstPublished",
    }
    source = sources.get(target, target)
    return FieldLineage(
        raw_snapshot_id=raw_id,
        source_field_path=f"$.games[0].{source}",
        target_field_path=f"listing_state_observations.{target}",
        transformation_name=f"YandexGameNormalizer.listing_state.{target}",
        transformation_version="4",
    )


def _write(
    *,
    raw_id: str = "raw:one",
    observed_at: datetime = _BASE,
    listing_id: str = "yandex_games:10",
    title: str = "Merge Lab",
) -> ListingStateWrite:
    return ListingStateWrite(
        observation=ListingStateObservation(
            platform_listing_id=listing_id,
            observed_at=observed_at,
            title=title,
            developer_id="yandex_games:dev-1",
            developer_name="Dev One",
            first_published_at=observed_at - timedelta(days=60),
            app_version="1.2.3",
            published_at=observed_at - timedelta(days=30),
            languages=("ru", "en"),
            supported_platforms=("desktop", "mobile"),
            orientation="any",
            cloud_save=True,
            leaderboards=False,
            purchases_enabled=True,
            has_products=False,
            rewarded_ads=True,
            fullscreen_ads=False,
            sticky_ads=False,
        ),
        evidence=EvidenceEnvelope(
            source_id="yandex_public",
            observed_at=observed_at,
            available_at=observed_at,
            retrieved_at=observed_at + timedelta(seconds=1),
            provenance=Provenance.FIRST_PARTY,
            measurement_kind=MeasurementKind.OBSERVED,
            semantic_confidence=SemanticConfidence.HIGH,
            coverage_status=CoverageStatus.COMPLETE,
            historical_availability=HistoricalAvailability.POINT_IN_TIME,
            revision_status=RevisionStatus.IMMUTABLE,
            lineage_refs=("raw-ref:b", "raw-ref:a"),
        ),
        normalizer_name="YandexGameNormalizer",
        normalizer_version="4",
        lineage=(
            _lineage(raw_id),
            _lineage(raw_id, target="title"),
            _lineage(raw_id, target="developer_name"),
            _lineage(raw_id, target="first_published_at"),
            _lineage(raw_id, target="leaderboards"),
        ),
    )


def _persist_listing(path: Path, listing_id: str = "yandex_games:10") -> None:
    SQLiteIdentityStore(path).persist_listing_identity(
        _listing(listing_id),
        None,
        _BASE - timedelta(minutes=1),
    )


def test_listing_state_store_round_trips_fields_evidence_and_lineage(tmp_path: Path) -> None:
    path = tmp_path / "market.sqlite3"
    _persist_listing(path)
    store = SQLiteListingStateStore(path)

    observation_id = store.persist(_write())
    history = store.state_history("yandex_games:10")

    assert len(history) == 1
    persisted = history[0]
    assert persisted.observation_id == observation_id
    assert persisted.observation.title == "Merge Lab"
    assert persisted.observation.developer_name == "Dev One"
    assert persisted.observation.first_published_at == _BASE - timedelta(days=60)
    assert persisted.observation.languages == ("ru", "en")
    assert persisted.observation.leaderboards is False
    assert persisted.observation.has_products is False
    assert persisted.evidence.lineage_refs == ("raw-ref:a", "raw-ref:b")
    assert {item.raw_snapshot_id for item in persisted.lineage} == {"raw:one"}
    assert persisted.normalizer_version == "4"


def test_listing_state_store_is_idempotent_and_rejects_conflict(tmp_path: Path) -> None:
    path = tmp_path / "market.sqlite3"
    _persist_listing(path)
    store = SQLiteListingStateStore(path)
    write = _write()

    first = store.persist(write)
    second = store.persist(write)
    assert first == second
    assert len(store.state_history("yandex_games:10")) == 1

    conflicting = write.model_copy(
        update={
            "observation": write.observation.model_copy(update={"title": "Different title"})
        }
    )
    with pytest.raises(ValueError, match="conflicting listing-state observation"):
        store.persist(conflicting)


def test_listing_state_store_orders_history_and_supports_as_of(tmp_path: Path) -> None:
    path = tmp_path / "market.sqlite3"
    _persist_listing(path)
    store = SQLiteListingStateStore(path)
    later = _BASE + timedelta(hours=2)

    store.persist(_write(raw_id="raw:later", observed_at=later, title="Later"))
    store.persist(_write(raw_id="raw:early", observed_at=_BASE, title="Earlier"))

    assert [item.observation.title for item in store.state_history("yandex_games:10")] == [
        "Earlier",
        "Later",
    ]
    as_of = store.state_history("yandex_games:10", as_of=_BASE + timedelta(minutes=1))
    assert [item.observation.title for item in as_of] == ["Earlier"]


def test_listing_state_store_reads_only_requested_raw_and_listings(tmp_path: Path) -> None:
    path = tmp_path / "market.sqlite3"
    _persist_listing(path, "yandex_games:10")
    _persist_listing(path, "yandex_games:20")
    store = SQLiteListingStateStore(path)

    store.persist(_write(raw_id="raw:a", listing_id="yandex_games:10", title="Ten"))
    store.persist(
        _write(
            raw_id="raw:b",
            observed_at=_BASE + timedelta(minutes=1),
            listing_id="yandex_games:20",
            title="Twenty",
        )
    )

    selected = store.states_for_raw_snapshots(
        ("raw:a", "raw:b"),
        listing_ids=("yandex_games:20",),
    )
    assert [item.observation.title for item in selected] == ["Twenty"]
    assert store.states_for_raw_snapshots(("raw:missing",)) == ()


def test_listing_state_store_requires_persisted_listing(tmp_path: Path) -> None:
    store = SQLiteListingStateStore(tmp_path / "market.sqlite3")
    with pytest.raises(ValueError, match="must be persisted before listing state"):
        store.persist(_write())


def test_listing_state_write_rejects_invalid_evidence_time_order() -> None:
    write = _write()
    invalid_evidence = write.evidence.model_copy(
        update={"retrieved_at": write.evidence.observed_at - timedelta(seconds=1)}
    )

    with pytest.raises(ValidationError, match="observed_at cannot be later than retrieved_at"):
        ListingStateWrite.model_validate(
            write.model_copy(update={"evidence": invalid_evidence}).model_dump()
        )


def test_listing_state_write_revalidates_model_copy_lineage() -> None:
    write = _write()
    bypassed = write.model_copy(update={"lineage": ()})

    with pytest.raises(ValidationError):
        ListingStateWrite.model_validate(bypassed.model_dump())
