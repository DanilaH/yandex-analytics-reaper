from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from yandex_analytics_reaper.analyst import (
    AnalystComparableSetBinding,
    AnalystRichMetadataBinding,
    AnalystSnapshotPayload,
)
from yandex_analytics_reaper.analyst_cli import _write_report
from yandex_analytics_reaper.domain import ProbeContext

_BASE = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)


def _comparable(set_id: str, *, page_limit: int) -> AnalystComparableSetBinding:
    return AnalystComparableSetBinding(
        set_id=set_id,
        version=1,
        query_family_id=f"{set_id}-family",
        query_family_version=1,
        construction_method="yandex_search_union_v1",
        context_id="context:shared",
        requested_page_limit=page_limit,
        observed_from=_BASE,
        observed_to=_BASE + timedelta(minutes=1),
        search_run_ids=(f"probe:{set_id}",),
        member_listing_ids=(f"yandex_games:{10 if set_id == 'merge' else 20}",),
    )


def _rich_metadata() -> AnalystRichMetadataBinding:
    return AnalystRichMetadataBinding(
        source_id="yandex_public",
        request_key="catalogue.get_games",
        raw_snapshot_id="20260829T120100000000Z-0000000000",
        retrieved_at=_BASE + timedelta(minutes=1),
        content_hash="0" * 64,
        parser_name="YandexGetGamesParser",
        parser_version="4",
        parsed_listing_ids=("yandex_games:10",),
        relevant_listing_ids=("yandex_games:10",),
    )


def test_snapshot_payload_rejects_mixed_search_page_limits() -> None:
    with pytest.raises(ValidationError, match="search_page_limit"):
        AnalystSnapshotPayload(
            spec_version="analyst-snapshot-v1",
            snapshot_id="pilot:v1",
            created_at=_BASE + timedelta(minutes=2),
            collection_parameters_status="provisional_uncalibrated",
            effective_context=ProbeContext(profile_age_days=0),
            search_page_limit=1,
            comparable_sets=(
                _comparable("merge", page_limit=1),
                _comparable("obby", page_limit=2),
            ),
            feed_runs=(),
            rich_metadata=(_rich_metadata(),),
        )


def test_snapshot_report_output_is_create_only(tmp_path: Path) -> None:
    report_path = tmp_path / "analysis" / "snapshot.json"

    _write_report(str(report_path), '{"snapshot_id":"pilot:v1"}')

    assert report_path.read_text(encoding="utf-8") == '{"snapshot_id":"pilot:v1"}\n'
    with pytest.raises(SystemExit, match="report already exists"):
        _write_report(str(report_path), '{"snapshot_id":"replacement"}')
