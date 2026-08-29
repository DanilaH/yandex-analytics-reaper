from __future__ import annotations

from yandex_analytics_reaper.cli import build_parser


def test_cli_parses_probe_search() -> None:
    args = build_parser().parse_args(
        [
            "probe-search",
            "merge",
            "--lang",
            "ru",
            "--pages",
            "3",
            "--session-profile",
            "persistent_anonymous",
        ]
    )
    assert args.command == "probe-search"
    assert args.query == "merge"
    assert args.lang == "ru"
    assert args.pages == 3
    assert args.session_profile == "persistent_anonymous"


def test_cli_feed_defaults_to_single_page_and_clean_session() -> None:
    args = build_parser().parse_args(["probe-feed"])
    assert args.command == "probe-feed"
    assert args.pages == 1
    assert args.session_profile == "clean_anonymous"


def test_cli_parses_explicit_feed_depth_run_ids() -> None:
    args = build_parser().parse_args(
        ["analyze-feed-depth", "probe:one", "probe:two", "--output", "data/raw"]
    )
    assert args.command == "analyze-feed-depth"
    assert args.run_ids == ["probe:one", "probe:two"]
    assert args.output == "data/raw"


def test_cli_parses_explicit_session_profile_blocks() -> None:
    args = build_parser().parse_args(
        [
            "analyze-session-profile-stability",
            "--block",
            "probe:one",
            "probe:two",
            "probe:three",
            "probe:four",
            "--block",
            "probe:five",
            "probe:six",
            "probe:seven",
            "probe:eight",
            "--output",
            "data/raw",
        ]
    )
    assert args.command == "analyze-session-profile-stability"
    assert args.blocks == [
        ["probe:one", "probe:two", "probe:three", "probe:four"],
        ["probe:five", "probe:six", "probe:seven", "probe:eight"],
    ]
    assert args.output == "data/raw"


def test_cli_parses_collection_cadence_manifest() -> None:
    args = build_parser().parse_args(
        [
            "analyze-collection-cadence",
            "cadence-manifest.json",
            "--output",
            "data/raw",
        ]
    )

    assert args.command == "analyze-collection-cadence"
    assert args.manifest == "cadence-manifest.json"
    assert args.output == "data/raw"
