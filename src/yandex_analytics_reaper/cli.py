from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from yandex_analytics_reaper.config import load_settings
from yandex_analytics_reaper.domain import ProbeContext, SessionProfile
from yandex_analytics_reaper.experiments import (
    CollectionCadenceExperiment,
    CollectionCadenceManifest,
    CollectionCadencePlanDeclaration,
    CollectionCadencePlanFreezer,
    FeedDepthExperiment,
    SessionProfileStabilityExperiment,
)
from yandex_analytics_reaper.ingestion import (
    ProbeCollectionError,
    SessionConfigurationError,
    SessionStateError,
    YandexNormalizationPersistence,
    YandexPaginatedProbeRunner,
    YandexSessionManager,
)
from yandex_analytics_reaper.schema_drift import DriftSeverity, SQLiteSchemaDriftRegistry
from yandex_analytics_reaper.sources.capabilities import CollectedResponse
from yandex_analytics_reaper.sources.yandex import (
    YandexGetGamesParser,
    YandexPlayPageParser,
    YandexPublicClient,
)
from yandex_analytics_reaper.sources.yandex.schema_contracts import (
    schema_comparison_scope_for_snapshot,
    schema_contract_for_request,
)
from yandex_analytics_reaper.storage import (
    FilesystemRawSnapshotStore,
    RawSnapshotMetadata,
    SQLiteProbeRunStore,
)


def _context(args: argparse.Namespace) -> ProbeContext:
    return ProbeContext(
        language=args.lang,
        device_type=args.device,
        platform=args.platform,
        session_profile=SessionProfile(args.session_profile),
    )


def _store(output: str | None) -> FilesystemRawSnapshotStore:
    settings = load_settings()
    root = Path(output) if output else settings.data_dir / "raw"
    return FilesystemRawSnapshotStore(root)


def _database_path(store: FilesystemRawSnapshotStore) -> Path:
    return store.root.parent / "market.sqlite3"


def _schema_registry(store: FilesystemRawSnapshotStore) -> SQLiteSchemaDriftRegistry:
    return SQLiteSchemaDriftRegistry(_database_path(store))


def _client() -> YandexPublicClient:
    settings = load_settings()
    return YandexPublicClient(
        base_url=settings.yandex_base_url,
        timeout_seconds=settings.http_timeout_seconds,
        user_agent=settings.user_agent,
    )


def _session_manager(store: FilesystemRawSnapshotStore) -> YandexSessionManager:
    settings = load_settings()
    return YandexSessionManager(
        state_root=store.root.parent / "sessions",
        base_url=settings.yandex_base_url,
        timeout_seconds=settings.http_timeout_seconds,
        user_agent=settings.user_agent,
    )


def _persist_or_fail(
    store: FilesystemRawSnapshotStore,
    response: CollectedResponse,
) -> RawSnapshotMetadata:
    metadata = store.persist(response)
    print(f"raw_snapshot={metadata.id} status={response.status_code}")
    if not 200 <= response.status_code < 300:
        raise SystemExit(f"source returned HTTP {response.status_code}; raw response was preserved")
    return metadata


