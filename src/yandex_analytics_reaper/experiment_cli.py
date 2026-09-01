from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from yandex_analytics_reaper.analyst_workflow import (
    AnalystExperimentError,
    resume_analyst_experiment,
    run_analyst_experiment,
)
from yandex_analytics_reaper.experiment_workers import DEFAULT_QUERY_WORKERS


def _run(args: argparse.Namespace) -> None:
    try:
        result = run_analyst_experiment(Path(args.manifest), query_workers=args.workers)
    except (OSError, ValueError, AnalystExperimentError) as exc:
        raise SystemExit(str(exc)) from exc
    print(result.model_dump_json(indent=2))


def _resume(args: argparse.Namespace) -> None:
    try:
        result = resume_analyst_experiment(Path(args.workdir), query_workers=args.workers)
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
    run.add_argument(
        "--workers",
        type=int,
        choices=range(1, 5),
        default=DEFAULT_QUERY_WORKERS,
        help="Concurrent exact-query workers (1-4; default: 4).",
    )
    run.set_defaults(handler=_run)
    resume = sub.add_parser("resume", help="Resume one preserved v1.2 workdir.")
    resume.add_argument("workdir", help="Path to artifacts/work/<experiment>/<run>.")
    resume.add_argument(
        "--workers",
        type=int,
        choices=range(1, 5),
        default=DEFAULT_QUERY_WORKERS,
        help="Concurrent exact-query workers (1-4; default: 4).",
    )
    resume.set_defaults(handler=_resume)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    handler = args.handler
    handler(args)
