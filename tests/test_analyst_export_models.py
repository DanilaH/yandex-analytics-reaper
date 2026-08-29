from __future__ import annotations

import pytest
from pydantic import ValidationError

from yandex_analytics_reaper.analyst import AnalystSearchSupplyObservation


def test_missing_search_supply_preserves_missingness_without_fake_source_path() -> None:
    observation = AnalystSearchSupplyObservation(
        set_id="merge-search",
        set_version=1,
        query_text="merge",
        probe_run_id="probe:one",
        page_index=0,
        raw_snapshot_id="raw:one",
        total_games_count=None,
        missing_reason="source_missing",
    )

    assert observation.total_games_count is None
    assert observation.missing_reason == "source_missing"
    assert observation.source_field_path is None


def test_observed_search_supply_requires_exact_source_path() -> None:
    with pytest.raises(ValidationError, match="exact source path"):
        AnalystSearchSupplyObservation(
            set_id="merge-search",
            set_version=1,
            query_text="merge",
            probe_run_id="probe:one",
            page_index=0,
            raw_snapshot_id="raw:one",
            total_games_count=42,
        )
