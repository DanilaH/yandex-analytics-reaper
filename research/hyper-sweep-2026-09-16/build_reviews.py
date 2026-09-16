"""Emit source-bound, deterministic analyst reviews from the human-curated verdict ledger.

Only the 2026-09-16 reviewed source snapshots are accepted. Every lexical
'direct_candidate' is bound to one explicit human decision (C/A or reviewed N).
This verifies metadata-review coverage, NOT source-wide competitor absence or
hands-on gameplay validation.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from zipfile import ZipFile

from yandex_analytics_reaper.analyst import AnalystSemanticEnrichmentReport
from yandex_analytics_reaper.thesis_directness import (
    DirectnessReviewDecisionV1,
    build_directness_review,
)
from yandex_analytics_reaper.thesis_workflow import load_thesis_suite

EXPECTED = {
    "prior": ("super-mega-giga-hyper-2026-09-16", "20260916T093032Z", "19400a97d95cd14114dce34fbc5855399579c962d842059ce64fcc4c1f16a286"),
    "new": ("hyper-sweep-product-systems-2026-09-16", "20260916T103334Z", "4330087e5efab003768d9560b903ff2fe28ef50ed75924d5ffcade75e3f16fe5"),
}
NOTES = {
    "yandex_games:562662": "Breeding, genetic ancestry and predicted offspring breeds occur, but the published offspring outcome is pair/recipe based; inheritance of visible individual traits is not established. Near-direct, not proven exact.",
    "yandex_games:361923": "Explicit yes/no responses change kingdom resources and lead to recurring decisions. Direct interaction, not evidence that a tiny content-free clone retains users.",
    "yandex_games:555782": "Explicit one-touch knife flip, cut scoring, combo and landing timing; full 3D authored levels remain a production cost.",
    "yandex_games:417566": "One-tap airborne knife, fruit cuts, hazards and finish; matches the target interaction, not proof of a cheap fully featured version.",
    "yandex_games:565549": "Drive robot vacuum around room, cover dirty floor, empty bin and buy upgrades; full 3D room is materially heavier than a 2D extraction.",
    "yandex_games:559814": "Switch magnetic polarity to attract or repel across authored levels; exact stateful movement mechanic.",
    "yandex_games:580873": "Move and match ordinary goods in a three-dimensional shelf-sorting game; full package includes home redecoration.",
    "yandex_games:597625": "Short oxygen-constrained dig/return run, sell loot and upgrade tools; the extra risk timer changes feel but core excavation economics is direct.",
    "yandex_games:559943": "Customers give orders; timed barista mini-games, tips and equipment progression; direct core but broader recipes/stocks/locations.",
}


def run(kind: str, suite_path: Path, unreviewed_intel_zip: Path, output_dir: Path) -> None:
    if kind not in EXPECTED:
        raise ValueError(f"unknown source cohort {kind}")
    ledger = json.loads(Path("research/hyper-sweep-2026-09-16/manual-verdicts.json").read_text(encoding="utf-8"))
    suite = load_thesis_suite(suite_path)
    expected_suite, expected_run, expected_digest = EXPECTED[kind]
    if suite.suite_id != expected_suite:
        raise ValueError("source suite mismatch")
    source_binding = json.loads(ZipFile(unreviewed_intel_zip).read("bindings/current-experiment-artifact.json"))
    if (source_binding["run_id"], source_binding["artifact_sha256"]) != (expected_run, expected_digest):
        raise ValueError("unreviewed intelligence is not bound to the frozen source archive")
    annotations = ledger[kind]
    if set(annotations) != {th.thesis_id for th in suite.theses}:
        raise ValueError("annotated thesis set differs from frozen suite")
    reviewed_at = datetime.fromisoformat(ledger["reviewed_at"].replace("Z", "+00:00"))
    output_dir.mkdir(parents=True, exist_ok=True)
    with ZipFile(unreviewed_intel_zip) as artifact:
        for thesis in suite.theses:
            semantic = AnalystSemanticEnrichmentReport.model_validate(
                json.loads(artifact.read(f"semantic/{thesis.thesis_id}.json"))
            )
            candidates = [row for row in semantic.listings if row.directness == "direct_candidate"]
            marks = annotations[thesis.thesis_id]
            categorized = {}
            for abbrev, verdict in (("C", "confirmed_direct"), ("A", "adjacent"), ("U", "unresolved")):
                for item_id in marks.get(abbrev, []):
                    pid = f"yandex_games:{item_id}"
                    if pid in categorized:
                        raise ValueError(f"duplicate review decision {pid}")
                    categorized[pid] = verdict
            known = {row.platform_listing_id for row in candidates}
            if not set(categorized).issubset(known):
                raise ValueError(f"annotated IDs outside frozen direct queue: {set(categorized) - known}")
            decisions = []
            for row in candidates:
                verdict = categorized.get(row.platform_listing_id, "not_direct")
                reason = {
                    "confirmed_direct": "direct_mechanic_and_theme",
                    "adjacent": "other",
                    "not_direct": "mechanic_mismatch",
                    "unresolved": "insufficient_context",
                }[verdict]
                note = NOTES.get(row.platform_listing_id) or {
                    "confirmed_direct": "Frozen title, description and instructions match the target atomic gameplay; hands-on and retention not established.",
                    "adjacent": "Frozen metadata shows only a partial core or broader/different reward and interaction package; not a transferable cheap exact game.",
                    "not_direct": "Title, description and available instructions describe a different core; lexical direct-candidate false positive.",
                    "unresolved": "Frozen textual metadata cannot determine whether the specific target interaction is present.",
                }[verdict]
                decisions.append(DirectnessReviewDecisionV1(
                    platform_listing_id=row.platform_listing_id,
                    analyst_verdict=verdict,
                    reason_code=reason,
                    note=note,
                    reviewed_at=reviewed_at,
                ))
            report = build_directness_review(suite, semantic, decisions=tuple(decisions))
            path = output_dir / f"{thesis.thesis_id}.json"
            path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
            print(f"{kind} {thesis.thesis_id} machine={len(candidates)} reviewed={len(report.rows)} C={sum(x.analyst_verdict == 'confirmed_direct' for x in report.rows)} A={sum(x.analyst_verdict == 'adjacent' for x in report.rows)} N={sum(x.analyst_verdict == 'not_direct' for x in report.rows)} U={sum(x.analyst_verdict == 'unresolved' for x in report.rows)} hash={report.content_hash}")


if __name__ == "__main__":
    if len(sys.argv) != 5:
        raise SystemExit("usage: build_reviews.py prior|new suite.json unreviewed-intel.zip output-directory")
    run(sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]))
