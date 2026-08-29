from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from yandex_analytics_reaper.schema_drift import (
    DriftKind,
    FieldExpectation,
    JsonValueType,
    SQLiteSchemaDriftRegistry,
    SchemaContract,
)
from yandex_analytics_reaper.sources.yandex.schema_contracts import (
    YANDEX_GET_GAMES_SCHEMA_V1,
    schema_comparison_scope_for_snapshot,
)
from yandex_analytics_reaper.storage import RawSnapshotMetadata


def _metadata(
    *,
    request_key: str,
    request_context: dict[str, object],
    body: bytes = b"{}",
    suffix: str = "scope",
) -> RawSnapshotMetadata:
    instant = datetime(2026, 8, 29, 6, 0, tzinfo=UTC)
    snapshot_id = f"{instant:%Y%m%dT%H%M%S%fZ}-{suffix:0<10}"[:38]
    return RawSnapshotMetadata(
        id=snapshot_id,
        source_id="yandex_public",
        retrieved_at=instant,
        request_key=request_key,
        method="GET",
        url="https://yandex.ru/games/test",
        request_context=request_context,
        content_path=f"raw/{snapshot_id}.json",
        metadata_path=f"raw/{snapshot_id}.metadata.json",
        content_hash=hashlib.sha256(body).hexdigest(),
        http_status=200,
        content_type="application/json",
        schema_hash=None,
    )


def test_get_games_contract_flags_app_id_missing_when_game_objects_exist(
    tmp_path: Path,
) -> None:
    body = json.dumps({"games": [{"title": "Missing ID"}]}).encode()
    metadata = _metadata(
        request_key="catalogue.get_games",
        request_context={"app_ids": [1], "format": "long"},
        body=body,
        suffix="missing-id",
    )
    registry = SQLiteSchemaDriftRegistry(tmp_path / "market.sqlite3")

    analysis = registry.observe_json(
        metadata,
        body,
        comparison_scope_id=schema_comparison_scope_for_snapshot(metadata),
        contract=YANDEX_GET_GAMES_SCHEMA_V1,
    )

    assert any(
        event.kind is DriftKind.REQUIRED_FIELD_MISSING
        and event.field_path == "$.games[].appID"
        for event in analysis.events
    )


def test_get_games_scope_normalizes_app_id_order() -> None:
    first = _metadata(
        request_key="catalogue.get_games",
        request_context={"app_ids": [3, 1, 2], "format": "long"},
        suffix="ids-a",
    )
    second = _metadata(
        request_key="catalogue.get_games",
        request_context={"app_ids": [2, 3, 1], "format": "long"},
        suffix="ids-b",
    )

    assert schema_comparison_scope_for_snapshot(first) == schema_comparison_scope_for_snapshot(
        second
    )


def test_search_scope_separates_query_and_probe_context() -> None:
    base_context: dict[str, object] = {
        "probe_context": {
            "language": "ru",
            "device_type": "desktop",
            "platform": "desktop_other",
            "session_profile": "clean_anonymous",
        },
        "query": "merge",
        "params": {"query": "merge", "lang": "ru"},
    }
    merge = _metadata(
        request_key="catalogue.search",
        request_context=base_context,
        suffix="merge",
    )
    obby = _metadata(
        request_key="catalogue.search",
        request_context={
            **base_context,
            "query": "obby",
            "params": {"query": "obby", "lang": "ru"},
        },
        suffix="obby",
    )
    mobile = _metadata(
        request_key="catalogue.search",
        request_context={
            **base_context,
            "probe_context": {
                **base_context["probe_context"],  # type: ignore[dict-item]
                "device_type": "mobile",
            },
        },
        suffix="mobile",
    )

    assert schema_comparison_scope_for_snapshot(merge) != schema_comparison_scope_for_snapshot(obby)
    assert schema_comparison_scope_for_snapshot(merge) != schema_comparison_scope_for_snapshot(mobile)


def test_feed_scope_ignores_token_value_but_preserves_page_kind() -> None:
    probe_context = {
        "language": "ru",
        "device_type": "desktop",
        "platform": "desktop_other",
        "session_profile": "clean_anonymous",
    }
    first = _metadata(
        request_key="catalogue.feed",
        request_context={
            "probe_context": probe_context,
            "params": {
                "games_count": 20,
                "with_promos": "false",
                "lang": "ru",
                "device-type": "desktop",
                "platform": "desktop_other",
            },
        },
        suffix="first",
    )
    paged_a = _metadata(
        request_key="catalogue.feed",
        request_context={
            "probe_context": probe_context,
            "params": {
                "games_count": 20,
                "with_promos": "false",
                "lang": "ru",
                "device-type": "desktop",
                "platform": "desktop_other",
                "page_id": "page-a",
                "rtx-reqid": "req-a",
            },
        },
        suffix="paged-a",
    )
    paged_b = _metadata(
        request_key="catalogue.feed",
        request_context={
            "probe_context": probe_context,
            "params": {
                "games_count": 20,
                "with_promos": "false",
                "lang": "ru",
                "device-type": "desktop",
                "platform": "desktop_other",
                "page_id": "page-b",
                "rtx-reqid": "req-b",
            },
        },
        suffix="paged-b",
    )

    assert schema_comparison_scope_for_snapshot(paged_a) == schema_comparison_scope_for_snapshot(
        paged_b
    )
    assert schema_comparison_scope_for_snapshot(first) != schema_comparison_scope_for_snapshot(
        paged_a
    )


def test_schema_contract_rejects_duplicate_field_paths() -> None:
    field = FieldExpectation(
        path="$.games",
        allowed_types=(JsonValueType.ARRAY,),
    )

    with pytest.raises(ValidationError, match="same field path"):
        SchemaContract(
            contract_id="duplicate.v1",
            request_key="duplicate",
            fields=(field, field),
        )
