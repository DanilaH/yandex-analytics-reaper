from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel

from yandex_analytics_reaper.taxonomy import (
    PrimaryArchetypeValidationDeclaration,
    TaxonomyAnnotationBatch,
    TaxonomyDiversitySampleReport,
    TaxonomyGoldSetDeclaration,
    TaxonomyGoldSetReport,
    build_controlled_dimension_agreement_report,
    build_primary_archetype_agreement_report,
    build_primary_archetype_validation_report,
    build_taxonomy_gold_set,
    validate_taxonomy_annotation_batch,
)


def _load_model[ModelT: BaseModel](path_value: str, model_type: type[ModelT]) -> ModelT:
    path = Path(path_value)
    try:
        payload = path.read_text(encoding="utf-8")
        return model_type.model_validate_json(payload)
    except (OSError, ValueError) as exc:
        raise SystemExit(f"cannot load {model_type.__name__} from {path}: {exc}") from exc


def _emit_report(report: BaseModel, report_path: str | None) -> None:
    payload = report.model_dump_json(indent=2) + "\n"
    if report_path is None:
        print(payload, end="")
        return

    path = Path(report_path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
    except FileExistsError as exc:
        raise SystemExit(
            f"report already exists: {path}; choose a new path rather than overwriting evidence"
        ) from exc
    except OSError as exc:
        raise SystemExit(f"cannot write report {path}: {exc}") from exc
    print(f"report={path}")


def _validate_annotation_batch(args: argparse.Namespace) -> None:
    sample = _load_model(args.sample, TaxonomyDiversitySampleReport)
    batch = _load_model(args.batch, TaxonomyAnnotationBatch)
    try:
        report = validate_taxonomy_annotation_batch(sample, batch)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    _emit_report(report, args.report)


def _build_gold_set(args: argparse.Namespace) -> None:
    sample = _load_model(args.sample, TaxonomyDiversitySampleReport)
    declaration = _load_model(args.declaration, TaxonomyGoldSetDeclaration)
    batches = tuple(_load_model(path, TaxonomyAnnotationBatch) for path in args.batches)
    try:
        report = build_taxonomy_gold_set(sample, declaration, batches)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    _emit_report(report, args.report)


def _build_primary_validation(args: argparse.Namespace) -> None:
    sample = _load_model(args.sample, TaxonomyDiversitySampleReport)
    gold_set = _load_model(args.gold_set, TaxonomyGoldSetReport)
    declaration = _load_model(args.declaration, PrimaryArchetypeValidationDeclaration)
    try:
        report = build_primary_archetype_validation_report(sample, gold_set, declaration)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    _emit_report(report, args.report)


def _analyze_primary_agreement(args: argparse.Namespace) -> None:
    sample = _load_model(args.sample, TaxonomyDiversitySampleReport)
    gold_set = _load_model(args.gold_set, TaxonomyGoldSetReport)
    batches = tuple(_load_model(path, TaxonomyAnnotationBatch) for path in args.batches)
    try:
        report = build_primary_archetype_agreement_report(sample, gold_set, batches)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    _emit_report(report, args.report)


def _analyze_controlled_agreement(args: argparse.Namespace) -> None:
    sample = _load_model(args.sample, TaxonomyDiversitySampleReport)
    gold_set = _load_model(args.gold_set, TaxonomyGoldSetReport)
    batches = tuple(_load_model(path, TaxonomyAnnotationBatch) for path in args.batches)
    try:
        report = build_controlled_dimension_agreement_report(sample, gold_set, batches)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    _emit_report(report, args.report)


def _add_report_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--report",
        help=(
            "Write the validated JSON artifact to this new path. Existing files are never "
            "overwritten. Without --report, JSON is written to stdout."
        ),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="yandex-reaper-taxonomy",
        description=(
            "Offline file-in/file-out execution surface for frozen Phase 3 taxonomy artifacts."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    annotation = sub.add_parser(
        "validate-annotation-batch",
        help="Validate one manual annotation batch against one exact taxonomy sample.",
    )
    annotation.add_argument("sample", help="Path to taxonomy-diversity-sample-v1 report JSON.")
    annotation.add_argument("batch", help="Path to taxonomy-manual-annotation-v1 batch JSON.")
    _add_report_argument(annotation)
    annotation.set_defaults(handler=_validate_annotation_batch)

    gold = sub.add_parser(
        "build-gold-set",
        help="Build one adjudicated gold-set artifact from exact independent source batches.",
    )
    gold.add_argument("sample", help="Path to taxonomy-diversity-sample-v1 report JSON.")
    gold.add_argument("declaration", help="Path to taxonomy-gold-set-v1 declaration JSON.")
    gold.add_argument(
        "batches",
        nargs="+",
        help="Source annotation batch JSON paths referenced by the declaration.",
    )
    _add_report_argument(gold)
    gold.set_defaults(handler=_build_gold_set)

    primary_validation = sub.add_parser(
        "build-primary-validation",
        help="Build the frozen primary-archetype review report from exact real artifacts.",
    )
    primary_validation.add_argument(
        "sample",
        help="Path to taxonomy-diversity-sample-v1 report JSON.",
    )
    primary_validation.add_argument("gold_set", help="Path to taxonomy-gold-set-v1 report JSON.")
    primary_validation.add_argument(
        "declaration",
        help="Path to taxonomy-primary-archetype-validation-v1 declaration JSON.",
    )
    _add_report_argument(primary_validation)
    primary_validation.set_defaults(handler=_build_primary_validation)

    primary_agreement = sub.add_parser(
        "analyze-primary-agreement",
        help="Analyze primary-archetype agreement for exact gold-bound source batches.",
    )
    primary_agreement.add_argument(
        "sample",
        help="Path to taxonomy-diversity-sample-v1 report JSON.",
    )
    primary_agreement.add_argument(
        "gold_set",
        help="Path to taxonomy-gold-set-v1 report JSON.",
    )
    primary_agreement.add_argument(
        "batches",
        nargs="+",
        help="Source annotation batch JSON paths in exact gold-set source-batch order.",
    )
    _add_report_argument(primary_agreement)
    primary_agreement.set_defaults(handler=_analyze_primary_agreement)

    controlled_agreement = sub.add_parser(
        "analyze-controlled-agreement",
        help="Analyze exact-set agreement for the four frozen controlled dimensions.",
    )
    controlled_agreement.add_argument(
        "sample",
        help="Path to taxonomy-diversity-sample-v1 report JSON.",
    )
    controlled_agreement.add_argument(
        "gold_set",
        help="Path to taxonomy-gold-set-v1 report JSON.",
    )
    controlled_agreement.add_argument(
        "batches",
        nargs="+",
        help="Source annotation batch JSON paths in exact gold-set source-batch order.",
    )
    _add_report_argument(controlled_agreement)
    controlled_agreement.set_defaults(handler=_analyze_controlled_agreement)

    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    handler = args.handler
    handler(args)


if __name__ == "__main__":
    main()
