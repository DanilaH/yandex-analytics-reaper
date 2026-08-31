from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from yandex_analytics_reaper.domain import PlatformDeveloper, PlatformListing

from . import listing_states as listing_state_storage
from .identity import SQLiteIdentityStore, _timestamp as identity_timestamp
from .lineage import persist_lineage_in_connection
from .listing_histories import ListingHistoryWrite, SQLiteListingHistoryStore
from .listing_states import ListingStateWrite, SQLiteListingStateStore
from .metrics import MetricWrite, SQLiteMetricStore
from .sqlite import SQLiteDatabase


class SQLiteAtomicNormalizationStore:
    """Commit one normalized listing observation as one SQLite transaction."""

    def __init__(self, path: Path) -> None:
        self.database = SQLiteDatabase(path)
        self.identity_store = SQLiteIdentityStore(path)
        self.state_store = SQLiteListingStateStore(path)
        self.metric_store = SQLiteMetricStore(path)
        self.history_store = SQLiteListingHistoryStore(path)

    @property
    def path(self) -> Path:
        return self.database.path

    def persist(
        self,
        *,
        listing: PlatformListing,
        developer: PlatformDeveloper | None,
        observed_at: datetime,
        state: ListingStateWrite,
        metrics: Sequence[MetricWrite],
        history: ListingHistoryWrite,
    ) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
        state = ListingStateWrite.model_validate(state.model_dump(mode="python"))
        metrics = tuple(
            MetricWrite.model_validate(item.model_dump(mode="python")) for item in metrics
        )
        history = ListingHistoryWrite.model_validate(history.model_dump(mode="python"))
        self._validate_listing_scope(listing, state, metrics, history)

        with self.database.connect() as connection:
            self._persist_identity(connection, listing, developer, observed_at)
            state_id = self._persist_state(connection, state)
            metric_ids = tuple(
                self.metric_store._persist_metric(connection, item) for item in metrics
            )
            history_ids = self._persist_history(connection, history)
        return state_id, metric_ids, history_ids

    def _persist_identity(
        self,
        connection: sqlite3.Connection,
        listing: PlatformListing,
        developer: PlatformDeveloper | None,
        observed_at: datetime,
    ) -> None:
        seen_at = identity_timestamp(observed_at)
        self.identity_store._validate_developer_link(listing, developer)
        if developer is not None:
            self.identity_store._upsert_developer(connection, developer, seen_at)
        self.identity_store._upsert_listing(connection, listing, seen_at)
        if developer is not None:
            self.identity_store._record_assignment(
                connection,
                listing.id,
                developer.id,
                seen_at,
            )

    def _persist_state(
        self,
        connection: sqlite3.Connection,
        write: ListingStateWrite,
    ) -> str:
        observation_id = listing_state_storage._observation_id(write)
        self.state_store._persist_rows(connection, observation_id, write)
        persist_lineage_in_connection(connection, observation_id, write.lineage)
        stored = self.state_store._load_one(connection, observation_id)
        if stored is None:
            raise RuntimeError("listing-state observation was not persisted")
        expected = listing_state_storage._persisted_from_write(observation_id, write)
        if stored != expected:
            raise ValueError(f"conflicting listing-state observation {observation_id}")
        return observation_id

    def _persist_history(
        self,
        connection: sqlite3.Connection,
        write: ListingHistoryWrite,
    ) -> tuple[str, ...]:
        listing_id = write.observations[0].observation.platform_listing_id
        listing = connection.execute(
            "SELECT id FROM platform_listings WHERE id = ?",
            (listing_id,),
        ).fetchone()
        if listing is None:
            raise ValueError(f"listing {listing_id} must be persisted before histories")
        return tuple(
            self.history_store._persist_item(connection, write, item)
            for item in write.observations
        )

    @staticmethod
    def _validate_listing_scope(
        listing: PlatformListing,
        state: ListingStateWrite,
        metrics: Sequence[MetricWrite],
        history: ListingHistoryWrite,
    ) -> None:
        listing_id = listing.id
        if state.observation.platform_listing_id != listing_id:
            raise ValueError("atomic normalization state targets a different listing")
        if any(item.metric.platform_listing_id != listing_id for item in metrics):
            raise ValueError("atomic normalization metrics target a different listing")
        if any(
            item.observation.platform_listing_id != listing_id
            for item in history.observations
        ):
            raise ValueError("atomic normalization history targets a different listing")
