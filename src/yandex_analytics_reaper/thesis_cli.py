from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from yandex_analytics_reaper.analyst_workflow import AnalystExperimentError, find_repository_root
from yandex_analytics_reaper.experiment_recovery import ExperimentRecoveryError
from yandex_analytics_reaper.experiment_workers import DEFAULT_QUERY_WORKERS
from yandex_analytics_reaper.thesis_intelligence import ThesisIntelligenceError
from yandex_analytics_reaper.thesis_workflow import (
    build_thesis_intelligence_artifact,
    load_directness_reviews,
    load_thesis_suite,
    run_thesis_intelligence,
    verify_thesis_intelligence_artifact,
)


def _paths(values: Sequence[str] | None) -> tuple[Path, ...]:
    return () if values is None else tuple(Path(value) for value in values)


def _run(args: argparse.Namespace) -> None:
    result = run_thesis_intelligence(
        Path(args.suite),
        prior_artifact_paths=_paths(args.prior),
        review_paths=_paths(args.review),
        query_workers=args.workers,
    )
    print(result.model_dump_json(indent=2))


def _build(args: argparse.Namespace) -> None:
    suite_path = Path(args.suite)
    suite = load_thesis_suite(suite_path)
    reviews = load_directness_reviews(_paths(args.review))
    repository_root = find_repository_root(suite_path)
    result = build_thesis_intelligence_artifact(
        suite,
        current_artifact_path=Path(args.current),
        prior_artifact_paths=_paths(args.prior),
        reviews=reviews,
        repository_root=repository_root,
    )
    print(result.model_dump_json(indent=2))


def _verify(args: argparse.Namespace) -> None:
    result = verify_thesis_intelligence_artifact(
        Path(args.artifact),
        current_artifact_path=Path(args.current),
        prior_artifact_paths=_paths(args.prior),
    )
    print(result.model_dump_json(indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="yandex-reaper-thesis",
        description="Build and verify deterministic thesis-intelligence artifacts.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser(
        "run",
        help="Compile a thesis suite, delegate collection to the existing experiment runner, then build intelligence.",
    )
    run.add_argument("suite", help="Path to one thesis-suite-v1 JSON declaration.")
    run.add_argument(
        "--prior",
        action="append",
        default=[],
        help="Prior immutable experiment ZIP. Repeat for multiple history artifacts.",
    )
    run.add_argument(
        "--review",
        action="append",
        default=[],
        help="Analyst directness-review JSON. Repeat for multiple theses.",
    )
    run.add_argument(
        "--workers",
        type=int,
        choices=range(1, 5),
        default=DEFAULT_QUERY_WORKERS,
        help="Existing experiment-runner exact-query workers (1-4; default: 4).",
    )
    run.set_defaults(handler=_run)

    build = sub.add_parser(
        "build",
        help="Build intelligence offline from one verified current experiment ZIP.",
    )
    build.add_argument("suite", help="Path to one thesis-suite-v1 JSON declaration.")
    build.add_argument("current", help="Current immutable experiment ZIP.")
    build.add_argument(
        "--prior",
        action="append",
        default=[],
        help="Prior immutable experiment ZIP. Repeat for multiple history artifacts.",
    )
    build.add_argument(
        "--review",
        action="append",
        default=[],
        help="Analyst directness-review JSON. Repeat for multiple theses.",
    )
    build.set_defaults(handler=_build)

    verify = sub.add_parser(
        "verify",
        help="Verify the intelligence ZIP and rebuild it from explicit frozen experiment sources.",
    )
    verify.add_argument("artifact", help="Final thesis-intelligence ZIP.")
    verify.add_argument(
        "--current",
        required=True,
        help="Exact current immutable experiment ZIP bound to the intelligence artifact.",
    )
    verify.add_argument(
        "--prior",
        action="append",
        default=[],
        help="Prior immutable experiment ZIP. Repeat for multiple history artifacts.",
    )
    verify.set_defaults(handler=_verify)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        handler = args.handler
        handler(args)
    except (
        OSError,
        ValueError,
        ThesisIntelligenceError,
        AnalystExperimentError,
        ExperimentRecoveryError,
    ) as exc:
        raise SystemExit(str(exc)) from exc
