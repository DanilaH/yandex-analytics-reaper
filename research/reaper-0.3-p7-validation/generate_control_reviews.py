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

REVIEWED_AT = "2026-09-02T16:00:00Z"

DECISIONS: dict[str, tuple[tuple[str, str, str, str | None], ...]] = {
    "custom-headphones": (
        (
            "yandex_games:517500",
            "not_direct",
            "mechanic_applies_to_other_object",
            "Headphones are incidental character styling; the decorate action applies to the room.",
        ),
        (
            "yandex_games:289855",
            "adjacent",
            "broader_multi_object_scope",
            "Headphones are one object among many aqua-print targets; useful customization grammar but not headphone-specific supply.",
        ),
    ),
    "custom-digicam": (
        (
            "yandex_games:428186",
            "not_direct",
            "theme_incidental",
            "Camera is a view-control mention while customization applies to the avatar.",
        ),
        (
            "yandex_games:439066",
            "not_direct",
            "mechanic_applies_to_other_object",
            "Beauty/fashion customization does not customize a camera or digicam.",
        ),
        (
            "yandex_games:248029",
            "not_direct",
            "theme_incidental",
            "Customization applies to a virtual pet; camera language is not the customization object.",
        ),
        (
            "yandex_games:350057",
            "not_direct",
            "theme_incidental",
            "Camera is a view-control mention and suspension is a car upgrade, not a camera charm.",
        ),
        (
            "yandex_games:438282",
            "not_direct",
            "theme_incidental",
            "Camera is a view-control mention and suspension is a car tuning part.",
        ),
        (
            "yandex_games:407439",
            "not_direct",
            "mechanic_applies_to_other_object",
            "The game decorates a hotel; camera is only a control/view mention.",
        ),
    ),
    "restore-retro-pocket-tech": (
        (
            "yandex_games:413168",
            "adjacent",
            "broader_multi_object_scope",
            "Real phone/electronics diagnosis and part-replacement loop, but a broad modern repair workshop rather than retro pocket-tech restoration/cleaning.",
        ),
        (
            "yandex_games:551629",
            "not_direct",
            "theme_incidental",
            "Phone appears in control context; repair gameplay concerns infrastructure during a firefighter simulation.",
        ),
        (
            "yandex_games:432691",
            "not_direct",
            "theme_incidental",
            "Phone is a platform/control reference; the game is a Dyatlov Pass hidden-object investigation.",
        ),
        (
            "yandex_games:489050",
            "not_direct",
            "theme_incidental",
            "Phone is a platform/control reference; the game is Backrooms survival.",
        ),
        (
            "yandex_games:235051",
            "not_direct",
            "mechanic_applies_to_other_object",
            "The repair action applies to a car while camera is only a control reference.",
        ),
        (
            "yandex_games:457561",
            "not_direct",
            "mechanic_applies_to_other_object",
            "Restoration applies to an old hotel, not pocket technology.",
        ),
        (
            "yandex_games:453758",
            "not_direct",
            "mechanic_applies_to_other_object",
            "Repair applies to cars; camera/player matches come from controls or multiplayer wording.",
        ),
        (
            "yandex_games:225999",
            "not_direct",
            "mechanic_applies_to_other_object",
            "Repair applies to cars; camera/player matches come from controls or multiplayer wording.",
        ),
        (
            "yandex_games:422450",
            "not_direct",
            "mechanic_applies_to_other_object",
            "Repair applies to cars and camera is a driving view control.",
        ),
        (
            "yandex_games:559346",
            "not_direct",
            "theme_incidental",
            "Phone language is platform/control context; the game is a traffic-gap timing puzzle.",
        ),
        (
            "yandex_games:547723",
            "not_direct",
            "mechanic_applies_to_other_object",
            "Repair applies to cars and camera is a driving view control.",
        ),
    ),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("suite", type=Path)
    parser.add_argument("intelligence_zip", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()

    suite = ThesisSuiteDeclaration.model_validate_json(args.suite.read_text(encoding="utf-8"))
    thesis_by_id = {item.thesis_id: item for item in suite.theses}
    args.output_dir.mkdir(parents=True, exist_ok=True)

    with ZipFile(args.intelligence_zip, mode="r") as archive:
        for thesis_id, decisions in DECISIONS.items():
            thesis = thesis_by_id[thesis_id]
            semantic = AnalystSemanticEnrichmentReport.model_validate_json(
                archive.read(f"semantic/{thesis_id}.json")
            )
            expected_ids = {
                item.platform_listing_id
                for item in semantic.listings
                if item.directness == "direct_candidate"
            }
            reviewed_ids = {item[0] for item in decisions}
            if reviewed_ids != expected_ids:
                raise ValueError(
                    f"{thesis_id}: review IDs do not equal semantic direct-candidate IDs; "
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
                for listing_id, verdict, reason_code, note in decisions
            )
            payload = AnalystDirectnessReviewPayload(
                suite_id=suite.suite_id,
                suite_version=suite.suite_version,
                thesis_id=thesis_id,
                thesis_version=thesis.thesis_version,
                semantic_report_content_hash=semantic.content_hash,
                rows=rows,
            )
            report = AnalystDirectnessReviewReport(
                **payload.model_dump(mode="python"),
                content_hash=canonical_model_hash(payload),
            )
            validate_directness_review(
                report,
                suite=suite,
                semantic_report=semantic,
            )
            output = args.output_dir / f"{thesis_id}.json"
            output.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "reviewed_theses": list(DECISIONS),
                "reviewed_candidate_count": sum(len(items) for items in DECISIONS.values()),
                "output_dir": str(args.output_dir),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
