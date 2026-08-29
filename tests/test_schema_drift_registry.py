from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from yandex_analytics_reaper.schema_drift import (
    DriftEvent,
    DriftKind,
    DriftSeverity,
    JsonValueType,
    SQLiteSchemaDriftRegistry,
    profile_json_snapshot,
)
from yandex_analytics_reaper.sources.yandex.schema_contracts import YANDEX_GET_GAMES_SCHEMA_V1
from yandex_analytics_reaper.storage import RawSnapshotMetadata

_SCOPE = "catalogue.get_games:test-cohort"


def _metadata(*, body: bytes, suffix: str, retrieved_at: datetime) -> RawSnapshotMetadata:
    snapshot_id = f"{retrieved_at:%Y%m%dT%H%M%S%fZ}-{suffix:0<10}"[:38]
    return RawSnapshotMetadata(
        id=snapshot_id,
        source_id="yandex_public",
        retrieved_at=retrieved_at,
        request_key="catalogue.get_games",
        method="POST",
        url="https://yandex.ru/games/api/catalogue/v2/get_games",
        request_context={},
        content_path=f"body/{snapshot_id}.json",
        metadata_path=f"meta/{snapshot_id}.json",
        content_hash=hashlib.sha256(body).hexdigest(),
        http_status=200,
        content_type="application/json",
        schema_hash=None,
    )


def _body(games: list[dict[str, object]]) -> bytes:
    return json.dumps({"games": games}).encode()


def _event_kinds(analysis_events: Sequence[DriftEvent]) -> set[DriftKind]:
    return {event.kind for event in analysis_events}


def test_profiler_tracks_field_types_and_missingness() -> None:
    observed_at = datetime(2026, 8, 29, 5, 0, tzinfo=UTC)
    body = _body(
        [
            {"appID": 1, "gqRating": 80},
            {"appID": 2},
            {"appID": 3, "gqRating": 70},
            {"appID": 4},
        ]
    )
    profile = profile_json_snapshot(
        _metadata(body=body, suffix="profile", retrieved_at=observed_at),
        body,
    )
    fields = {field.path: field for field in profile.fields}

    assert fields["$.games[].appID"].presence_ratio == 1.0
    rating = fields["$.games[].gqRating"]
    assert rating.value_types == (JsonValueType.INTEGER,)
    assert rating.present_count == 2
    assert rating.parent_count == 4
    assert rating.presence_ratio == 0.5


def test_first_valid_snapshot_has_no_baseline_noise(tmp_path: Path) -> None:
    registry = SQLiteSchemaDriftRegistry(tmp_path / "market.sqlite3")
    observed_at = datetime(2026, 8, 29, 5, 0, tzinfo=UTC)
    body = _body([{"appID": 1, "gqRating": 80}])

    analysis = registry.observe_json(
        _metadata(body=body, suffix="first", retrieved_at=observed_at),
        body,
        comparison_scope_id=_SCOPE,
        contract=YANDEX_GET_GAMES_SCHEMA_V1,
    )

    assert analysis.events == ()


def test_new_optional_field_is_informational(tmp_path: Path) -> None:
    registry = SQLiteSchemaDriftRegistry(tmp_path / "market.sqlite3")
    first = datetime(2026, 8, 29, 5, 0, tzinfo=UTC)
    before = _body([{"appID": 1}])
    registry.observe_json(
        _metadata(body=before, suffix="before", retrieved_at=first),
        before,
        comparison_scope_id=_SCOPE,
        contract=YANDEX_GET_GAMES_SCHEMA_V1,
    )

    after = _body([{"appID": 1, "newOptional": "x"}])
    analysis = registry.observe_json(
        _metadata(body=after, suffix="after", retrieved_at=first + timedelta(hours=1)),
        after,
        comparison_scope_id=_SCOPE,
        contract=YANDEX_GET_GAMES_SCHEMA_V1,
    )

    event = next(event for event in analysis.events if event.field_path == "$.games[].newOptional")
    assert event.kind is DriftKind.NEW_FIELD
    assert event.severity is DriftSeverity.INFO


def test_contract_type_change_is_breaking_even_if_parser_could_coerce_it(tmp_path: Path) -> None:
    registry = SQLiteSchemaDriftRegistry(tmp_path / "market.sqlite3")
    observed_at = datetime(2026, 8, 29, 5, 0, tzinfo=UTC)
    body = _body([{"appID": 1, "gqRating": "86"}])

    analysis = registry.observe_json(
        _metadata(body=body, suffix="string", retrieved_at=observed_at),
        body,
        comparison_scope_id=_SCOPE,
        contract=YANDEX_GET_GAMES_SCHEMA_V1,
    )

    mismatch = next(
        event
        for event in analysis.events
        if event.kind is DriftKind.CONTRACT_TYPE_MISMATCH
        and event.field_path == "$.games[].gqRating"
    )
    assert mismatch.severity is DriftSeverity.BREAKING
    assert mismatch.current_types == (JsonValueType.STRING,)


