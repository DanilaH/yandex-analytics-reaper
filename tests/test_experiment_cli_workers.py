from __future__ import annotations

import pytest

from yandex_analytics_reaper.experiment_cli import build_parser


def test_run_and_resume_default_to_four_workers() -> None:
    parser = build_parser()
    assert parser.parse_args(["run", "manifest.json"]).workers == 4
    assert parser.parse_args(["resume", "workdir"]).workers == 4


def test_worker_override_is_available_to_run_and_resume() -> None:
    parser = build_parser()
    assert parser.parse_args(["run", "manifest.json", "--workers", "1"]).workers == 1
    assert parser.parse_args(["resume", "workdir", "--workers", "3"]).workers == 3


@pytest.mark.parametrize("workers", ["0", "5"])
def test_cli_rejects_out_of_range_workers(workers: str) -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["run", "manifest.json", "--workers", workers])
