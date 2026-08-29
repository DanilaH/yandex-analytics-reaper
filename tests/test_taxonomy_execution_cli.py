from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel

from yandex_analytics_reaper.taxonomy_execution_cli import _emit_report, build_parser


class _ExampleReport(BaseModel):
    value: int


def test_taxonomy_execution_cli_parses_annotation_validation() -> None:
    args = build_parser().parse_args(
        [
            "validate-annotation-batch",
            "sample.json",
            "annotator-a.json",
            "--report",
            "data/reports/annotator-a.validated.json",
        ]
    )

    assert args.command == "validate-annotation-batch"
    assert args.sample == "sample.json"
    assert args.batch == "annotator-a.json"
    assert args.report == "data/reports/annotator-a.validated.json"


def test_taxonomy_execution_cli_parses_gold_set_build() -> None:
    args = build_parser().parse_args(
        [
            "build-gold-set",
            "sample.json",
            "gold-declaration.json",
            "annotator-a.json",
            "annotator-b.json",
            "--report",
            "data/reports/gold.json",
        ]
    )

    assert args.command == "build-gold-set"
    assert args.sample == "sample.json"
    assert args.declaration == "gold-declaration.json"
    assert args.batches == ["annotator-a.json", "annotator-b.json"]
    assert args.report == "data/reports/gold.json"


def test_taxonomy_execution_cli_parses_primary_validation() -> None:
    args = build_parser().parse_args(
        [
            "build-primary-validation",
            "sample.json",
            "gold.json",
            "primary-review.json",
        ]
    )

    assert args.command == "build-primary-validation"
    assert args.sample == "sample.json"
    assert args.gold_set == "gold.json"
    assert args.declaration == "primary-review.json"
    assert args.report is None


def test_taxonomy_execution_cli_parses_agreement_analysis() -> None:
    args = build_parser().parse_args(
        [
            "analyze-primary-agreement",
            "sample.json",
            "gold.json",
            "annotator-a.json",
            "annotator-b.json",
        ]
    )

    assert args.command == "analyze-primary-agreement"
    assert args.sample == "sample.json"
    assert args.gold_set == "gold.json"
    assert args.batches == ["annotator-a.json", "annotator-b.json"]
    assert args.report is None


def test_emit_report_writes_new_file_and_never_overwrites(tmp_path: Path) -> None:
    output = tmp_path / "reports" / "artifact.json"
    report = _ExampleReport(value=7)

    _emit_report(report, str(output))

    assert output.read_text(encoding="utf-8") == '{\n  "value": 7\n}\n'
    with pytest.raises(SystemExit, match="report already exists"):
        _emit_report(report, str(output))


def test_emit_report_defaults_to_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    _emit_report(_ExampleReport(value=9), None)

    assert capsys.readouterr().out == '{\n  "value": 9\n}\n'
