from __future__ import annotations

import argparse
from pathlib import Path

from pydantic import ValidationError

from yandex_analytics_reaper.config import load_settings
from yandex_analytics_reaper.ingestion import (
    RichMetadataCollectionError,
    YandexNormalizationPersistence,
    YandexRichMetadataCollector,
)
from yandex_analytics_reaper.point_observation import (
    ListingObservationArtifactCollector,
    ListingObservationError,
    ListingObservationSetDeclaration,
    verify_listing_observation_artifact,
)
from yandex_analytics_reaper.schema_drift import SQLiteSchemaDriftRegistry
from yandex_analytics_reaper.sources.yandex import YandexPublicClient
from yandex_analytics_reaper.storage import FilesystemRawSnapshotStore


def _raw_store(raw_root: str | None) -> FilesystemRawSnapshotStore:
    settings = load_settings()
    root = Path(raw_root) if raw_root else settings.data_dir / "raw"
    return FilesystemRawSnapshotStore(root)


def _run(args: argparse.Namespace) -> None:
    declaration_path = Path(args.declaration)
    artifact_path = Path(args.artifact)
    try:
        declaration = ListingObservationSetDeclaration.model_validate_json(
            declaration_path.read_text(encoding="utf-8")
        )
    except (OSError, ValidationError) as exc:
        raise SystemExit(f"invalid observation declaration: {exc}") from exc

    store = _raw_store(args.raw_root)
    database_path = store.root.parent / "market.sqlite3"
    settings = load_settings()
    try:
        with YandexPublicClient(
            base_url=settings.yandex_base_url,
            timeout_seconds=settings.http_timeout_seconds,
            user_agent=settings.user_agent,
        ) as client:
            rich = YandexRichMetadataCollector(
                client=client,
                raw_store=store,
                schema_registry=SQLiteSchemaDriftRegistry(database_path),
                persistence=YandexNormalizationPersistence(database_path),
            )
            verification = ListingObservationArtifactCollector(
                rich_collector=rich,
                raw_store=store,
            ).collect(declaration, artifact_path)
    except (ListingObservationError, RichMetadataCollectionError, OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    print(verification.model_dump_json(indent=2))


def _verify(args: argparse.Namespace) -> None:
    try:
        verification = verify_listing_observation_artifact(Path(args.artifact))
    except ListingObservationError as exc:
        raise SystemExit(str(exc)) from exc
    print(verification.model_dump_json(indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="yandex-reaper-observe",
        description="Collect and verify immutable exact-ID Yandex listing observations.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Collect one exact-ID cohort into a create-only artifact.")
    run.add_argument("declaration", help="Path to listing-observation-set-v1 JSON declaration.")
    run.add_argument("artifact", help="Create-only output ZIP path.")
    run.add_argument(
        "--raw-root",
        help="Raw snapshot root. Defaults to REAPER_DATA_DIR/raw.",
    )
    run.set_defaults(handler=_run)

    verify = sub.add_parser("verify", help="Offline-verify one observation artifact.")
    verify.add_argument("artifact", help="Observation artifact ZIP path.")
    verify.set_defaults(handler=_verify)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    args.handler(args)


if __name__ == "__main__":
    main()
