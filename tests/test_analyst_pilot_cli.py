from __future__ import annotations

from yandex_analytics_reaper.analyst_cli import build_parser


def test_analyst_cli_parses_pilot_verification_command() -> None:
    args = build_parser().parse_args(
        [
            "verify-pilot",
            "snapshot.json",
            "market-export.json",
            "market-features.json",
            "--report",
            "pilot-verification.json",
            "--output",
            "data/raw",
        ]
    )

    assert args.command == "verify-pilot"
    assert args.snapshot_report == "snapshot.json"
    assert args.market_export == "market-export.json"
    assert args.market_features == "market-features.json"
    assert args.report == "pilot-verification.json"
    assert args.output == "data/raw"