def _observe_json_schema(
    store: FilesystemRawSnapshotStore,
    metadata: RawSnapshotMetadata,
    response: CollectedResponse,
) -> None:
    registry = _schema_registry(store)
    analysis = registry.observe_json(
        metadata,
        response.body,
        comparison_scope_id=schema_comparison_scope_for_snapshot(metadata),
        contract=schema_contract_for_request(metadata.request_key),
    )
    if analysis.events:
        print(
            json.dumps(
                {
                    "schema_analysis": analysis.analysis_id,
                    "events": [
                        {
                            "severity": event.severity.value,
                            "kind": event.kind.value,
                            "field": event.field_path,
                            "message": event.message,
                        }
                        for event in analysis.events
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    if any(event.severity is DriftSeverity.BREAKING for event in analysis.events):
        raise SystemExit(
            "breaking source-schema drift detected; raw response and drift analysis were preserved"
        )


def _record_parser_failure(
    store: FilesystemRawSnapshotStore,
    metadata: RawSnapshotMetadata,
    *,
    parser_name: str,
    parser_version: str,
    error: ValueError,
) -> None:
    analysis = _schema_registry(store).record_parser_failure(
        metadata,
        comparison_scope_id=schema_comparison_scope_for_snapshot(metadata),
        parser_name=parser_name,
        parser_version=parser_version,
        error=str(error),
    )
    print(
        json.dumps(
            {
                "schema_analysis": analysis.analysis_id,
                "events": [
                    {
                        "severity": event.severity.value,
                        "kind": event.kind.value,
                        "message": event.message,
                    }
                    for event in analysis.events
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def _paginated_runner(
    store: FilesystemRawSnapshotStore,
    client: YandexPublicClient,
) -> YandexPaginatedProbeRunner:
    database_path = _database_path(store)
    return YandexPaginatedProbeRunner(
        client=client,
        raw_store=store,
        probe_store=SQLiteProbeRunStore(database_path),
        schema_registry=SQLiteSchemaDriftRegistry(database_path),
    )


def _probe_feed(args: argparse.Namespace) -> None:
    store = _store(args.output)
    try:
        with _session_manager(store).open(_context(args)) as session:
            result = _paginated_runner(store, session.client).run_feed(
                session.context,
                page_limit=args.pages,
                count=args.count,
            )
    except (ProbeCollectionError, SessionConfigurationError, SessionStateError) as exc:
        raise SystemExit(str(exc)) from exc

    cards = [game for page in result.parsed_pages for game in page.games]
    unique_app_ids = list(dict.fromkeys(game.app_id for game in cards))
    print(
        json.dumps(
            {
                "run_id": result.record.run.id,
                "status": result.record.run.status.value,
                "pages": len(result.record.pages),
                "cards": len(cards),
                "unique_games": len(unique_app_ids),
                "organic": sum(not game.sponsored for game in cards),
                "sponsored": sum(game.sponsored for game in cards),
                "appIDs": unique_app_ids,
                "lastPageInfo": result.parsed_pages[-1].page_info.model_dump(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def _probe_search(args: argparse.Namespace) -> None:
    store = _store(args.output)
    try:
        with _session_manager(store).open(_context(args)) as session:
            result = _paginated_runner(store, session.client).run_search(
                args.query,
                session.context,
                page_limit=args.pages,
            )
    except (ProbeCollectionError, SessionConfigurationError, SessionStateError) as exc:
        raise SystemExit(str(exc)) from exc

    cards = [game for page in result.parsed_pages for game in page.games]
    unique_app_ids = list(dict.fromkeys(game.app_id for game in cards))
    total_games_count = next(
        (
            page.total_games_count
            for page in result.parsed_pages
            if page.total_games_count is not None
        ),
        None,
    )
    print(
        json.dumps(
            {
                "run_id": result.record.run.id,
                "status": result.record.run.status.value,
                "query": result.record.run.query_text,
                "pages": len(result.record.pages),
                "results": len(cards),
                "unique_results": len(unique_app_ids),
                "totalGamesCount": total_games_count,
                "appIDs": unique_app_ids,
                "lastPageInfo": result.parsed_pages[-1].page_info.model_dump(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def _analyze_feed_depth(args: argparse.Namespace) -> None:
    store = _store(args.output)
    database_path = _database_path(store)
    if not database_path.is_file():
        raise SystemExit(
            f"operational database not found: {database_path}; "
            "collect feed trials before running feed-depth analysis"
        )
    experiment = FeedDepthExperiment(
        raw_store=store,
        probe_store=SQLiteProbeRunStore(database_path),
    )
    try:
        report = experiment.analyze(args.run_ids)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(report.model_dump_json(indent=2))


def _analyze_session_profile_stability(args: argparse.Namespace) -> None:
    store = _store(args.output)
    database_path = _database_path(store)
    if not database_path.is_file():
        raise SystemExit(
            f"operational database not found: {database_path}; "
            "collect matched session-profile blocks before analysis"
        )
    experiment = SessionProfileStabilityExperiment(
        raw_store=store,
        probe_store=SQLiteProbeRunStore(database_path),
    )
    try:
        report = experiment.analyze(args.blocks)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(report.model_dump_json(indent=2))


def _freeze_collection_cadence_plan(args: argparse.Namespace) -> None:
    store = _store(args.output)
    database_path = _database_path(store)
    if not database_path.is_file():
        raise SystemExit(
            f"operational database not found: {database_path}; "
            "persist the listing cohort and query family before freezing a cadence plan"
        )
    plan_path = Path(args.plan)
    try:
        declaration = CollectionCadencePlanDeclaration.model_validate_json(
            plan_path.read_text(encoding="utf-8")
        )
        frozen = CollectionCadencePlanFreezer(database_path).freeze(declaration)
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    print(frozen.model_dump_json(indent=2))


def _analyze_collection_cadence(args: argparse.Namespace) -> None:
    store = _store(args.output)
    database_path = _database_path(store)
    if not database_path.is_file():
        raise SystemExit(
            f"operational database not found: {database_path}; "
            "freeze a cadence plan and collect daily evidence before analysis"
        )
    manifest_path = Path(args.manifest)
    try:
        manifest = CollectionCadenceManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
        report = CollectionCadenceExperiment(
            raw_store=store,
            database_path=database_path,
        ).analyze(manifest)
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    print(report.model_dump_json(indent=2))


def _probe_games(args: argparse.Namespace) -> None:
    store = _store(args.output)
    with _client() as client:
        response = client.collect_games(args.app_ids)
    metadata = _persist_or_fail(store, response)
    _observe_json_schema(store, metadata, response)
    parser = YandexGetGamesParser()
    try:
        parsed = parser.parse(response.body)
    except ValueError as exc:
        _record_parser_failure(
            store,
            metadata,
            parser_name=type(parser).__name__,
            parser_version=parser.version,
            error=exc,
        )
        raise

    persistence = YandexNormalizationPersistence(_database_path(store))
    for game in parsed.games:
        persistence.persist_details(game, metadata)
    print(
        json.dumps(
            [
                {
                    "appID": game.app_id,
                    "title": game.title,
                    "gqRating": game.yandex_rating,
                    "rating": game.player_rating,
                    "ratingCount": game.rating_count,
                    "firstPublished": game.first_published,
                    "minLoadTime": game.min_load_time,
                }
                for game in parsed.games
            ],
            ensure_ascii=False,
            indent=2,
        )
    )


def _probe_page(args: argparse.Namespace) -> None:
    store = _store(args.output)
    with _client() as client:
        response = client.collect_game_page(args.app_id)
    metadata = _persist_or_fail(store, response)
    parser = YandexPlayPageParser()
    try:
        parsed = parser.parse(response.body)
    except ValueError as exc:
        _record_parser_failure(
            store,
            metadata,
            parser_name=type(parser).__name__,
            parser_version=parser.version,
            error=exc,
        )
        raise
    if parsed.app_id != args.app_id:
        raise SystemExit(
            f"game page returned appID={parsed.app_id}; expected requested appID={args.app_id}"
        )
    YandexNormalizationPersistence(_database_path(store)).persist_play_page(
        parsed,
        metadata,
    )
    print(parsed.model_dump_json(indent=2, exclude={"raw_game_data"}))


def _add_context_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--lang", default="ru")
    parser.add_argument("--device", choices=["desktop", "mobile"], default="desktop")
    parser.add_argument("--platform", default="desktop_other")
    parser.add_argument(
        "--session-profile",
        choices=[profile.value for profile in SessionProfile],
        default=SessionProfile.CLEAN_ANONYMOUS.value,
        help="HTTP session isolation profile for contextual feed/search probes.",
    )
    parser.add_argument("--output", help="Raw snapshot root. Defaults to REAPER_DATA_DIR/raw.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="yandex-reaper")
    sub = parser.add_subparsers(dest="command", required=True)

    feed = sub.add_parser("probe-feed", help="Fetch and persist Yandex feed pages.")
    _add_context_args(feed)
    feed.add_argument("--count", type=int, default=20)
    feed.add_argument("--pages", type=int, default=1, help="Maximum feed pages in this probe run.")
    feed.set_defaults(handler=_probe_feed)

    search = sub.add_parser("probe-search", help="Fetch and persist Yandex search pages.")
    _add_context_args(search)
    search.add_argument("query")
    search.add_argument(
        "--pages",
        type=int,
        default=1,
        help="Maximum search pages in this probe run.",
    )
    search.set_defaults(handler=_probe_search)

    depth = sub.add_parser(
        "analyze-feed-depth",
        help="Replay explicit up-to-10-page feed runs and evaluate feed-depth-v1.",
    )
    depth.add_argument(
        "run_ids",
        nargs="+",
        help="Probe run IDs to include in the experiment report.",
    )
    depth.add_argument("--output", help="Raw snapshot root. Defaults to REAPER_DATA_DIR/raw.")
    depth.set_defaults(handler=_analyze_feed_depth)

    session_profiles = sub.add_parser(
        "analyze-session-profile-stability",
        help="Replay explicit matched feed blocks and evaluate session-profile-stability-v1.",
    )
    session_profiles.add_argument(
        "--block",
        dest="blocks",
        action="append",
        nargs=4,
        required=True,
        metavar=("RUN1", "RUN2", "RUN3", "RUN4"),
        help="Four run IDs for one matched block; repeat --block for additional blocks.",
    )
    session_profiles.add_argument(
        "--output",
        help="Raw snapshot root. Defaults to REAPER_DATA_DIR/raw.",
    )
    session_profiles.set_defaults(handler=_analyze_session_profile_stability)

    freeze_cadence = sub.add_parser(
        "freeze-collection-cadence-plan",
        help="Persist a collection-cadence-v1 cohort/window before daily collection begins.",
    )
    freeze_cadence.add_argument(
        "plan",
        help="Path to a predeclared collection-cadence-v1 plan JSON file.",
    )
    freeze_cadence.add_argument(
        "--output",
        help="Raw snapshot root. Defaults to REAPER_DATA_DIR/raw.",
    )
    freeze_cadence.set_defaults(handler=_freeze_collection_cadence_plan)

    cadence = sub.add_parser(
        "analyze-collection-cadence",
        help="Replay run bindings against one frozen collection-cadence-v1 plan.",
    )
    cadence.add_argument("manifest", help="Path to the cadence evidence-binding JSON manifest.")
    cadence.add_argument(
        "--output",
        help="Raw snapshot root. Defaults to REAPER_DATA_DIR/raw.",
    )
    cadence.set_defaults(handler=_analyze_collection_cadence)

    games = sub.add_parser("probe-games", help="Fetch and persist rich metadata for app IDs.")
    games.add_argument("app_ids", nargs="+", type=int)
    games.add_argument("--output")
    games.set_defaults(handler=_probe_games)

    page = sub.add_parser("probe-page", help="Fetch and parse __playPageData__ for one app.")
    page.add_argument("app_id", type=int)
    page.add_argument("--output")
    page.set_defaults(handler=_probe_page)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    handler = args.handler
    handler(args)
