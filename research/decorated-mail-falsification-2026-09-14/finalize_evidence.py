from __future__ import annotations

import zipfile
from datetime import datetime
from pathlib import Path

from yandex_analytics_reaper.analyst import AnalystSemanticEnrichmentReport
from yandex_analytics_reaper.thesis_directness import (
    DirectnessReviewDecisionV1,
    build_directness_review,
)
from yandex_analytics_reaper.thesis_workflow import load_thesis_suite

SUITE_PATH = Path("research/decorated-mail-falsification-2026-09-14/suite.json")
REVIEW_PATH = Path("research/decorated-mail-falsification-2026-09-14/directness-review.json")
REVIEWED_AT = datetime.fromisoformat("2026-09-14T10:42:00+00:00")

EXPECTED_DIRECT_IDS = {
    "yandex_games:494708",
    "yandex_games:393987",
    "yandex_games:528812",
    "yandex_games:244947",
    "yandex_games:473429",
    "yandex_games:485861",
    "yandex_games:274516",
    "yandex_games:273878",
    "yandex_games:523909",
    "yandex_games:237687",
    "yandex_games:237693",
    "yandex_games:474333",
    "yandex_games:213698",
    "yandex_games:462782",
    "yandex_games:552337",
    "yandex_games:492278",
}

ADJACENT_NOTES = {
    "yandex_games:485861": (
        "Postcard creation/coloring is a meaningful adjacent interaction, but the product has no physical-mail send/receive, stamp/postmark, or reply loop."
    ),
    "yandex_games:273878": (
        "The game contains collectible postage stamps and a stamp album, but they are a reward layer inside a hidden-object travel game rather than a decorated-mail loop."
    ),
}

NOT_DIRECT_REASONS = {
    "yandex_games:494708": "theme_mismatch",
    "yandex_games:393987": "theme_mismatch",
    "yandex_games:528812": "theme_mismatch",
    "yandex_games:244947": "theme_incidental",
    "yandex_games:473429": "theme_incidental",
    "yandex_games:274516": "theme_mismatch",
    "yandex_games:523909": "theme_mismatch",
    "yandex_games:237687": "theme_mismatch",
    "yandex_games:237693": "theme_mismatch",
    "yandex_games:474333": "theme_mismatch",
    "yandex_games:213698": "theme_mismatch",
    "yandex_games:462782": "theme_mismatch",
    "yandex_games:552337": "theme_mismatch",
    "yandex_games:492278": "theme_mismatch",
}


def _find_unreviewed_intelligence_zip() -> Path:
    paths = sorted(
        Path("artifacts/intelligence/decorated-mail-falsification-2026-09-14").rglob("*.zip")
    )
    if len(paths) != 1:
        raise RuntimeError(
            f"expected exactly one unreviewed intelligence ZIP, found {len(paths)}"
        )
    return paths[0]


def _load_semantic_report(path: Path) -> AnalystSemanticEnrichmentReport:
    with zipfile.ZipFile(path) as archive:
        raw = archive.read("semantic/decorated-mail-pen-pal.json")
    return AnalystSemanticEnrichmentReport.model_validate_json(raw)


def main() -> None:
    suite = load_thesis_suite(SUITE_PATH)
    semantic = _load_semantic_report(_find_unreviewed_intelligence_zip())
    actual_direct_ids = {
        row.platform_listing_id
        for row in semantic.listings
        if row.directness == "direct_candidate"
    }
    if actual_direct_ids != EXPECTED_DIRECT_IDS:
        missing = sorted(EXPECTED_DIRECT_IDS - actual_direct_ids)
        unexpected = sorted(actual_direct_ids - EXPECTED_DIRECT_IDS)
        raise RuntimeError(
            "semantic direct-candidate set changed since manual review; "
            f"missing={missing}, unexpected={unexpected}"
        )

    if set(ADJACENT_NOTES) | set(NOT_DIRECT_REASONS) != EXPECTED_DIRECT_IDS:
        raise RuntimeError("review classification does not cover the exact direct-candidate set")

    decisions: list[DirectnessReviewDecisionV1] = []
    for row in semantic.listings:
        if row.directness != "direct_candidate":
            continue
        listing_id = row.platform_listing_id
        if listing_id in ADJACENT_NOTES:
            decisions.append(
                DirectnessReviewDecisionV1(
                    platform_listing_id=listing_id,
                    analyst_verdict="adjacent",
                    reason_code="other",
                    note=ADJACENT_NOTES[listing_id],
                    reviewed_at=REVIEWED_AT,
                )
            )
        else:
            decisions.append(
                DirectnessReviewDecisionV1(
                    platform_listing_id=listing_id,
                    analyst_verdict="not_direct",
                    reason_code=NOT_DIRECT_REASONS[listing_id],
                    reviewed_at=REVIEWED_AT,
                )
            )

    review = build_directness_review(suite, semantic, decisions=tuple(decisions))
    REVIEW_PATH.write_text(review.model_dump_json(indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
