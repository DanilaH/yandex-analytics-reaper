from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from yandex_analytics_reaper.analyst import (
    AnalystSemanticEnricher,
    AnalystSemanticThesisDeclaration,
    AnalystSnapshotReport,
    validate_analyst_semantic_enrichment,
    write_analyst_semantic_csv,
)
from yandex_analytics_reaper.config import load_settings
from yandex_analytics_reaper.storage import FilesystemRawSnapshotStore


def _raw_store(output: str | None) -> FilesystemRawSnapshotStore:
    settings = load_settings()
    root = Path(output) if output else settings.data_dir / "raw"
    return FilesystemRawSnapshotStore(root)


def _read_text(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(str(exc)) from exc


def _write_report(path: str, content: str) -> None:
    report_path = Path(path)
    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with report_path.open("x", encoding="utf-8") as handle:
            handle.write(content)
            handle.write("\n")
    except FileExistsError as exc:
        raise SystemExit(
            f"report already exists: {report_path}; choose a new output path"
        ) from exc
    except OSError as exc:
        raise SystemExit(str(exc)) from exc


def _build(args: argparse.Namespace) -> None:
    raw_store = _raw_store(args.output)
    try:
        snapshot = AnalystSnapshotReport.model_validate_json(_read_text(args.snapshot_report))
        thesis = AnalystSemanticThesisDeclaration.model_validate_json(
            _read_text(args.thesis_declaration)
        )
        report = AnalystSemanticEnricher(raw_store=raw_store).build(snapshot, thesis)
        report = validate_analyst_semantic_enrichment(report)
        _write_report(args.report, report.model_dump_json(indent=2))
        if args.csv is not None:
            write_analyst_semantic_csv(report, Path(args.csv))
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    print(
        f"semantic_enrichment={report.snapshot_id} "
        f"thesis={report.thesis.thesis_id}@{report.thesis.version} "
        f"content_hash={report.content_hash}"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="yandex-reaper-semantic",
        description=(
            "Replay frozen Yandex get_games metadata into a transparent semantic/directness "
            "triage artifact."
        ),
    )
    parser.add_argument("snapshot_report", help="Path to an AnalystSnapshotReport JSON file.")
    parser.add_argument(
        "thesis_declaration",
        help="Path to an analyst-semantic-thesis-v1 JSON declaration.",
    )
    parser.add_argument("--report", required=True, help="Create-only enrichment report JSON path.")
    parser.add_argument("--csv", help="Optional create-only analyst-readable CSV path.")
    parser.add_argument(
        "--output",
        help="Raw snapshot root. Defaults to REAPER_DATA_DIR/raw.",
    )
    parser.set_defaults(handler=_build)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    handler = args.handler
    handler(args)
