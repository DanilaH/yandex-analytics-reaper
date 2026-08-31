from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from yandex_analytics_reaper.ingestion.yandex_normalization import YandexNormalizationPersistence
from yandex_analytics_reaper.schema_drift import DriftSeverity, SQLiteSchemaDriftRegistry
from yandex_analytics_reaper.sources.capabilities import CollectedResponse
from yandex_analytics_reaper.sources.yandex import YandexGetGamesParser
from yandex_analytics_reaper.sources.yandex.schema_contracts import (
    schema_comparison_scope_for_snapshot,
    schema_contract_for_request,
)
from yandex_analytics_reaper.storage import FilesystemRawSnapshotStore, RawSnapshotMetadata


class YandexRichMetadataClient(Protocol):
    source_id: str

    def collect_games(self, app_ids: Sequence[int]) -> CollectedResponse: ...


class RichMetadataCollectionError(RuntimeError):
    """Rich metadata could not be accepted without weakening raw-first semantics."""


@dataclass(frozen=True, slots=True)
class RichMetadataCollectionResult:
    raw_snapshot: RawSnapshotMetadata
    parsed_listing_ids: tuple[str, ...]


class YandexRichMetadataCollector:
    """Collect one get_games batch from raw capture through normalized persistence."""

    def __init__(
        self,
        *,
        client: YandexRichMetadataClient,
        raw_store: FilesystemRawSnapshotStore,
        schema_registry: SQLiteSchemaDriftRegistry,
        persistence: YandexNormalizationPersistence,
    ) -> None:
        self.client = client
        self.raw_store = raw_store
        self.schema_registry = schema_registry
        self.persistence = persistence

    def collect(self, app_ids: Sequence[int]) -> RichMetadataCollectionResult:
        response = self.client.collect_games(app_ids)
        metadata = self.raw_store.persist(response)
        if not 200 <= response.status_code < 300:
            raise RichMetadataCollectionError(
                f"source returned HTTP {response.status_code}; raw response was preserved"
            )

        analysis = self.schema_registry.observe_json(
            metadata,
            response.body,
            comparison_scope_id=schema_comparison_scope_for_snapshot(metadata),
            contract=schema_contract_for_request(metadata.request_key),
        )
        if any(event.severity is DriftSeverity.BREAKING for event in analysis.events):
            raise RichMetadataCollectionError(
                "breaking source-schema drift detected; raw response and analysis were preserved"
            )

        parser = YandexGetGamesParser()
        try:
            parsed = parser.parse(response.body)
        except ValueError as exc:
            self.schema_registry.record_parser_failure(
                metadata,
                comparison_scope_id=schema_comparison_scope_for_snapshot(metadata),
                parser_name=type(parser).__name__,
                parser_version=parser.version,
                error=str(exc),
            )
            raise RichMetadataCollectionError(str(exc)) from exc

        for game in parsed.games:
            self.persistence.persist_details(game, metadata)

        return RichMetadataCollectionResult(
            raw_snapshot=metadata,
            parsed_listing_ids=tuple(f"yandex_games:{game.app_id}" for game in parsed.games),
        )
