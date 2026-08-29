from __future__ import annotations

from yandex_analytics_reaper.schema_drift import (
    FieldExpectation,
    JsonValueType,
    SchemaContract,
)

_NUMERIC = (JsonValueType.INTEGER, JsonValueType.NUMBER)

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
            required=True,
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
