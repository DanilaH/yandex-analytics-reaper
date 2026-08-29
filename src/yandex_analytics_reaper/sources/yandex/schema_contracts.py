from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

from yandex_analytics_reaper.schema_drift import (
    FieldExpectation,
    JsonValueType,
    SchemaContract,
)
from yandex_analytics_reaper.storage import RawSnapshotMetadata

_NUMERIC = (JsonValueType.INTEGER, JsonValueType.NUMBER)
_VOLATILE_PAGINATION_KEYS = {"page_id", "rtx-reqid"}
_VOLATILE_SESSION_CONTEXT_KEYS = {"cookie_state_hash", "profile_age_days"}

_FEED_FIELDS = (
    FieldExpectation(
        path="$.feed",
        allowed_types=(JsonValueType.ARRAY,),
        required=True,
    ),
    FieldExpectation(
        path="$.totalGamesCount",
        allowed_types=(JsonValueType.INTEGER,),
        required=False,
    ),
    FieldExpectation(
        path="$.pageInfo",
        allowed_types=(JsonValueType.OBJECT,),
        required=False,
    ),
    FieldExpectation(
        path="$.feed[].items[].appID",
        allowed_types=(JsonValueType.INTEGER,),
        required=False,
    ),
    FieldExpectation(
        path="$.feed[].items[].gqRating",
        allowed_types=(JsonValueType.INTEGER,),
        required=False,
    ),
    FieldExpectation(
        path="$.feed[].items[].rating",
        allowed_types=_NUMERIC,
        required=False,
    ),
    FieldExpectation(
        path="$.feed[].items[].ratingCount",
        allowed_types=(JsonValueType.INTEGER,),
        required=False,
    ),
    FieldExpectation(
        path="$.feed[].widgets[].data.appID",
        allowed_types=(JsonValueType.INTEGER,),
        required=False,
    ),
    FieldExpectation(
        path="$.feed[].widgets[].data.gqRating",
        allowed_types=(JsonValueType.INTEGER,),
        required=False,
    ),
)

YANDEX_FEED_SCHEMA_V1 = SchemaContract(
    contract_id="yandex.catalogue.feed.v1",
    request_key="catalogue.feed",
    fields=_FEED_FIELDS,
)

YANDEX_SEARCH_SCHEMA_V1 = SchemaContract(
    contract_id="yandex.catalogue.search.v1",
    request_key="catalogue.search",
    fields=_FEED_FIELDS,
)

YANDEX_GET_GAMES_SCHEMA_V1 = SchemaContract(
    contract_id="yandex.catalogue.get_games.v1",
    request_key="catalogue.get_games",
    fields=(
        FieldExpectation(
            path="$.games",
            allowed_types=(JsonValueType.ARRAY,),
            required=True,
        ),
        FieldExpectation(
            path="$.games[].appID",
            allowed_types=(JsonValueType.INTEGER,),
            required=False,
            minimum_presence_ratio=1.0,
        ),
        FieldExpectation(
            path="$.games[].gqRating",
            allowed_types=(JsonValueType.INTEGER,),
            required=False,
        ),
        FieldExpectation(
            path="$.games[].rating",
            allowed_types=_NUMERIC,
            required=False,
        ),
        FieldExpectation(
            path="$.games[].ratingCount",
            allowed_types=(JsonValueType.INTEGER,),
            required=False,
        ),
        FieldExpectation(
            path="$.games[].firstPublished",
            allowed_types=(JsonValueType.INTEGER,),
            required=False,
        ),
        FieldExpectation(
            path="$.games[].minLoadTime",
            allowed_types=_NUMERIC,
            required=False,
        ),
    ),
)

_CONTRACTS = {
    item.request_key: item
    for item in (
        YANDEX_FEED_SCHEMA_V1,
        YANDEX_SEARCH_SCHEMA_V1,
        YANDEX_GET_GAMES_SCHEMA_V1,
    )
}


def schema_contract_for_request(request_key: str) -> SchemaContract | None:
    return _CONTRACTS.get(request_key)


def schema_comparison_scope_for_snapshot(metadata: RawSnapshotMetadata) -> str:
    """Build a stable scope for temporal drift comparisons within comparable requests."""

    context = _normalized_context(metadata.request_key, metadata.request_context)
    payload = json.dumps(
        {"request_key": metadata.request_key, "context": context},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    digest = hashlib.sha256(payload).hexdigest()[:20]
    return f"{metadata.request_key}:{digest}"


def _normalized_context(request_key: str, context: Mapping[str, object]) -> object:
    normalized = _canonical_value(context)
    if not isinstance(normalized, dict):
        return normalized

    if request_key in {"catalogue.feed", "catalogue.search"}:
        params = normalized.get("params")
        if isinstance(params, dict):
            page_kind = (
                "paged"
                if any(key in params for key in _VOLATILE_PAGINATION_KEYS)
                else "first"
            )
            normalized["params"] = {
                key: value
                for key, value in params.items()
                if key not in _VOLATILE_PAGINATION_KEYS
            }
            normalized["page_kind"] = page_kind

        probe_context = normalized.get("probe_context")
        if isinstance(probe_context, dict):
            stable_context = {
                key: value
                for key, value in probe_context.items()
                if key not in _VOLATILE_SESSION_CONTEXT_KEYS
            }
            if stable_context.get("session_instance_id") is None:
                stable_context.pop("session_instance_id", None)
            normalized["probe_context"] = stable_context

    if request_key == "catalogue.get_games":
        app_ids = normalized.get("app_ids")
        if isinstance(app_ids, list) and all(isinstance(item, int) for item in app_ids):
            normalized["app_ids"] = sorted(app_ids)

    return normalized


def _canonical_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): _canonical_value(child)
            for key, child in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, list):
        return [_canonical_value(child) for child in value]
    if isinstance(value, tuple):
        return [_canonical_value(child) for child in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"unsupported request-context value for schema scope: {type(value).__name__}")