def test_missing_required_field_is_breaking(tmp_path: Path) -> None:
    registry = SQLiteSchemaDriftRegistry(tmp_path / "market.sqlite3")
    observed_at = datetime(2026, 8, 29, 5, 0, tzinfo=UTC)
    body = json.dumps({"unexpected": []}).encode()

    analysis = registry.observe_json(
        _metadata(body=body, suffix="missing", retrieved_at=observed_at),
        body,
        comparison_scope_id=_SCOPE,
        contract=YANDEX_GET_GAMES_SCHEMA_V1,
    )

    missing = next(
        event
        for event in analysis.events
        if event.kind is DriftKind.REQUIRED_FIELD_MISSING
        and event.field_path == "$.games"
    )
    assert missing.severity is DriftSeverity.BREAKING


def test_empty_games_array_does_not_fake_missing_app_id_drift(tmp_path: Path) -> None:
    registry = SQLiteSchemaDriftRegistry(tmp_path / "market.sqlite3")
    observed_at = datetime(2026, 8, 29, 5, 0, tzinfo=UTC)
    body = _body([])

    analysis = registry.observe_json(
        _metadata(body=body, suffix="empty", retrieved_at=observed_at),
        body,
        comparison_scope_id=_SCOPE,
        contract=YANDEX_GET_GAMES_SCHEMA_V1,
    )

    assert not any(event.field_path == "$.games[].appID" for event in analysis.events)


def test_material_missingness_change_is_warning(tmp_path: Path) -> None:
    registry = SQLiteSchemaDriftRegistry(tmp_path / "market.sqlite3")
    first = datetime(2026, 8, 29, 5, 0, tzinfo=UTC)
    dense = _body([{"appID": item, "gqRating": 80} for item in range(4)])
    registry.observe_json(
        _metadata(body=dense, suffix="dense", retrieved_at=first),
        dense,
        comparison_scope_id=_SCOPE,
        contract=YANDEX_GET_GAMES_SCHEMA_V1,
    )

    sparse = _body(
        [
            {"appID": 1, "gqRating": 80},
            {"appID": 2},
            {"appID": 3},
            {"appID": 4},
        ]
    )
    analysis = registry.observe_json(
        _metadata(body=sparse, suffix="sparse", retrieved_at=first + timedelta(hours=1)),
        sparse,
        comparison_scope_id=_SCOPE,
        contract=YANDEX_GET_GAMES_SCHEMA_V1,
    )

    missingness = next(
        event
        for event in analysis.events
        if event.kind is DriftKind.MISSINGNESS_CHANGED
        and event.field_path == "$.games[].gqRating"
    )
    assert missingness.severity is DriftSeverity.WARNING
    assert missingness.previous_presence_ratio == 1.0
    assert missingness.current_presence_ratio == 0.25


def test_different_comparison_scopes_do_not_create_false_temporal_drift(tmp_path: Path) -> None:
    registry = SQLiteSchemaDriftRegistry(tmp_path / "market.sqlite3")
    first = datetime(2026, 8, 29, 5, 0, tzinfo=UTC)
    before = _body([{"appID": 1, "scopeOnly": True}])
    registry.observe_json(
        _metadata(body=before, suffix="scope-a", retrieved_at=first),
        before,
        comparison_scope_id="scope:a",
        contract=YANDEX_GET_GAMES_SCHEMA_V1,
    )

    after = _body([{"appID": 1}])
    analysis = registry.observe_json(
        _metadata(body=after, suffix="scope-b", retrieved_at=first + timedelta(hours=1)),
        after,
        comparison_scope_id="scope:b",
        contract=YANDEX_GET_GAMES_SCHEMA_V1,
    )

    assert DriftKind.REMOVED_FIELD not in _event_kinds(analysis.events)


def test_same_timestamp_has_no_artificial_snapshot_order(tmp_path: Path) -> None:
    registry = SQLiteSchemaDriftRegistry(tmp_path / "market.sqlite3")
    instant = datetime(2026, 8, 29, 5, 0, tzinfo=UTC)
    first = _body([{"appID": 1, "firstOnly": True}])
    registry.observe_json(
        _metadata(body=first, suffix="same-a", retrieved_at=instant),
        first,
        comparison_scope_id=_SCOPE,
        contract=YANDEX_GET_GAMES_SCHEMA_V1,
    )

    second = _body([{"appID": 1, "secondOnly": True}])
    analysis = registry.observe_json(
        _metadata(body=second, suffix="same-b", retrieved_at=instant),
        second,
        comparison_scope_id=_SCOPE,
        contract=YANDEX_GET_GAMES_SCHEMA_V1,
    )

    assert DriftKind.NEW_FIELD not in _event_kinds(analysis.events)
    assert DriftKind.REMOVED_FIELD not in _event_kinds(analysis.events)


