from __future__ import annotations

from datetime import UTC, datetime

from yandex_analytics_reaper.normalizers import NormalizationContext, YandexGameNormalizer
from yandex_analytics_reaper.sources.yandex.parsers import Developer, GameDetails


def test_details_normalizer_keeps_snapshot_scoped_developer_and_first_publication() -> None:
    instant = datetime(2026, 8, 29, 18, 0, tzinfo=UTC)
    source_timestamp = 1_750_000_000
    normalized = YandexGameNormalizer().normalize_details(
        GameDetails(
            app_id=10,
            source_object_path="$.games[0]",
            title="Example",
            developer=Developer(id=501, name="Snapshot Studio"),
            first_published=source_timestamp,
        ),
        NormalizationContext(
            raw_snapshot_id="raw:metadata",
            observed_at=instant,
            available_at=instant,
            retrieved_at=instant,
        ),
    )

    assert normalized.listing_state.developer_id == "yandex_games:501"
    assert normalized.listing_state.developer_name == "Snapshot Studio"
    assert normalized.listing_state.first_published_at == datetime.fromtimestamp(
        source_timestamp,
        UTC,
    )
    lineage = {
        item.target_field_path: item.source_field_path
        for item in normalized.listing_state_lineage
    }
    assert lineage["listing_state_observations.developer_name"] == "$.games[0].developer.name"
    assert lineage["listing_state_observations.first_published_at"] == "$.games[0].firstPublished"
