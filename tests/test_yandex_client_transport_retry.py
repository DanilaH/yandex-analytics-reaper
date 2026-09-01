from __future__ import annotations

import httpx
import pytest

from yandex_analytics_reaper.sources.yandex.client import (
    YandexPublicClient,
    YandexTransientProtocolError,
)


class _RemoteProtocolFailureClient:
    def request(self, method: str, url: str, **_: object) -> httpx.Response:
        request = httpx.Request(method, url)
        raise httpx.RemoteProtocolError(
            "peer closed connection without sending complete message body",
            request=request,
        )


def test_remote_protocol_error_is_normalized_for_runner_retry() -> None:
    client = YandexPublicClient.__new__(YandexPublicClient)
    client._client = _RemoteProtocolFailureClient()  # type: ignore[assignment]

    with pytest.raises(YandexTransientProtocolError) as exc_info:
        client._request(
            "GET",
            "https://yandex.ru/games/api/catalogue/v2/search",
            request_key="catalogue.search",
            context={"query": "display collection"},
        )

    assert isinstance(exc_info.value, httpx.ConnectError)
    assert isinstance(exc_info.value.__cause__, httpx.RemoteProtocolError)
