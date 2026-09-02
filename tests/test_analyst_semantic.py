from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from yandex_analytics_reaper.analyst import (
    AnalystComparableSetBinding,
    AnalystRichMetadataBinding,
    AnalystSemanticEnricher,
    AnalystSemanticRule,
    AnalystSemanticThesisDeclaration,
    AnalystSnapshotPayload,
    AnalystSnapshotReport,
    validate_analyst_semantic_enrichment,
    write_analyst_semantic_csv,
)
from yandex_analytics_reaper.domain import ProbeContext
from yandex_analytics_reaper.sources import CollectedResponse
from yandex_analytics_reaper.sources.yandex.parsers import YandexGetGamesParser
from yandex_analytics_reaper.storage import FilesystemRawSnapshotStore


def _snapshot_hash(payload: AnalystSnapshotPayload) -> str:
    encoded = json.dumps(
        payload.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _snapshot(raw_store: FilesystemRawSnapshotStore) -> AnalystSnapshotReport:
    retrieved_at = datetime(2026, 9, 2, 10, 0, tzinfo=UTC)
    body = json.dumps(
        {
            "games": [
                {
                    "appID": 1,
                    "title": "Custom Headphones Studio",
                    "description": (
                        "<p>Decorate your headphones with rhinestones, charms and stickers. "
                        "Complete designs for your collection.</p>"
                    ),
                    "instruction": "Choose a color, add charms, then reveal the final design.",
                    "seoDescription": "Headphone customization game",
                    "categoriesNames": ["Симуляторы"],
                    "categoryIDs": [7],
                    "tagIDs": [10, 11],
                },
                {
                    "appID": 2,
                    "title": "Headphones Music Player",
                    "description": "Listen to tracks using stylish headphones.",
                },
                {
                    "appID": 3,
                    "title": "DIY Phone Case",
                    "description": "Decorate a phone case with stickers and charms.",
                },
                {
                    "appID": 4,
                    "title": "Merge Island",
                    "description": "Merge fruit and build an island.",
                },
            ]
        },
        ensure_ascii=False,
    ).encode()
    metadata = raw_store.persist(
        CollectedResponse(
            source_id="yandex_public",
            request_key="catalogue.get_games",
            method="GET",
            url="https://yandex.test/games",
            status_code=200,
            headers={"content-type": "application/json"},
            body=body,
            retrieved_at=retrieved_at,
            request_context={},
        )
    )
    listing_ids = tuple(f"yandex_games:{app_id}" for app_id in range(1, 5))
    comparable = AnalystComparableSetBinding(
        set_id="headphones-thesis",
        version=1,
        query_family_id="headphones-queries",
        query_family_version=1,
        construction_method="yandex_search_union_v1",
        context_id="ctx:test",
        requested_page_limit=3,
        observed_from=datetime(2026, 9, 2, 9, 0, tzinfo=UTC),
        observed_to=datetime(2026, 9, 2, 9, 30, tzinfo=UTC),
        search_run_ids=("run:headphones",),
        member_listing_ids=listing_ids,
    )
    rich = AnalystRichMetadataBinding(
        source_id="yandex_public",
        request_key="catalogue.get_games",
        raw_snapshot_id=metadata.id,
        retrieved_at=metadata.retrieved_at,
        content_hash=metadata.content_hash,
        parser_name=YandexGetGamesParser.__name__,
        parser_version=YandexGetGamesParser.version,
        parsed_listing_ids=listing_ids,
        relevant_listing_ids=listing_ids,
    )
    payload = AnalystSnapshotPayload(
        spec_version="analyst-snapshot-v1",
        snapshot_id="snapshot:semantic-test",
        created_at=datetime(2026, 9, 2, 10, 5, tzinfo=UTC),
        collection_parameters_status="provisional_uncalibrated",
        effective_context=ProbeContext(),
        search_page_limit=3,
        comparable_sets=(comparable,),
        feed_runs=(),
        rich_metadata=(rich,),
    )
    return AnalystSnapshotReport.model_validate(
        {**payload.model_dump(mode="python"), "content_hash": _snapshot_hash(payload)}
    )


def _thesis() -> AnalystSemanticThesisDeclaration:
    return AnalystSemanticThesisDeclaration(
        spec_version="analyst-semantic-thesis-v1",
        thesis_id="custom-headphones",
        version=1,
        label="customization x headphones",
        target_set_ids=("headphones-thesis",),
        theme=AnalystSemanticRule(terms=("headphone", "наушник")),
        mechanic=AnalystSemanticRule(terms=("decorate", "customization", "stickers", "charms")),
        reward_grammar=AnalystSemanticRule(terms=("collection", "reveal")),
    )


def test_semantic_enrichment_separates_direct_adjacent_and_noise(tmp_path: Path) -> None:
    raw_store = FilesystemRawSnapshotStore(tmp_path / "raw")
    report = AnalystSemanticEnricher(raw_store=raw_store).build(_snapshot(raw_store), _thesis())
    report = validate_analyst_semantic_enrichment(report)

    rows = {row.external_app_id: row for row in report.listings}
    assert rows["1"].directness == "direct_candidate"
    assert rows["2"].directness == "adjacent_candidate"
    assert rows["3"].directness == "adjacent_candidate"
    assert rows["4"].directness == "noise_candidate"

    direct = rows["1"]
    assert direct.theme_match.status == "match"
    assert direct.mechanic_match.status == "match"
    assert direct.reward_grammar_match.status == "match"
    assert direct.source is not None
    assert direct.source.source_object_path == "$.games[0]"
    assert direct.corpus.description is not None
    assert "<p>" not in direct.theme_match.evidence_snippets[0].snippet
    assert direct.corpus.category_ids == (7,)
    assert direct.corpus.tag_ids == (10, 11)


def test_semantic_enrichment_is_deterministic_and_csv_keeps_evidence(tmp_path: Path) -> None:
    raw_store = FilesystemRawSnapshotStore(tmp_path / "raw")
    snapshot = _snapshot(raw_store)
    thesis = _thesis()

    first = AnalystSemanticEnricher(raw_store=raw_store).build(snapshot, thesis)
    second = AnalystSemanticEnricher(raw_store=raw_store).build(snapshot, thesis)
    assert first == second

    csv_path = tmp_path / "semantic.csv"
    write_analyst_semantic_csv(first, csv_path)
    csv_text = csv_path.read_text(encoding="utf-8")
    assert "direct_candidate" in csv_text
    assert "evidence_snippets" in csv_text
    assert first.listings[0].source is not None
    assert first.listings[0].source.raw_snapshot_id in csv_text
