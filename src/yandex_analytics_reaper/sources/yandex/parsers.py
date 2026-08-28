from __future__ import annotations

import html as html_lib
import json
import re
from typing import Any, Mapping

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
    title: str | None = None
    developer: Developer | None = None
    category_ids: tuple[int, ...] = ()
    tag_ids: tuple[int, ...] = ()
    player_rating: float | None = None
    rating_count: int | None = None
    yandex_rating: int | None = None
    badge: dict[str, Any] = Field(default_factory=dict)
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
    languages: tuple[str, ...] = ()
    platforms: tuple[str, ...] = ()
    orientation: str | None = None
    cloud_save: bool | None = None
    leaderboards: bool | None = None
    purchases_enabled: bool | None = None
    has_products: bool | None = None
    media: dict[str, Any] = Field(default_factory=dict)


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
    raw_game_data: dict[str, Any] = Field(default_factory=dict)


def _load_json(body: bytes) -> Any:
    try:
        return json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("response is not valid JSON") from exc


def _developer(value: object) -> Developer | None:
    if not isinstance(value, Mapping):
        return None
    return Developer(id=value.get("id"), name=_as_str(value.get("name")))


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


def _tuple_ints(value: object) -> tuple[int, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in (_as_int(v) for v in value) if item is not None)


