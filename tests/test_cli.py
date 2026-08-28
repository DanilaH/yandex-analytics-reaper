from __future__ import annotations

from yandex_analytics_reaper.cli import build_parser


def test_cli_parses_probe_search() -> None:
    args = build_parser().parse_args(["probe-search", "merge", "--lang", "ru"])
    assert args.command == "probe-search"
    assert args.query == "merge"
    assert args.lang == "ru"
