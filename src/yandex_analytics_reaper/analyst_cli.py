from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from yandex_analytics_reaper.analyst import (
    AnalystMarketExportReport,
    AnalystMarketExporter,
    AnalystMarketFeatureBuilder,
    AnalystSnapshotBuilder,
    AnalystSnapshotDeclaration,
    AnalystSnapshotReport,
    validate_analyst_market_export,
    validate_analyst_market_features,
    write_analyst_export_csv,
)
from yandex_analytics_reaper.comparables import YandexSearchComparableSetBuilder
from yandex_analytics_reaper.config import load_settings
from yandex_analytics_reaper.domain import QueryFamilyVersion
from yandex_analytics_reaper.storage import (
    FilesystemRawSnapshotStore,
    SQLiteComparableSetStore,
    SQLiteProbeRunStore,
    SQLiteQueryFamilyStore,
)


class SearchComparableSetDeclaration(BaseModel):
    """Explicit file input for one reproducible yandex_search_union_v1 build."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    construction_method: Literal["yandex_search_union_v1"]
    set_id: str
    version: int = Field(ge=1)
    query_family_id: str
    query_family_version: int = Field(ge=1)
    created_at: AwareDatetime
    run_ids: tuple[str, ...] = Field(min_length=1)

    @field_validator("set_id", "query_family_id")
    @classmethod
    def validate_trimmed_non_blank(cls, value: str) -> str:
        if not value:
            raise ValueError("declaration identifiers cannot be blank")
        if value != value.strip():
            raise ValueError("declaration identifiers must already be trimmed")
        return value

    @model_validator(mode="after")
    def validate_run_ids(self) -> SearchComparableSetDeclaration:
        if any(not run_id or run_id != run_id.strip() for run_id in self.run_ids):
            raise ValueError("run_ids must be non-blank and already trimmed")
        if len(set(self.run_ids)) != len(self.run_ids):
            raise ValueError("run_ids must be unique")
        return self


def _raw_store(output: str | None) -> FilesystemRawSnapshotStore:
    settings = load_settings()
    root = Path(output) if output else settings.data_dir / "raw"
    return FilesystemRawSnapshotStore(root)


def _database_path(raw_store: FilesystemRawSnapshotStore) -> Path:
    return raw_store.root.parent / "market.sqlite3"


def _read_text(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(str(exc)) from exc


def _write_report(path: str, content: str) -> None:
    report_path = Path(path)
    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with report_path.open("x", encoding="utf-8") as handle:
            handle.write(content)
            handle.write("\n")
    except FileExistsError as exc:
        raise SystemExit(
            f"report already exists: {report_path}; choose a new output path"
        ) from exc
    except OSError as exc:
        raise SystemExit(str(exc)) from exc


def _persist_query_family(args: argparse.Namespace) -> None:
    raw_store = _raw_store(args.output)
    try:
        family = QueryFamilyVersion.model_validate_json(_read_text(args.declaration))
        stored = SQLiteQueryFamilyStore(_database_path(raw_store)).persist(family)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(stored.model_dump_json(indent=2))


def _build_search_comparable_set(args: argparse.Namespace) -> None:
    raw_store = _raw_store(args.output)
    database_path = _database_path(raw_store)
    if not database_path.is_file():
        raise SystemExit(
            f"operational database not found: {database_path}; "
            "persist the query family and collect its search runs first"
        )

    try:
        declaration = SearchComparableSetDeclaration.model_validate_json(
            _read_text(args.declaration)
        )
        family = SQLiteQueryFamilyStore(database_path).get(
            declaration.query_family_id,
            declaration.query_family_version,
        )
        if family is None:
            raise ValueError(
                "referenced query-family version is not persisted: "
                f"{declaration.query_family_id}@{declaration.query_family_version}"
            )
        comparable_set = YandexSearchComparableSetBuilder(
            raw_store=raw_store,
            probe_store=SQLiteProbeRunStore(database_path),
        ).build(
            family,
            declaration.run_ids,
            set_id=declaration.set_id,
            version=declaration.version,
            created_at=declaration.created_at,
        )
        stored = SQLiteComparableSetStore(database_path).persist(comparable_set)
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    print(stored.model_dump_json(indent=2))


def _build_snapshot(args: argparse.Namespace) -> None:
    raw_store = _raw_store(args.output)
    database_path = _database_path(raw_store)
    if not database_path.is_file():
        raise SystemExit(
            f"operational database not found: {database_path}; "
            "persist comparable/search evidence before building an analyst snapshot"
        )
    try:
        declaration = AnalystSnapshotDeclaration.model_validate_json(
            _read_text(args.declaration)
        )
        report = AnalystSnapshotBuilder(
            raw_store=raw_store,
            database_path=database_path,
        ).build(declaration)
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    _write_report(args.report, report.model_dump_json(indent=2))
    print(f"analyst_snapshot={report.snapshot_id} content_hash={report.content_hash}")


def _export_snapshot(args: argparse.Namespace) -> None:
    raw_store = _raw_store(args.output)
    database_path = _database_path(raw_store)
    if not database_path.is_file():
        raise SystemExit(f"operational database not found: {database_path}")
    try:
        snapshot = AnalystSnapshotReport.model_validate_json(_read_text(args.snapshot_report))
        export = AnalystMarketExporter(
            raw_store=raw_store,
            database_path=database_path,
        ).build(snapshot)
        export = validate_analyst_market_export(export)
        _write_report(args.report, export.model_dump_json(indent=2))
        if args.csv_dir is not None:
            write_analyst_export_csv(export, Path(args.csv_dir))
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    print(f"analyst_export={export.snapshot_id} content_hash={export.content_hash}")


def _build_market_features(args: argparse.Namespace) -> None:
    try:
        snapshot = AnalystSnapshotReport.model_validate_json(_read_text(args.snapshot_report))
        market_export = AnalystMarketExportReport.model_validate_json(
            _read_text(args.market_export)
        )
        report = AnalystMarketFeatureBuilder().build(snapshot, market_export)
        report = validate_analyst_market_features(report)
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    _write_report(args.report, report.model_dump_json(indent=2))
    print(f"analyst_features={report.snapshot_id} content_hash={report.content_hash}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="yandex-reaper-analyst",
        description=(
            "Offline operator workflow over persisted Yandex evidence. "
            "See docs/analyst-workflow.md."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    family = sub.add_parser(
        "persist-query-family",
        help="Validate and persist one immutable QueryFamilyVersion JSON declaration.",
    )
    family.add_argument("declaration", help="Path to a QueryFamilyVersion JSON file.")
    family.add_argument("--output", help="Raw snapshot root. Defaults to REAPER_DATA_DIR/raw.")
    family.set_defaults(handler=_persist_query_family)

    comparable = sub.add_parser(
        "build-search-comparable-set",
        help="Replay explicit completed search runs into yandex_search_union_v1.",
    )
    comparable.add_argument(
        "declaration",
        help="Path to a SearchComparableSetDeclaration JSON file.",
    )
    comparable.add_argument(
        "--output",
        help="Raw snapshot root. Defaults to REAPER_DATA_DIR/raw.",
    )
    comparable.set_defaults(handler=_build_search_comparable_set)

    snapshot = sub.add_parser(
        "build-snapshot",
        help="Bind comparable/feed/rich-metadata evidence into analyst-snapshot-v1.",
    )
    snapshot.add_argument("declaration", help="Path to an AnalystSnapshotDeclaration JSON file.")
    snapshot.add_argument("--report", required=True, help="Create-only snapshot report JSON path.")
    snapshot.add_argument(
        "--output",
        help="Raw snapshot root. Defaults to REAPER_DATA_DIR/raw.",
    )
    snapshot.set_defaults(handler=_build_snapshot)

    export = sub.add_parser(
        "export-snapshot",
        help="Build analyst-market-export-v1 from one frozen analyst snapshot report.",
    )
    export.add_argument("snapshot_report", help="Path to an AnalystSnapshotReport JSON file.")
    export.add_argument("--report", required=True, help="Create-only market export JSON path.")
    export.add_argument(
        "--csv-dir",
        help="Optional create-only directory for analyst-readable CSV tables.",
    )
    export.add_argument(
        "--output",
        help="Raw snapshot root. Defaults to REAPER_DATA_DIR/raw.",
    )
    export.set_defaults(handler=_export_snapshot)

    features = sub.add_parser(
        "build-market-features",
        help="Build analyst-market-features-v1 from frozen snapshot/export JSON files.",
    )
    features.add_argument("snapshot_report", help="Path to an AnalystSnapshotReport JSON file.")
    features.add_argument("market_export", help="Path to an AnalystMarketExportReport JSON file.")
    features.add_argument("--report", required=True, help="Create-only feature report JSON path.")
    features.set_defaults(handler=_build_market_features)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    handler = args.handler
    handler(args)
