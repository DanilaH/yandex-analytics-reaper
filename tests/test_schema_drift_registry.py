from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from yandex_analytics_reaper.schema_drift import (
    DriftKind,
    DriftSeverity,
    JsonValueType,
    SQLiteSchemaDriftRegistry,
    profile_json_snapshot,
)
from yandex_analytics_reaper.sources.yandex.schema_contracts import YANDEX_GET_GAMES_SCHEMA_V1
from yandex_analytics_reaper.storage import RawSnapshotMetadata


def _metadata(*, suffix: str, retrieved_at: datetime) -> RawSnapshotMetadata:
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
        content_hash="a" * 64,
        http_status=200,
        content_type="application/json",
        schema_hash="b" * 64,
    )


def _body(games: list[dict[str, object]]) -> bytes:
    return json.dumps({"games": games}).encode()


def _event_kinds(analysis_events: object) -> set[DriftKind]:
    return {event.kind for event in analysis_events}  # type: ignore[attr-defined]


def test_profiler_tracks_field_types_and_missingness() -> None:
    observed_at = datetime(2026, 8, 29, 5, 0, tzinfo=UTC)
    profile = profile_json_snapshot(
        _metadata(suffix="profile", retrieved_at=observed_at),
        _body(
            [
                {"appID": 1, "gqRating": 80},
                {"appID": 2},
                {"appID": 3, "gqRating": 70},
                {"appID": 4},
            ]
        ),
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

    analysis = registry.observe_json(
        _metadata(suffix="first", retrieved_at=observed_at),
        _body([{"appID": 1, "gqRating": 80}]),
        contract=YANDEX_GET_GAMES_SCHEMA_V1,
    )

    assert analysis.events == ()


def test_new_optional_field_is_informational(tmp_path: Path) -> None:
    registry = SQLiteSchemaDriftRegistry(tmp_path / "market.sqlite3")
    first = datetime(2026, 8, 29, 5, 0, tzinfo=UTC)
    registry.observe_json(
        _metadata(suffix="before", retrieved_at=first),
        _body([{"appID": 1}]),
        contract=YANDEX_GET_GAMES_SCHEMA_V1,
    )

    analysis = registry.observe_json(
        _metadata(suffix="after", retrieved_at=first + timedelta(hours=1)),
        _body([{"appID": 1, "newOptional": "x"}]),
        contract=YANDEX_GET_GAMES_SCHEMA_V1,
    )

    event = next(event for event in analysis.events if event.field_path == "$.games[].newOptional")
    assert event.kind is DriftKind.NEW_FIELD
    assert event.severity is DriftSeverity.INFO


def test_contract_type_change_is_breaking_even_if_parser_could_coerce_it(tmp_path: Path) -> None:
    registry = SQLiteSchemaDriftRegistry(tmp_path / "market.sqlite3")
    observed_at = datetime(2026, 8, 29, 5, 0, tzinfo=UTC)

    analysis = registry.observe_json(
        _metadata(suffix="string", retrieved_at=observed_at),
        _body([{"appID": 1, "gqRating": "86"}]),
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

    analysis = registry.observe_json(
        _metadata(suffix="missing", retrieved_at=observed_at),
        json.dumps({"unexpected": []}).encode(),
        contract=YANDEX_GET_GAMES_SCHEMA_V1,
    )

    missing = next(
        event
        for event in analysis.events
        if event.kind is DriftKind.REQUIRED_FIELD_MISSING
        and event.field_path == "$.games"
    )
    assert missing.severity is DriftSeverity.BREAKING


def test_material_missingness_change_is_warning(tmp_path: Path) -> None:
    registry = SQLiteSchemaDriftRegistry(tmp_path / "market.sqlite3")
    first = datetime(2026, 8, 29, 5, 0, tzinfo=UTC)
    registry.observe_json(
        _metadata(suffix="dense", retrieved_at=first),
        _body([{"appID": item, "gqRating": 80} for item in range(4)]),
        contract=YANDEX_GET_GAMES_SCHEMA_V1,
    )

    analysis = registry.observe_json(
        _metadata(suffix="sparse", retrieved_at=first + timedelta(hours=1)),
        _body(
            [
                {"appID": 1, "gqRating": 80},
                {"appID": 2},
                {"appID": 3},
                {"appID": 4},
            ]
        ),
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


def test_invalid_json_and_parser_failure_are_separate_breaking_events(tmp_path: Path) -> None:
    registry = SQLiteSchemaDriftRegistry(tmp_path / "market.sqlite3")
    observed_at = datetime(2026, 8, 29, 5, 0, tzinfo=UTC)
    metadata = _metadata(suffix="broken", retrieved_at=observed_at)

    raw_analysis = registry.observe_json(
        metadata,
        b"{not-json",
        contract=YANDEX_GET_GAMES_SCHEMA_V1,
    )
    parser_analysis = registry.record_parser_failure(
        metadata,
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

    registry.observe_json(
        _metadata(suffix="future", retrieved_at=base + timedelta(hours=2)),
        _body([{"appID": 1, "futureOnly": True}]),
        contract=YANDEX_GET_GAMES_SCHEMA_V1,
    )
    historical = registry.observe_json(
        _metadata(suffix="past", retrieved_at=base),
        _body([{"appID": 1}]),
        contract=YANDEX_GET_GAMES_SCHEMA_V1,
    )

    assert DriftKind.REMOVED_FIELD not in _event_kinds(historical.events)
    assert DriftKind.NEW_FIELD not in _event_kinds(historical.events)

    middle = registry.observe_json(
        _metadata(suffix="middle", retrieved_at=base + timedelta(hours=1)),
        _body([{"appID": 1, "middleOnly": True}]),
        contract=YANDEX_GET_GAMES_SCHEMA_V1,
    )
    paths = {event.field_path for event in middle.events}
    assert "$.games[].middleOnly" in paths
    assert "$.games[].futureOnly" not in paths


def test_same_raw_snapshot_can_have_multiple_versioned_contract_analyses(tmp_path: Path) -> None:
    registry = SQLiteSchemaDriftRegistry(tmp_path / "market.sqlite3")
    observed_at = datetime(2026, 8, 29, 5, 0, tzinfo=UTC)
    metadata = _metadata(suffix="multi", retrieved_at=observed_at)
    body = _body([{"appID": 1}])

    contracted = registry.observe_json(
        metadata,
        body,
        contract=YANDEX_GET_GAMES_SCHEMA_V1,
    )
    uncontracted = registry.observe_json(metadata, body)

    assert contracted.analysis_id != uncontracted.analysis_id
    assert len(registry.analyses_for_snapshot(metadata.id)) == 2
