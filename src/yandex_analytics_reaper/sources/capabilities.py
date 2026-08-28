from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from yandex_analytics_reaper.domain.models import ProbeContext


class SourceCapability(StrEnum):
    CATALOG_METADATA = "catalog_metadata"
    SEARCH_DISCOVERY = "search_discovery"
    RECOMMENDATION_EXPOSURE = "recommendation_exposure"
    HISTORICAL_METRICS = "historical_metrics"
    STATUS_HISTORY = "status_history"
    MEDIA = "media"
    TREND = "trend"


@dataclass(frozen=True, slots=True)
class CollectedResponse:
    """Exact source response plus safe request metadata, before parsing."""

    source_id: str
    request_key: str
    method: str
    url: str
    status_code: int
    headers: Mapping[str, str]
    body: bytes
    retrieved_at: datetime
    request_context: Mapping[str, object]


class CatalogMetadataProvider(Protocol):
    source_id: str

    def collect_games(self, app_ids: Sequence[int]) -> CollectedResponse: ...


class SearchDiscoveryProvider(Protocol):
    source_id: str

    def collect_search(
        self,
        query: str,
        context: ProbeContext,
        *,
        page_id: str | None = None,
        rtx_reqid: str | None = None,
    ) -> CollectedResponse: ...


class RecommendationExposureProvider(Protocol):
    source_id: str

    def collect_feed(
        self,
        context: ProbeContext,
        *,
        count: int = 20,
        page_id: str | None = None,
        rtx_reqid: str | None = None,
    ) -> CollectedResponse: ...
