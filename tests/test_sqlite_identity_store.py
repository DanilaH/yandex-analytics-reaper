from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from yandex_analytics_reaper.domain import Platform, PlatformDeveloper, PlatformListing
from yandex_analytics_reaper.storage import SQLiteIdentityStore


def _listing(
    *,
    developer_external_id: str | None = "10",
    listing_url: str | None = "https://yandex.ru/games/app/438560",
) -> PlatformListing:
    return PlatformListing(
        id="yandex_games:438560",
        platform=Platform.YANDEX_GAMES,
        external_app_id="438560",
        listing_url=listing_url,
        developer_external_id=developer_external_id,
        first_published_at=datetime(2025, 6, 11, 8, 12, tzinfo=UTC),
    )


def _developer(
    *,
    external_id: str = "10",
    name: str | None = "Example Dev",
) -> PlatformDeveloper:
    return PlatformDeveloper(
        id=f"yandex_games:{external_id}",
        platform=Platform.YANDEX_GAMES,
        external_developer_id=external_id,
        display_name=name,
    )


def test_store_persists_listing_developer_and_assignment(tmp_path: Path) -> None:
    store = SQLiteIdentityStore(tmp_path / "market.sqlite3")
    observed_at = datetime(2026, 8, 29, 0, 0, tzinfo=UTC)

    store.persist_listing_identity(_listing(), _developer(), observed_at)

    listing = store.get_listing("yandex_games:438560")
    developer = store.get_developer("yandex_games:10")

    assert listing is not None
    assert listing.external_app_id == "438560"
    assert listing.first_seen_at == observed_at
    assert listing.last_seen_at == observed_at
    assert listing.first_published_at == datetime(2025, 6, 11, 8, 12, tzinfo=UTC)
    assert developer is not None
    assert developer.display_name == "Example Dev"
    assert developer.first_seen_at == observed_at
    assert developer.last_seen_at == observed_at
    assert store.developer_assignments(listing.id) == ((developer.id, observed_at),)


def test_store_keeps_latest_metadata_when_older_backfill_arrives_later(tmp_path: Path) -> None:
    store = SQLiteIdentityStore(tmp_path / "market.sqlite3")
    later = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
    earlier = later - timedelta(days=2)

    store.persist_listing_identity(
        _listing(listing_url="https://yandex.ru/games/app/new"),
        _developer(name="New Name"),
        later,
    )
    store.persist_listing_identity(
        _listing(listing_url="https://yandex.ru/games/app/old"),
        _developer(name="Old Name"),
        earlier,
    )

    listing = store.get_listing("yandex_games:438560")
    developer = store.get_developer("yandex_games:10")

    assert listing is not None
    assert listing.first_seen_at == earlier
    assert listing.last_seen_at == later
    assert listing.listing_url == "https://yandex.ru/games/app/new"
    assert developer is not None
    assert developer.display_name == "New Name"
    assert developer.first_seen_at == earlier
    assert developer.last_seen_at == later
    assert store.developer_assignments(listing.id) == (
        (developer.id, earlier),
        (developer.id, later),
    )


def test_store_records_developer_reassignment_without_rewriting_history(tmp_path: Path) -> None:
    store = SQLiteIdentityStore(tmp_path / "market.sqlite3")
    first = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)
    second = first + timedelta(days=1)

    store.persist_listing_identity(_listing(), _developer(), first)
    reassigned_listing = _listing(developer_external_id="11")
    store.persist_listing_identity(reassigned_listing, _developer(external_id="11"), second)

    listing = store.get_listing(reassigned_listing.id)
    assert listing is not None
    assert listing.developer_external_id == "11"
    assert store.developer_assignments(reassigned_listing.id) == (
        ("yandex_games:10", first),
        ("yandex_games:11", second),
    )


def test_store_rolls_back_conflicting_assignment_at_same_observation_time(
    tmp_path: Path,
) -> None:
    store = SQLiteIdentityStore(tmp_path / "market.sqlite3")
    observed_at = datetime(2026, 8, 29, 0, 0, tzinfo=UTC)

    store.persist_listing_identity(_listing(), _developer(), observed_at)

    with pytest.raises(ValueError, match="conflicting developer assignment"):
        store.persist_listing_identity(
            _listing(developer_external_id="11"),
            _developer(external_id="11"),
            observed_at,
        )

    listing = store.get_listing("yandex_games:438560")
    assert listing is not None
    assert listing.developer_external_id == "10"
    assert store.get_developer("yandex_games:11") is None
    assert store.developer_assignments(listing.id) == (("yandex_games:10", observed_at),)


def test_store_requires_listing_developer_identity_to_match(tmp_path: Path) -> None:
    store = SQLiteIdentityStore(tmp_path / "market.sqlite3")
    observed_at = datetime(2026, 8, 29, 0, 0, tzinfo=UTC)

    with pytest.raises(ValueError, match="developer_external_id does not match"):
        store.persist_listing_identity(
            _listing(developer_external_id=None),
            _developer(),
            observed_at,
        )


def test_store_rejects_naive_observation_time(tmp_path: Path) -> None:
    store = SQLiteIdentityStore(tmp_path / "market.sqlite3")

    with pytest.raises(ValueError, match="timezone-aware"):
        store.persist_listing_identity(
            _listing(),
            _developer(),
            datetime(2026, 8, 29, 0, 0),
        )
