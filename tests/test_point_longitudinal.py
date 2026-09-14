from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from yandex_analytics_reaper.point_longitudinal import compare_listing_observation_artifacts
from yandex_analytics_reaper.point_observation import (
    ListingObservationError,
    ListingObservationSetDeclaration,
    build_listing_observation_report,
    write_listing_observation_artifact,
)
from yandex_analytics_reaper.storage import RawSnapshotMetadata


def _body(values: dict[int, int | None]) -> bytes:
    games: list[dict[str, object]] = []
    for app_id, rating_count in values.items():
        game: dict[str, object] = {
            "appID": app_id,
            "title": f"Game {app_id}",
        }
        if rating_count is not None:
            game["ratingCount"] = rating_count
        games.append(game)
    return json.dumps({"games": games}, separators=(",", ":")).encode()


def _artifact(
    path: Path,
    *,
    observed_at: datetime,
    requested: tuple[int, ...],
    returned: dict[int, int | None],
    version: int = 1,
) -> Path:
    declaration = ListingObservationSetDeclaration(
        observation_set_id="known-cohort",
        observation_set_version=version,
        app_ids=requested,
    )
    body = _body(returned)
    content_hash = hashlib.sha256(body).hexdigest()
    metadata = RawSnapshotMetadata(
        id=f"snapshot-{observed_at:%Y%m%d%H%M%S}-{version}",
        source_id="yandex_public",
        retrieved_at=observed_at,
        request_key="catalogue.get_games",
        method="POST",
        url="https://yandex.ru/games/api/catalogue/v2/get_games",
        request_context={"app_ids": list(requested), "format": "long"},
        content_path="raw/body.json",
        metadata_path="raw/metadata.json",
        content_hash=content_hash,
        http_status=200,
        content_type="application/json",
    )
    report = build_listing_observation_report(declaration, metadata, body)
    write_listing_observation_artifact(
        path,
        declaration=declaration,
        report=report,
        raw_metadata_bytes=metadata.model_dump_json(indent=2).encode(),
        raw_body=body,
    )
    return path


def test_longitudinal_comparison_preserves_delta_revision_and_missing_semantics(
    tmp_path: Path,
) -> None:
    requested = (1, 2, 3, 4, 5)
    previous = _artifact(
        tmp_path / "previous.zip",
        observed_at=datetime(2026, 9, 14, 12, 0, tzinfo=UTC),
        requested=requested,
        returned={1: 10, 2: 20, 4: None, 5: 5},
    )
    current = _artifact(
        tmp_path / "current.zip",
        observed_at=datetime(2026, 9, 16, 12, 0, tzinfo=UTC),
        requested=requested,
        returned={1: 14, 2: 18, 3: 7, 4: 9},
    )
    output = tmp_path / "comparison.json"

    comparison = compare_listing_observation_artifacts(previous, current, output)

    assert comparison.provenance_channel == "point_observed"
    assert comparison.elapsed_seconds == 172_800
    assert comparison.elapsed_days == 2.0
    assert comparison.requested_app_ids == requested
    facts = {fact.app_id: fact for fact in comparison.facts}

    assert facts[1].measurement_status == "comparable"
    assert facts[1].rating_count_delta == 4
    assert facts[1].observed_rating_delta_per_day == 2.0
    assert facts[1].revision_status == "increase"

    assert facts[2].measurement_status == "comparable"
    assert facts[2].rating_count_delta == -2
    assert facts[2].observed_rating_delta_per_day == -1.0
    assert facts[2].revision_status == "revision_decrease"

    assert facts[3].measurement_status == "missing_previous"
    assert facts[3].rating_count_delta is None
    assert facts[3].revision_status == "unavailable"

    assert facts[4].measurement_status == "metric_missing_previous"
    assert facts[4].rating_count_previous is None
    assert facts[4].rating_count_current == 9

    assert facts[5].measurement_status == "missing_current"
    assert facts[5].rating_count_previous == 5
    assert facts[5].rating_count_current is None

    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert persisted["interpretation_boundary"] == (
        "point_velocity_not_search_visibility_dau_installs_revenue_or_retention"
    )
    assert persisted["previous"]["artifact_sha256"] == comparison.previous.artifact_sha256
    assert persisted["current"]["artifact_sha256"] == comparison.current.artifact_sha256


def test_longitudinal_output_is_create_only_before_artifact_work(tmp_path: Path) -> None:
    output = tmp_path / "comparison.json"
    output.write_text("existing", encoding="utf-8")

    with pytest.raises(ListingObservationError, match="refusing to overwrite"):
        compare_listing_observation_artifacts(
            tmp_path / "does-not-need-to-exist-before.zip",
            tmp_path / "also-does-not-need-to-exist-before.zip",
            output,
        )


def test_longitudinal_comparison_rejects_changed_cohort_identity(tmp_path: Path) -> None:
    previous = _artifact(
        tmp_path / "previous.zip",
        observed_at=datetime(2026, 9, 14, 12, 0, tzinfo=UTC),
        requested=(1, 2),
        returned={1: 10, 2: 20},
        version=1,
    )
    current = _artifact(
        tmp_path / "current.zip",
        observed_at=datetime(2026, 9, 16, 12, 0, tzinfo=UTC),
        requested=(1, 2),
        returned={1: 12, 2: 22},
        version=2,
    )

    with pytest.raises(ListingObservationError, match="not compatible"):
        compare_listing_observation_artifacts(previous, current, tmp_path / "comparison.json")


def test_longitudinal_comparison_requires_forward_time(tmp_path: Path) -> None:
    previous = _artifact(
        tmp_path / "previous.zip",
        observed_at=datetime(2026, 9, 16, 12, 0, tzinfo=UTC),
        requested=(1,),
        returned={1: 10},
    )
    current = _artifact(
        tmp_path / "current.zip",
        observed_at=datetime(2026, 9, 14, 12, 0, tzinfo=UTC),
        requested=(1,),
        returned={1: 12},
    )

    with pytest.raises(ListingObservationError, match="later than previous"):
        compare_listing_observation_artifacts(previous, current, tmp_path / "comparison.json")