def _tuple_strs(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(v for v in value if isinstance(v, str))


def _is_sponsored(game: Mapping[str, Any]) -> bool:
    badge = game.get("badge")
    badge_type = badge.get("badgeType") if isinstance(badge, Mapping) else None
    return bool(game.get("source") or game.get("click_link") or badge_type == "badge.direct")


def _card(value: Mapping[str, Any]) -> GameCard | None:
    app_id = _as_int(value.get("appID"))
    if app_id is None:
        return None
    badge = value.get("badge") if isinstance(value.get("badge"), dict) else {}
    return GameCard(
        app_id=app_id,
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


class YandexFeedParser:
    version = "1"

    def parse(self, body: bytes) -> FeedPage:
        data = _load_json(body)
        if not isinstance(data, Mapping):
            raise ValueError("feed root must be an object")

        games: list[GameCard] = []
        seen: set[int] = set()
        feed = data.get("feed")
        if isinstance(feed, list):
            for block in feed:
                if not isinstance(block, Mapping):
                    continue
                widgets = block.get("widgets")
                if isinstance(widgets, list):
                    for widget in widgets:
                        if not isinstance(widget, Mapping) or widget.get("type") != "game":
                            continue
                        game_data = widget.get("data")
                        if isinstance(game_data, Mapping):
                            card = _card(game_data)
                            if card is not None and card.app_id not in seen:
                                seen.add(card.app_id)
                                games.append(card)
                items = block.get("items")
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, Mapping):
                            card = _card(item)
                            if card is not None and card.app_id not in seen:
                                seen.add(card.app_id)
                                games.append(card)

        page_info_value = data.get("pageInfo")
        page_info_map = page_info_value if isinstance(page_info_value, Mapping) else {}
        page_info = PageInfo(
            next_page_id=_as_str(page_info_map.get("nextPageId")),
            rtx_reqid=_as_str(page_info_map.get("rtxReqId")),
            has_next_page=bool(page_info_map.get("hasNextPage")),
        )
        return FeedPage(
            games=tuple(games),
            total_games_count=_as_int(data.get("totalGamesCount")),
            page_info=page_info,
        )


class YandexGetGamesParser:
    version = "1"

    def parse(self, body: bytes) -> GetGamesResult:
        data = _load_json(body)
        if not isinstance(data, Mapping):
            raise ValueError("get_games root must be an object")
        raw_games = data.get("games")
        if not isinstance(raw_games, list):
            return GetGamesResult(games=())

        games: list[GameDetails] = []
        for value in raw_games:
            if not isinstance(value, Mapping):
                continue
            card = _card(value)
            if card is None:
                continue
            features = value.get("features") if isinstance(value.get("features"), Mapping) else {}
            extra = (
                value.get("extraFeatures")
                if isinstance(value.get("extraFeatures"), Mapping)
                else {}
            )
            score_raw = value.get("score") if isinstance(value.get("score"), Mapping) else {}
            score = {
                str(k): v
                for k, v in score_raw.items()
                if isinstance(k, (str, int)) and isinstance(v, int) and not isinstance(v, bool)
            }
            media = value.get("media") if isinstance(value.get("media"), dict) else {}
            games.append(
                GameDetails(
                    **card.model_dump(),
                    categories_names=_tuple_strs(value.get("categoriesNames")),
                    score=score,
                    first_published=_as_int(value.get("firstPublished")),
                    min_load_time=_as_float(value.get("minLoadTime")),
                    description=_as_str(value.get("description")),
                    instruction=_as_str(value.get("instruction")),
                    seo_description=_as_str(value.get("seoDescription")),
                    languages=_tuple_strs(features.get("languages")),
                    platforms=_tuple_strs(features.get("platforms")),
                    orientation=_as_str(features.get("orientation")),
                    cloud_save=(
                        features.get("cloud_save")
                        if isinstance(features.get("cloud_save"), bool)
                        else None
                    ),
                    leaderboards=(
                        extra.get("leaderboards")
                        if isinstance(extra.get("leaderboards"), bool)
                        else None
                    ),
                    purchases_enabled=(
                        extra.get("purchases")
                        if isinstance(extra.get("purchases"), bool)
                        else None
                    ),
                    has_products=(
                        extra.get("hasProducts")
                        if isinstance(extra.get("hasProducts"), bool)
                        else None
                    ),
                    media=media,
                )
            )
        return GetGamesResult(games=tuple(games))


_SCRIPT_TEMPLATE = r'<script[^>]+id=["\']{script_id}["\'][^>]*>(.*?)</script>'


class YandexPlayPageParser:
    version = "1"

    def parse(self, body: bytes) -> PlayPageData:
        try:
            page_html = body.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("game page is not UTF-8") from exc
        payload = self._extract_script(page_html, "__playPageData__")
        if not isinstance(payload, Mapping):
            raise ValueError("__playPageData__ was not found")
        raw_game = payload.get("gameData")
        game_data = raw_game if isinstance(raw_game, dict) else {}
        adv = (
            game_data.get("advUsedBlocks")
            if isinstance(game_data.get("advUsedBlocks"), Mapping)
            else {}
        )
        extra = (
            game_data.get("extraFeatures")
            if isinstance(game_data.get("extraFeatures"), Mapping)
            else {}
        )
        settings = (
            game_data.get("settings")
            if isinstance(game_data.get("settings"), Mapping)
            else {}
        )
        settings_adv = settings.get("adv") if isinstance(settings.get("adv"), Mapping) else {}
        sticky = settings_adv.get("sticky")
        sticky_enabled: bool | None
        if isinstance(sticky, bool):
            sticky_enabled = sticky
        elif isinstance(sticky, Mapping):
            sticky_enabled = bool(sticky)
        else:
            sticky_enabled = None
        return PlayPageData(
            app_id=_as_int(game_data.get("appID")),
            app_version=_as_str(game_data.get("appVersion")),
            published_time=_as_int(game_data.get("publishedTime")),
            yandex_rating=_as_int(game_data.get("gqRating")),
            rewarded_ads=adv.get("rewarded") if isinstance(adv.get("rewarded"), bool) else None,
            fullscreen_ads=(
                adv.get("fullscreen") if isinstance(adv.get("fullscreen"), bool) else None
            ),
            sticky_ads=sticky_enabled,
            leaderboards=(
                extra.get("leaderboards") if isinstance(extra.get("leaderboards"), bool) else None
            ),
            purchases_enabled=(
                extra.get("purchases") if isinstance(extra.get("purchases"), bool) else None
            ),
            has_products=(
                extra.get("hasProducts") if isinstance(extra.get("hasProducts"), bool) else None
            ),
            raw_game_data=game_data,
        )

    @staticmethod
    def _extract_script(page_html: str, script_id: str) -> Any | None:
        pattern = re.compile(_SCRIPT_TEMPLATE.format(script_id=re.escape(script_id)), re.S | re.I)
        match = pattern.search(page_html)
        if match is None:
            return None
        raw = html_lib.unescape(match.group(1)).strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None
