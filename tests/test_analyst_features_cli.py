from __future__ import annotations

from yandex_analytics_reaper.analyst_cli import build_parser


def test_analyst_cli_parses_market_feature_command() -> None:
    args = build_parser().parse_args(
        [
            "build-market-features",
            "snapshot-report.json",
            "market-export.json",
            "--report",
            "market-features.json",
        ]
    )

    assert args.command == "build-market-features"
    assert args.snapshot_report == "snapshot-report.json"
    assert args.market_export == "market-export.json"
    assert args.report == "market-features.json"
