from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Mapping, Sequence

import httpx

from yandex_analytics_reaper.domain.models import ProbeContext
from yandex_analytics_reaper.sources.capabilities import CollectedResponse


class YandexPublicClient:
    """Small explicit client for currently observed Yandex Games frontend endpoints."""

    source_id = "yandex_public"

    def __init__(
        self,
        *,
        base_url: str = "https://yandex.ru/games",
        timeout_seconds: float = 30.0,
        user_agent: str = "YandexAnalyticsReaper/0.1 (+private-research)",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            timeout=timeout_seconds,
            follow_redirects=True,
            headers={
                "User-Agent": user_agent,
                "Accept-Language": "ru,en-US;q=0.8,en;q=0.7",
            },
        )

    def __enter__(self) -> "YandexPublicClient":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def collect_feed(
        self,
        context: ProbeContext,
        *,
        count: int = 20,
        page_id: str | None = None,
        rtx_reqid: str | None = None,
    ) -> CollectedResponse:
        if not 1 <= count <= 100:
            raise ValueError("count must be between 1 and 100")
        params: dict[str, str | int] = {
            "games_count": count,
            "with_promos": "false",
            "lang": context.language,
            "device-type": context.device_type,
            "platform": context.platform,
        }
        if page_id:
            params["page_id"] = page_id
        if rtx_reqid:
            params["rtx-reqid"] = rtx_reqid
        return self._request(
            "GET",
            f"{self.base_url}/api/catalogue/v2/feed/",
            request_key="catalogue.feed",
            params=params,
            context={"probe_context": context.model_dump(mode="json"), "params": params},
        )

    def collect_search(
        self,
        query: str,
        context: ProbeContext,
        *,
        page_id: str | None = None,
        rtx_reqid: str | None = None,
    ) -> CollectedResponse:
        if not query.strip():
            raise ValueError("query cannot be blank")
        params: dict[str, str] = {"query": query.strip(), "lang": context.language}
        if page_id:
            params["page_id"] = page_id
        if rtx_reqid:
            params["rtx-reqid"] = rtx_reqid
        return self._request(
            "GET",
            f"{self.base_url}/api/catalogue/v2/search",
            request_key="catalogue.search",
            params=params,
            context={
                "probe_context": context.model_dump(mode="json"),
                "query": query.strip(),
                "params": params,
            },
        )

    def collect_games(self, app_ids: Sequence[int]) -> CollectedResponse:
        ids = list(dict.fromkeys(app_ids))
        if not ids:
            raise ValueError("app_ids cannot be empty")
        if len(ids) > 100:
            raise ValueError("collect_games accepts at most 100 app IDs per request")
        payload = {"appIDs": ids, "format": "long"}
        return self._request(
            "POST",
            f"{self.base_url}/api/catalogue/v2/get_games",
            request_key="catalogue.get_games",
            json_body=payload,
            context={"app_ids": ids, "format": "long"},
        )

    def collect_game_page(self, app_id: int) -> CollectedResponse:
        return self._request(
            "GET",
            f"{self.base_url}/app/{app_id}",
            request_key="game.page",
            context={"app_id": app_id},
            headers={"Accept": "text/html,application/xhtml+xml"},
        )

    def _request(
        self,
        method: str,
        url: str,
        *,
        request_key: str,
        context: Mapping[str, object],
        params: Mapping[str, str | int] | None = None,
        json_body: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> CollectedResponse:
        response = self._client.request(
            method,
            url,
            params=params,
            json=json_body,
            headers=headers,
        )
        return CollectedResponse(
            source_id=self.source_id,
            request_key=request_key,
            method=method,
            url=str(response.url),
            status_code=response.status_code,
            headers=dict(response.headers),
            body=response.content,
            retrieved_at=datetime.now(UTC),
            request_context=dict(context),
        )
