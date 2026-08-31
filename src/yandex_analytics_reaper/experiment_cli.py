from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from yandex_analytics_reaper.analyst_workflow import (
    AnalystExperimentError,
    run_analyst_experiment,
)


def _run(args: argparse.Namespace) -> None:
    try:
        result = run_analyst_experiment(Path(args.manifest))
    except (OSError, ValueError, AnalystExperimentError) as exc:
        raise SystemExit(str(exc)) from exc
    print(result.model_dump_json(indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="yandex-reaper-experiment",
        description="Run one declarative analyst experiment end-to-end.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="Run one versioned JSON experiment manifest.")
    run.add_argument("manifest", help="Path to the experiment manifest JSON.")
    run.set_defaults(handler=_run)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    handler = args.handler
    handler(args)
