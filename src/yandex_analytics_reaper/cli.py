from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from yandex_analytics_reaper.config import load_settings
from yandex_analytics_reaper.domain.models import ProbeContext
from yandex_analytics_reaper.sources.capabilities import CollectedResponse
from yandex_analytics_reaper.sources.yandex import (
    YandexFeedParser,
    YandexGetGamesParser,
    YandexPlayPageParser,
    YandexPublicClient,
)
from yandex_analytics_reaper.storage import FilesystemRawSnapshotStore


def _context(args: argparse.Namespace) -> ProbeContext:
    return ProbeContext(
        language=args.lang,
        device_type=args.device,
        platform=args.platform,
    )


def _store(output: str | None) -> FilesystemRawSnapshotStore:
    settings = load_settings()
    root = Path(output) if output else settings.data_dir / "raw"
    return FilesystemRawSnapshotStore(root)


def _client() -> YandexPublicClient:
    settings = load_settings()
    return YandexPublicClient(
        base_url=settings.yandex_base_url,
        timeout_seconds=settings.http_timeout_seconds,
        user_agent=settings.user_agent,
    )


def _persist_or_fail(store: FilesystemRawSnapshotStore, response: CollectedResponse) -> None:
    metadata = store.persist(response)
    print(f"raw_snapshot={metadata.id} status={response.status_code}")
    if not 200 <= response.status_code < 300:
        raise SystemExit(f"source returned HTTP {response.status_code}; raw response was preserved")


def _probe_feed(args: argparse.Namespace) -> None:
    store = _store(args.output)
    with _client() as client:
        response = client.collect_feed(_context(args), count=args.count)
    _persist_or_fail(store, response)
    parsed = YandexFeedParser().parse(response.body)
    organic = sum(not game.sponsored for game in parsed.games)
    sponsored = sum(game.sponsored for game in parsed.games)
    print(
        json.dumps(
            {
                "games": len(parsed.games),
                "organic": organic,
                "sponsored": sponsored,
                "totalGamesCount": parsed.total_games_count,
                "pageInfo": parsed.page_info.model_dump(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def _probe_search(args: argparse.Namespace) -> None:
    store = _store(args.output)
    with _client() as client:
        response = client.collect_search(args.query, _context(args))
    _persist_or_fail(store, response)
    parsed = YandexFeedParser().parse(response.body)
    print(
        json.dumps(
            {
                "query": args.query,
                "results_in_page": len(parsed.games),
                "totalGamesCount": parsed.total_games_count,
                "pageInfo": parsed.page_info.model_dump(),
                "appIDs": [game.app_id for game in parsed.games],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def _probe_games(args: argparse.Namespace) -> None:
    store = _store(args.output)
    with _client() as client:
        response = client.collect_games(args.app_ids)
    _persist_or_fail(store, response)
    parsed = YandexGetGamesParser().parse(response.body)
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
    _persist_or_fail(store, response)
    parsed = YandexPlayPageParser().parse(response.body)
    print(parsed.model_dump_json(indent=2, exclude={"raw_game_data"}))


def _add_context_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--lang", default="ru")
    parser.add_argument("--device", choices=["desktop", "mobile"], default="desktop")
    parser.add_argument("--platform", default="desktop_other")
    parser.add_argument("--output", help="Raw snapshot root. Defaults to REAPER_DATA_DIR/raw.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="yandex-reaper")
    sub = parser.add_subparsers(dest="command", required=True)

    feed = sub.add_parser("probe-feed", help="Fetch and persist one Yandex feed page.")
    _add_context_args(feed)
    feed.add_argument("--count", type=int, default=20)
    feed.set_defaults(handler=_probe_feed)

    search = sub.add_parser("probe-search", help="Fetch and persist one Yandex search page.")
    _add_context_args(search)
    search.add_argument("query")
    search.set_defaults(handler=_probe_search)

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
