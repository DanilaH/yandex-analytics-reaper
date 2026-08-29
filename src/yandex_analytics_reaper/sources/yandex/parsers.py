from __future__ import annotations

import html as html_lib
import json
import re
from collections.abc import Mapping
from typing import cast

from pydantic import BaseModel, ConfigDict, Field


class Developer(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str | int | None = None
    name: str | None = None


class PageInfo(BaseModel):
    model_config = ConfigDict(frozen=True)

    next_page_id: str | None = None
    rtx_reqid: str | None = None
    has_next_page: bool = False


class GameCard(BaseModel):
    model_config = ConfigDict(frozen=True)

    app_id: int
    source_object_path: str | None = None
    title: str | None = None
    developer: Developer | None = None
    category_ids: tuple[int, ...] = ()
    tag_ids: tuple[int, ...] = ()
    player_rating: float | None = None
    rating_count: int | None = None
    yandex_rating: int | None = None
    badge: dict[str, object] = Field(default_factory=dict)
    source_marker: str | None = None
    sponsored: bool = False
    row: int | None = None
    column: int | None = None


class FeedPage(BaseModel):
    model_config = ConfigDict(frozen=True)

    games: tuple[GameCard, ...]
    total_games_count: int | None = None
    page_info: PageInfo = Field(default_factory=PageInfo)


class GameDetails(GameCard):
    categories_names: tuple[str, ...] = ()
    score: dict[str, int] = Field(default_factory=dict)
    first_published: int | None = None
    min_load_time: float | None = None
    description: str | None = None
    instruction: str | None = None
    seo_description: str | None = None
    languages: tuple[str, ...] | None = None
    platforms: tuple[str, ...] | None = None
    orientation: str | None = None
    cloud_save: bool | None = None
    leaderboards: bool | None = None
    purchases_enabled: bool | None = None
    has_products: bool | None = None
    media: dict[str, object] | None = None


class GetGamesResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    games: tuple[GameDetails, ...]


class PlayPageData(BaseModel):
    model_config = ConfigDict(frozen=True)

    app_id: int | None = None
    app_version: str | None = None
    published_time: int | None = None
    yandex_rating: int | None = None
    rewarded_ads: bool | None = None
    fullscreen_ads: bool | None = None
    sticky_ads: bool | None = None
    leaderboards: bool | None = None
    purchases_enabled: bool | None = None
    has_products: bool | None = None
    raw_game_data: dict[str, object] = Field(default_factory=dict)


def _load_json(body: bytes) -> object:
    try:
        value: object = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("response is not valid JSON") from exc
    return value


def _string_mapping(value: object) -> dict[str, object] | None:
    """Validate a JSON object boundary once so Any does not leak through the parser."""

    if not isinstance(value, dict):
        return None
    if not all(isinstance(key, str) for key in value):
        return None
    return cast(dict[str, object], value)


def _developer(value: object) -> Developer | None:
    data = _string_mapping(value)
    if data is None:
        return None
    raw_id = data.get("id")
    developer_id = raw_id if isinstance(raw_id, (str, int)) and not isinstance(raw_id, bool) else None
    return Developer(id=developer_id, name=_as_str(data.get("name")))


def _as_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _as_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _as_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _as_bool(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _tuple_ints(value: object) -> tuple[int, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in (_as_int(v) for v in value) if item is not None)


def _tuple_strs(value: object) -> tuple[str, ...] | None:
    if not isinstance(value, list):
        return None
    return tuple(v for v in value if isinstance(v, str))


def _is_sponsored(game: Mapping[str, object]) -> bool:
    badge = _string_mapping(game.get("badge"))
    badge_type = badge.get("badgeType") if badge is not None else None
    return bool(game.get("source") or game.get("click_link") or badge_type == "badge.direct")


def _card(
    value: Mapping[str, object],
    *,
    source_object_path: str | None = None,
) -> GameCard | None:
    app_id = _as_int(value.get("appID"))
    if app_id is None:
        return None
    badge = _string_mapping(value.get("badge")) or {}
    return GameCard(
        app_id=app_id,
        source_object_path=source_object_path,
        title=_as_str(value.get("title")),
        developer=_developer(value.get("developer")),
        category_ids=_tuple_ints(value.get("categoryIDs")),
        tag_ids=_tuple_ints(value.get("tagIDs")),
        player_rating=_as_float(value.get("rating")),
        rating_count=_as_int(value.get("ratingCount")),
        yandex_rating=_as_int(value.get("gqRating")),
        badge=badge,
        source_marker=_as_str(value.get("source")),
        sponsored=_is_sponsored(value),
        row=_as_int(value.get("row")),
        column=_as_int(value.get("column")),
    )


def _details(card: GameCard, value: Mapping[str, object]) -> GameDetails:
    features = _string_mapping(value.get("features")) or {}
    extra = _string_mapping(value.get("extraFeatures")) or {}
    score_raw = _string_mapping(value.get("score")) or {}
    score = {
        key: raw_count
        for key, raw_count in score_raw.items()
        if isinstance(raw_count, int) and not isinstance(raw_count, bool)
    }
    media = _string_mapping(value.get("media"))
    return GameDetails(
        app_id=card.app_id,
        source_object_path=card.source_object_path,
        title=card.title,
        developer=card.developer,
        category_ids=card.category_ids,
        tag_ids=card.tag_ids,
        player_rating=card.player_rating,
        rating_count=card.rating_count,
        yandex_rating=card.yandex_rating,
        badge=card.badge,
        source_marker=card.source_marker,
        sponsored=card.sponsored,
        row=card.row,
        column=card.column,
        categories_names=_tuple_strs(value.get("categoriesNames")) or (),
        score=score,
        first_published=_as_int(value.get("firstPublished")),
        min_load_time=_as_float(value.get("minLoadTime")),
        description=_as_str(value.get("description")),
        instruction=_as_str(value.get("instruction")),
        seo_description=_as_str(value.get("seoDescription")),
        languages=_tuple_strs(features.get("languages")),
        platforms=_tuple_strs(features.get("platforms")),
        orientation=_as_str(features.get("orientation")),
        cloud_save=_as_bool(features.get("cloud_save")),
        leaderboards=_as_bool(extra.get("leaderboards")),
        purchases_enabled=_as_bool(extra.get("purchases")),
        has_products=_as_bool(extra.get("hasProducts")),
        media=media,
    )


class YandexFeedParser:
    version = "2"

    def parse(self, body: bytes) -> FeedPage:
        data = _string_mapping(_load_json(body))
        if data is None:
            raise ValueError("feed root must be an object")

        games: list[GameCard] = []
        seen: set[int] = set()
        feed = data.get("feed")
        if isinstance(feed, list):
            for block_index, raw_block in enumerate(feed):
                block = _string_mapping(raw_block)
                if block is None:
                    continue
                widgets = block.get("widgets")
                if isinstance(widgets, list):
                    for widget_index, raw_widget in enumerate(widgets):
                        widget = _string_mapping(raw_widget)
                        if widget is None or widget.get("type") != "game":
                            continue
                        game_data = _string_mapping(widget.get("data"))
                        if game_data is not None:
                            card = _card(
                                game_data,
                                source_object_path=(
                                    f"$.feed[{block_index}].widgets[{widget_index}].data"
                                ),
                            )
                            if card is not None and card.app_id not in seen:
                                seen.add(card.app_id)
                                games.append(card)
                items = block.get("items")
                if isinstance(items, list):
                    for item_index, raw_item in enumerate(items):
                        item = _string_mapping(raw_item)
                        if item is not None:
                            card = _card(
                                item,
                                source_object_path=f"$.feed[{block_index}].items[{item_index}]",
                            )
                            if card is not None and card.app_id not in seen:
                                seen.add(card.app_id)
                                games.append(card)

        page_info_map = _string_mapping(data.get("pageInfo")) or {}
        page_info = PageInfo(
            next_page_id=_as_str(page_info_map.get("nextPageId")),
            rtx_reqid=_as_str(page_info_map.get("rtxReqId")),
            has_next_page=_as_bool(page_info_map.get("hasNextPage")) or False,
        )
        return FeedPage(
            games=tuple(games),
            total_games_count=_as_int(data.get("totalGamesCount")),
            page_info=page_info,
        )


class YandexGetGamesParser:
    version = "4"

    def parse(self, body: bytes) -> GetGamesResult:
        data = _string_mapping(_load_json(body))
        if data is None:
            raise ValueError("get_games root must be an object")
        raw_games = data.get("games")
        if not isinstance(raw_games, list):
            return GetGamesResult(games=())

        games: list[GameDetails] = []
        for game_index, raw_value in enumerate(raw_games):
            value = _string_mapping(raw_value)
            if value is None:
                continue
            card = _card(value, source_object_path=f"$.games[{game_index}]")
            if card is not None:
                games.append(_details(card, value))
        return GetGamesResult(games=tuple(games))


_SCRIPT_TEMPLATE = r'<script[^>]+id=["\']{script_id}["\'][^>]*>(.*?)</script>'


class YandexPlayPageParser:
    version = "1"

    def parse(self, body: bytes) -> PlayPageData:
        try:
            page_html = body.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("game page is not UTF-8") from exc

        payload = _string_mapping(self._extract_script(page_html, "__playPageData__"))
        if payload is None:
            raise ValueError("__playPageData__ was not found")
        game_data = _string_mapping(payload.get("gameData")) or {}
        adv = _string_mapping(game_data.get("advUsedBlocks")) or {}
        extra = _string_mapping(game_data.get("extraFeatures")) or {}
        settings = _string_mapping(game_data.get("settings")) or {}
        settings_adv = _string_mapping(settings.get("adv")) or {}
        sticky = settings_adv.get("sticky")

        sticky_enabled: bool | None = None
        if isinstance(sticky, bool):
            sticky_enabled = sticky
        else:
            sticky_config = _string_mapping(sticky)
            if sticky_config is not None:
                sticky_enabled = _as_bool(sticky_config.get("enabled"))

        return PlayPageData(
            app_id=_as_int(game_data.get("appID")),
            app_version=_as_str(game_data.get("appVersion")),
            published_time=_as_int(game_data.get("publishedTime")),
            yandex_rating=_as_int(game_data.get("gqRating")),
            rewarded_ads=_as_bool(adv.get("rewarded")),
            fullscreen_ads=_as_bool(adv.get("fullscreen")),
            sticky_ads=sticky_enabled,
            leaderboards=_as_bool(extra.get("leaderboards")),
            purchases_enabled=_as_bool(extra.get("purchases")),
            has_products=_as_bool(extra.get("hasProducts")),
            raw_game_data=game_data,
        )

    @staticmethod
    def _extract_script(page_html: str, script_id: str) -> object | None:
        pattern = re.compile(_SCRIPT_TEMPLATE.format(script_id=re.escape(script_id)), re.S | re.I)
        match = pattern.search(page_html)
        if match is None:
            return None
        raw = html_lib.unescape(match.group(1)).strip()
        try:
            value: object = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return value
