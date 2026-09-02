from __future__ import annotations

import argparse
import json
from pathlib import Path
from zipfile import ZipFile

from yandex_analytics_reaper.analyst import AnalystSemanticEnrichmentReport
from yandex_analytics_reaper.thesis_directness import (
    AnalystDirectnessReviewPayload,
    AnalystDirectnessReviewReport,
    AnalystDirectnessReviewRow,
    validate_directness_review,
)
from yandex_analytics_reaper.thesis_intelligence import (
    ThesisSuiteDeclaration,
    canonical_model_hash,
)

REVIEWED_AT = "2026-09-02T16:15:00Z"

DECISIONS = (
    (
        "yandex_games:540826",
        "confirmed_direct",
        "direct_mechanic_and_theme",
        "Exact low-complexity core: choose a weapon, click an ordinary object, break it, repeat.",
    ),
    (
        "yandex_games:430845",
        "confirmed_direct",
        "direct_mechanic_and_theme",
        "Direct break-all-objects-with-weapons loop; movement makes production heavier but the gameplay job is direct.",
    ),
    (
        "yandex_games:476984",
        "confirmed_direct",
        "direct_mechanic_and_theme",
        "Direct room-destruction loop using weapons against furniture, electronics and decor.",
    ),
    (
        "yandex_games:373094",
        "confirmed_direct",
        "direct_mechanic_and_theme",
        "Simple click/tap shooting loop whose explicit objective is breaking bottles for score.",
    ),
    (
        "yandex_games:437035",
        "adjacent",
        "broader_multi_object_scope",
        "Primary fantasy is superhero/ragdoll combat; object destruction is a substantial but secondary chaos mechanic.",
    ),
    (
        "yandex_games:513912",
        "not_direct",
        "mechanic_applies_to_other_object",
        "Primary game is a 3D physics puzzle; breaking glass cubes is one incidental submechanic.",
    ),
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("suite", type=Path)
    parser.add_argument("intelligence_zip", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    suite = ThesisSuiteDeclaration.model_validate_json(args.suite.read_text(encoding="utf-8"))
    thesis = suite.theses[0]
    with ZipFile(args.intelligence_zip, mode="r") as archive:
        semantic = AnalystSemanticEnrichmentReport.model_validate_json(
            archive.read("semantic/satisfying-destruction.json")
        )

    expected_ids = {
        item.platform_listing_id
        for item in semantic.listings
        if item.directness == "direct_candidate"
    }
    reviewed_ids = {item[0] for item in DECISIONS}
    if reviewed_ids != expected_ids:
        raise ValueError(
            "review IDs do not equal semantic direct-candidate IDs; "
            f"missing={sorted(expected_ids - reviewed_ids)}, "
            f"unexpected={sorted(reviewed_ids - expected_ids)}"
        )

    rows = tuple(
        AnalystDirectnessReviewRow(
            platform_listing_id=listing_id,
            analyst_verdict=verdict,
            reason_code=reason_code,
            note=note,
            reviewed_at=REVIEWED_AT,
        )
        for listing_id, verdict, reason_code, note in DECISIONS
    )
    payload = AnalystDirectnessReviewPayload(
        suite_id=suite.suite_id,
        suite_version=suite.suite_version,
        thesis_id=thesis.thesis_id,
        thesis_version=thesis.thesis_version,
        semantic_report_content_hash=semantic.content_hash,
        rows=rows,
    )
    report = AnalystDirectnessReviewReport(
        **payload.model_dump(mode="python"),
        content_hash=canonical_model_hash(payload),
    )
    validate_directness_review(report, suite=suite, semantic_report=semantic)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "reviewed_candidate_count": len(rows),
                "confirmed_direct": sum(row.analyst_verdict == "confirmed_direct" for row in rows),
                "adjacent": sum(row.analyst_verdict == "adjacent" for row in rows),
                "not_direct": sum(row.analyst_verdict == "not_direct" for row in rows),
                "semantic_report_content_hash": semantic.content_hash,
                "review_content_hash": report.content_hash,
                "output": str(args.output),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
