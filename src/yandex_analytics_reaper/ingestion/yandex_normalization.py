from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

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
    NormalizedListingHistories,
    YandexGameNormalizer,
    YandexListingHistoryNormalizer,
)
from yandex_analytics_reaper.sources.yandex.parsers import GameDetails, PlayPageData
from yandex_analytics_reaper.storage import (
    ListingHistoryObservationWrite,
    ListingHistoryWrite,
    MetricWrite,
    RawSnapshotMetadata,
    SQLiteIdentityStore,
    SQLiteListingHistoryStore,
    SQLiteMetricStore,
)

_SOURCE_ID = "yandex_public"
_GET_GAMES_REQUEST_KEY = "catalogue.get_games"
_GAME_PAGE_REQUEST_KEY = "game.page"


class PersistedYandexNormalization(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    platform_listing_id: str
    metric_observation_ids: tuple[str, ...]
    history_observation_ids: tuple[str, ...]


class YandexNormalizationPersistence:
    """Persist normalized current Yandex observations after immutable raw capture."""

    def __init__(self, database_path: Path) -> None:
        self.identity_store = SQLiteIdentityStore(database_path)
        self.metric_store = SQLiteMetricStore(database_path)
        self.history_store = SQLiteListingHistoryStore(database_path)
        self.game_normalizer = YandexGameNormalizer()
        self.history_normalizer = YandexListingHistoryNormalizer()

    def persist_details(
        self,
        details: GameDetails,
        metadata: RawSnapshotMetadata,
    ) -> PersistedYandexNormalization:
        _validate_metadata(metadata, _GET_GAMES_REQUEST_KEY)
        context = _context(metadata)
        normalized = self.game_normalizer.normalize_details(details, context)
        histories = self.history_normalizer.normalize_details(details, context)
        return self._persist(normalized, histories)

    def persist_play_page(
        self,
        page: PlayPageData,
        metadata: RawSnapshotMetadata,
    ) -> PersistedYandexNormalization:
        _validate_metadata(metadata, _GAME_PAGE_REQUEST_KEY)
        context = _context(metadata)
        normalized = self.game_normalizer.normalize_play_page(page, context)
        histories = self.history_normalizer.normalize_play_page(page, context)
        return self._persist(normalized, histories)

    def _persist(
        self,
        normalized: object,
        histories: NormalizedListingHistories,
    ) -> PersistedYandexNormalization:
        from yandex_analytics_reaper.normalizers import NormalizedListingObservation

        listing_observation = NormalizedListingObservation.model_validate(normalized)
        context = listing_observation.context
        evidence = _evidence(context)
        self.identity_store.persist_listing_identity(
            listing_observation.listing,
            listing_observation.developer,
            context.observed_at,
        )
        metric_ids = self.metric_store.persist_metrics(
            tuple(
                MetricWrite(
                    metric=item.metric,
                    evidence=evidence,
                    normalizer_name=type(self.game_normalizer).__name__,
                    normalizer_version=self.game_normalizer.version,
                    lineage=item.lineage,
                )
                for item in listing_observation.metrics
            )
        )
        history_items = tuple(
            ListingHistoryObservationWrite(
                observation=item.observation,
                lineage=item.lineage,
            )
            for item in (histories.update, histories.status, histories.media)
            if item is not None
        )
        history_ids = self.history_store.persist(
            ListingHistoryWrite(
                observations=history_items,
                evidence=evidence,
                normalizer_name=type(self.history_normalizer).__name__,
                normalizer_version=self.history_normalizer.version,
            )
        )
        history_listing_ids = {
            item.observation.platform_listing_id for item in history_items
        }
        if history_listing_ids != {listing_observation.listing.id}:
            raise RuntimeError("Yandex normalizers disagreed on platform listing identity")
        return PersistedYandexNormalization(
            platform_listing_id=listing_observation.listing.id,
            metric_observation_ids=metric_ids,
            history_observation_ids=history_ids,
        )


def _validate_metadata(metadata: RawSnapshotMetadata, request_key: str) -> None:
    if metadata.source_id != _SOURCE_ID:
        raise ValueError(f"Yandex normalization requires source_id={_SOURCE_ID}")
    if metadata.request_key != request_key:
        raise ValueError(f"Yandex normalization requires request_key={request_key}")
    if not 200 <= metadata.http_status < 300:
        raise ValueError("Yandex normalization requires a successful raw response")


def _context(metadata: RawSnapshotMetadata) -> NormalizationContext:
    return NormalizationContext(
        raw_snapshot_id=metadata.id,
        observed_at=metadata.retrieved_at,
        available_at=metadata.retrieved_at,
        retrieved_at=metadata.retrieved_at,
    )


def _evidence(context: NormalizationContext) -> EvidenceEnvelope:
    return EvidenceEnvelope(
        source_id=_SOURCE_ID,
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
