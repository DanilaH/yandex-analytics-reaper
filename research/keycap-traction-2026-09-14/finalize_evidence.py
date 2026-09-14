from __future__ import annotations

import json
import zipfile
from datetime import datetime
from pathlib import Path

from yandex_analytics_reaper.analyst import AnalystSemanticEnrichmentReport
from yandex_analytics_reaper.sources.yandex.client import YandexPublicClient
from yandex_analytics_reaper.thesis_directness import (
    DirectnessReviewDecisionV1,
    build_directness_review,
)
from yandex_analytics_reaper.thesis_workflow import load_thesis_suite

SUITE_PATH = Path("research/keycap-traction-2026-09-14/suite.json")
REVIEW_PATH = Path("research/keycap-traction-2026-09-14/directness-review.json")
KNOWN_DIRECT_PATH = Path("known-direct-553722.json")
REVIEWED_AT = datetime.fromisoformat("2026-09-14T10:05:00+00:00")

EXPECTED_DIRECT_IDS = {
    "yandex_games:541802", "yandex_games:540402", "yandex_games:569883",
    "yandex_games:511439", "yandex_games:551728", "yandex_games:538799",
    "yandex_games:559445", "yandex_games:451175", "yandex_games:535429",
    "yandex_games:548061", "yandex_games:550210", "yandex_games:553057",
    "yandex_games:544722", "yandex_games:558742", "yandex_games:548593",
    "yandex_games:488053", "yandex_games:551195", "yandex_games:474636",
    "yandex_games:543052", "yandex_games:552303", "yandex_games:583932",
    "yandex_games:591339", "yandex_games:565786", "yandex_games:550524",
    "yandex_games:556438", "yandex_games:565058", "yandex_games:479295",
    "yandex_games:540983", "yandex_games:550472", "yandex_games:541682",
    "yandex_games:523149", "yandex_games:460480", "yandex_games:586494",
    "yandex_games:554841", "yandex_games:270605", "yandex_games:578851",
    "yandex_games:230025", "yandex_games:559744", "yandex_games:165866",
    "yandex_games:188896", "yandex_games:330401", "yandex_games:443005",
    "yandex_games:195283", "yandex_games:556089", "yandex_games:588690",
    "yandex_games:565301", "yandex_games:586441", "yandex_games:548740",
    "yandex_games:559212", "yandex_games:550206", "yandex_games:585306",
    "yandex_games:567315",
}
CONFIRMED_DIRECT_IDS = {"yandex_games:540402", "yandex_games:559445"}
ADJACENT_IDS = {"yandex_games:550210", "yandex_games:552303"}


def _find_unreviewed_intelligence_zip() -> Path:
    paths = sorted(Path("artifacts/intelligence/keycap-traction-2026-09-14").rglob("*.zip"))
    if len(paths) != 1:
        raise RuntimeError(f"expected exactly one unreviewed intelligence ZIP, found {len(paths)}")
    return paths[0]


def _load_semantic_report(path: Path) -> AnalystSemanticEnrichmentReport:
    with zipfile.ZipFile(path) as archive:
        raw = archive.read("semantic/keycap-asmr-collector.json")
    return AnalystSemanticEnrichmentReport.model_validate_json(raw)


def _write_known_direct_observation() -> None:
    with YandexPublicClient() as client:
        response = client.collect_games([553722])
    if response.status_code != 200:
        raise RuntimeError(f"known direct listing observation returned HTTP {response.status_code}")
    body = json.loads(response.body)
    payload = {
        "spec_version": "known-direct-point-observation-v1",
        "platform": "yandex_games",
        "app_ids": [553722],
        "request_key": response.request_key,
        "url": response.url,
        "status_code": response.status_code,
        "retrieved_at": response.retrieved_at.isoformat(),
        "request_context": response.request_context,
        "body": body,
    }
    KNOWN_DIRECT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_directness_review() -> None:
    suite = load_thesis_suite(SUITE_PATH)
    semantic = _load_semantic_report(_find_unreviewed_intelligence_zip())
    actual_direct_ids = {
        row.platform_listing_id for row in semantic.listings if row.directness == "direct_candidate"
    }
    if actual_direct_ids != EXPECTED_DIRECT_IDS:
        missing = sorted(EXPECTED_DIRECT_IDS - actual_direct_ids)
        unexpected = sorted(actual_direct_ids - EXPECTED_DIRECT_IDS)
        raise RuntimeError(
            "semantic direct-candidate set changed since manual review; "
            f"missing={missing}, unexpected={unexpected}"
        )

    decisions: list[DirectnessReviewDecisionV1] = []
    for row in semantic.listings:
        if row.directness != "direct_candidate":
            continue
        listing_id = row.platform_listing_id
        if listing_id in CONFIRMED_DIRECT_IDS:
            verdict = "confirmed_direct"
            reason = "direct_mechanic_and_theme"
            note = None
        elif listing_id in ADJACENT_IDS:
            verdict = "adjacent"
            reason = "other"
            note = "Keyboard customization/ASMR is present, but the core loop is obby rather than keyboard click/upgrade/collection."
        else:
            verdict = "not_direct"
            reason = "mechanic_mismatch"
            note = None
        decisions.append(
            DirectnessReviewDecisionV1(
                platform_listing_id=listing_id,
                analyst_verdict=verdict,
                reason_code=reason,
                note=note,
                reviewed_at=REVIEWED_AT,
            )
        )

    review = build_directness_review(suite, semantic, decisions=tuple(decisions))
    REVIEW_PATH.write_text(review.model_dump_json(indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    _write_known_direct_observation()
    _write_directness_review()
