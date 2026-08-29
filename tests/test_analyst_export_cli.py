from __future__ import annotations

from yandex_analytics_reaper.analyst_cli import build_parser


def test_analyst_cli_parses_snapshot_export_command() -> None:
    args = build_parser().parse_args(
        [
            "export-snapshot",
            "snapshot-report.json",
            "--report",
            "market-export.json",
            "--csv-dir",
            "market-export-csv",
            "--output",
            "data/raw",
        ]
    )

    assert args.command == "export-snapshot"
    assert args.snapshot_report == "snapshot-report.json"
    assert args.report == "market-export.json"
    assert args.csv_dir == "market-export-csv"
    assert args.output == "data/raw"
