from __future__ import annotations

import pytest

from yandex_analytics_reaper.thesis_cli import build_parser


def test_run_parser_accepts_repeatable_prior_review_and_workers() -> None:
    args = build_parser().parse_args(
        [
            "run",
            "suite.json",
            "--prior",
            "older.zip",
            "--prior",
            "newer.zip",
            "--review",
            "headphones.json",
            "--review",
            "digicam.json",
            "--workers",
            "3",
        ]
    )

    assert args.command == "run"
    assert args.suite == "suite.json"
    assert args.prior == ["older.zip", "newer.zip"]
    assert args.review == ["headphones.json", "digicam.json"]
    assert args.workers == 3


def test_build_parser_has_offline_current_and_repeatable_inputs() -> None:
    args = build_parser().parse_args(
        [
            "build",
            "suite.json",
            "current.zip",
            "--prior",
            "prior.zip",
            "--review",
            "review.json",
        ]
    )

    assert args.command == "build"
    assert args.suite == "suite.json"
    assert args.current == "current.zip"
    assert args.prior == ["prior.zip"]
    assert args.review == ["review.json"]


def test_verify_requires_explicit_current_source() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["verify", "intelligence.zip"])

    args = build_parser().parse_args(
        [
            "verify",
            "intelligence.zip",
            "--current",
            "current.zip",
            "--prior",
            "prior-a.zip",
            "--prior",
            "prior-b.zip",
        ]
    )
    assert args.artifact == "intelligence.zip"
    assert args.current == "current.zip"
    assert args.prior == ["prior-a.zip", "prior-b.zip"]


def test_run_workers_remain_existing_runner_bounds() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["run", "suite.json", "--workers", "5"])