def test_invalid_json_and_parser_failure_are_separate_breaking_events(tmp_path: Path) -> None:
    registry = SQLiteSchemaDriftRegistry(tmp_path / "market.sqlite3")
    observed_at = datetime(2026, 8, 29, 5, 0, tzinfo=UTC)
    body = b"{not-json"
    metadata = _metadata(body=body, suffix="broken", retrieved_at=observed_at)

    raw_analysis = registry.observe_json(
        metadata,
        body,
        comparison_scope_id=_SCOPE,
        contract=YANDEX_GET_GAMES_SCHEMA_V1,
    )
    parser_analysis = registry.record_parser_failure(
        metadata,
        comparison_scope_id=_SCOPE,
        parser_name="YandexGetGamesParser",
        parser_version="3",
        error="get_games root must be an object",
    )

    assert raw_analysis.events[0].kind is DriftKind.RAW_PARSE_FAILURE
    assert raw_analysis.events[0].severity is DriftSeverity.BREAKING
    assert parser_analysis.events[0].kind is DriftKind.PARSER_FAILURE
    assert parser_analysis.events[0].severity is DriftSeverity.BREAKING
    assert len(registry.analyses_for_snapshot(metadata.id)) == 2


def test_out_of_order_backfill_never_compares_against_future_snapshot(tmp_path: Path) -> None:
    registry = SQLiteSchemaDriftRegistry(tmp_path / "market.sqlite3")
    base = datetime(2026, 8, 29, 5, 0, tzinfo=UTC)

    future = _body([{"appID": 1, "futureOnly": True}])
    registry.observe_json(
        _metadata(body=future, suffix="future", retrieved_at=base + timedelta(hours=2)),
        future,
        comparison_scope_id=_SCOPE,
        contract=YANDEX_GET_GAMES_SCHEMA_V1,
    )
    past = _body([{"appID": 1}])
    historical = registry.observe_json(
        _metadata(body=past, suffix="past", retrieved_at=base),
        past,
        comparison_scope_id=_SCOPE,
        contract=YANDEX_GET_GAMES_SCHEMA_V1,
    )

    assert DriftKind.REMOVED_FIELD not in _event_kinds(historical.events)
    assert DriftKind.NEW_FIELD not in _event_kinds(historical.events)

    middle_body = _body([{"appID": 1, "middleOnly": True}])
    middle = registry.observe_json(
        _metadata(body=middle_body, suffix="middle", retrieved_at=base + timedelta(hours=1)),
        middle_body,
        comparison_scope_id=_SCOPE,
        contract=YANDEX_GET_GAMES_SCHEMA_V1,
    )
    paths = {event.field_path for event in middle.events}
    assert "$.games[].middleOnly" in paths
    assert "$.games[].futureOnly" not in paths


def test_same_raw_snapshot_can_have_multiple_versioned_contract_analyses(tmp_path: Path) -> None:
    registry = SQLiteSchemaDriftRegistry(tmp_path / "market.sqlite3")
    observed_at = datetime(2026, 8, 29, 5, 0, tzinfo=UTC)
    body = _body([{"appID": 1}])
    metadata = _metadata(body=body, suffix="multi", retrieved_at=observed_at)

    contracted = registry.observe_json(
        metadata,
        body,
        comparison_scope_id=_SCOPE,
        contract=YANDEX_GET_GAMES_SCHEMA_V1,
    )
    uncontracted = registry.observe_json(
        metadata,
        body,
        comparison_scope_id=_SCOPE,
    )

    assert contracted.analysis_id != uncontracted.analysis_id
    assert len(registry.analyses_for_snapshot(metadata.id)) == 2


def test_registry_rejects_wrong_body_even_when_analysis_is_cached(tmp_path: Path) -> None:
    registry = SQLiteSchemaDriftRegistry(tmp_path / "market.sqlite3")
    observed_at = datetime(2026, 8, 29, 5, 0, tzinfo=UTC)
    original = _body([{"appID": 1}])
    metadata = _metadata(body=original, suffix="integrity", retrieved_at=observed_at)
    registry.observe_json(
        metadata,
        original,
        comparison_scope_id=_SCOPE,
        contract=YANDEX_GET_GAMES_SCHEMA_V1,
    )

    with pytest.raises(ValueError, match="content hash"):
        registry.observe_json(
            metadata,
            _body([{"appID": 2}]),
            comparison_scope_id=_SCOPE,
            contract=YANDEX_GET_GAMES_SCHEMA_V1,
        )
