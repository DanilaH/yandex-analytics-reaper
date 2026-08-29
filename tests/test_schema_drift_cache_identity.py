from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from yandex_analytics_reaper.schema_drift import SQLiteSchemaDriftRegistry
from yandex_analytics_reaper.sources.yandex.schema_contracts import YANDEX_GET_GAMES_SCHEMA_V1
from yandex_analytics_reaper.storage import RawSnapshotMetadata


def _metadata(body: bytes) -> RawSnapshotMetadata:
    instant = datetime(2026, 8, 29, 7, 0, tzinfo=UTC)
    return RawSnapshotMetadata(
        id="20260829T070000000000Z-cache00001",
        source_id="yandex_public",
        retrieved_at=instant,
        request_key="catalogue.get_games",
        method="POST",
        url="https://yandex.ru/games/api/catalogue/v2/get_games",
        request_context={"app_ids": [1], "format": "long"},
        content_path="raw/body.json",
        metadata_path="raw/metadata.json",
        content_hash=hashlib.sha256(body).hexdigest(),
        http_status=200,
        content_type="application/json",
        schema_hash=None,
    )


def test_cached_analysis_rejects_same_snapshot_id_with_different_content_identity(
    tmp_path: Path,
) -> None:
    registry = SQLiteSchemaDriftRegistry(tmp_path / "market.sqlite3")
    original = json.dumps({"games": [{"appID": 1}]}).encode()
    original_metadata = _metadata(original)
    registry.observe_json(
        original_metadata,
        original,
        comparison_scope_id="catalogue.get_games:cache",
        contract=YANDEX_GET_GAMES_SCHEMA_V1,
    )

    replacement = json.dumps({"games": [{"appID": 1, "gqRating": 90}]}).encode()
    replacement_metadata = _metadata(replacement)

    with pytest.raises(ValueError, match="metadata conflicts"):
        registry.observe_json(
            replacement_metadata,
            replacement,
            comparison_scope_id="catalogue.get_games:cache",
            contract=YANDEX_GET_GAMES_SCHEMA_V1,
        )
