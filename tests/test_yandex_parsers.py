from __future__ import annotations

import json

from yandex_analytics_reaper.sources.yandex.parsers import (
    YandexFeedParser,
    YandexGetGamesParser,
    YandexPlayPageParser,
)


def test_feed_parser_separates_sponsored_cards() -> None:
    payload = {
        "feed": [
            {
                "widgets": [
                    {
                        "type": "game",
                        "data": {
                            "appID": 1,
                            "title": "Organic",
                            "gqRating": 74,
                            "rating": 4.4,
                            "ratingCount": 100,
                        },
                    },
                    {
                        "type": "game",
                        "data": {
                            "appID": 2,
                            "title": "Sponsored",
                            "source": "bk_direct",
                            "click_link": "https://example.test",
                            "badge": {"badgeType": "badge.direct"},
                        },
                    },
                ]
            }
        ],
        "totalGamesCount": 120,
        "pageInfo": {
            "nextPageId": "next",
            "rtxReqId": "req",
            "hasNextPage": True,
        },
    }
    parsed = YandexFeedParser().parse(json.dumps(payload).encode())

    assert [game.app_id for game in parsed.games] == [1, 2]
    assert parsed.games[0].sponsored is False
    assert parsed.games[1].sponsored is True
    assert parsed.games[0].yandex_rating == 74
    assert parsed.total_games_count == 120
    assert parsed.page_info.next_page_id == "next"


def test_get_games_parser_keeps_yandex_rating_separate_from_player_rating() -> None:
    payload = {
        "games": [
            {
                "appID": 438560,
                "title": "Example",
                "developer": {"id": 10, "name": "Dev"},
                "rating": 4.3,
                "ratingCount": 6,
                "score": {"1": 1, "2": 0, "3": 0, "4": 1, "5": 4},
                "gqRating": 86,
                "firstPublished": 1750000000,
                "minLoadTime": 14.8,
                "categoriesNames": ["Симуляторы"],
                "tagIDs": [1, 2],
                "features": {
                    "languages": ["ru", "en"],
                    "platforms": ["desktop", "mobile"],
                    "orientation": "any",
                    "cloud_save": True,
                },
                "extraFeatures": {
                    "leaderboards": True,
                    "purchases": True,
                    "hasProducts": False,
                },
            }
        ]
    }
    game = YandexGetGamesParser().parse(json.dumps(payload).encode()).games[0]

    assert game.yandex_rating == 86
    assert game.player_rating == 4.3
    assert game.rating_count == 6
    assert sum(game.score.values()) == game.rating_count
    assert game.languages == ("ru", "en")
    assert game.purchases_enabled is True
    assert game.has_products is False


def test_get_games_parser_distinguishes_missing_language_fields() -> None:
    payload = {"games": [{"appID": 1}]}

    game = YandexGetGamesParser().parse(json.dumps(payload).encode()).games[0]

    assert game.languages is None
    assert game.platforms is None


def test_play_page_parser_reads_play_page_data() -> None:
    payload = {
        "gameData": {
            "appID": 438560,
            "appVersion": "1.2.3",
            "publishedTime": 1750000100,
            "gqRating": 86,
            "advUsedBlocks": {"rewarded": True, "fullscreen": False},
            "settings": {"adv": {"sticky": {"enabled": True}}},
            "extraFeatures": {
                "leaderboards": True,
                "purchases": True,
                "hasProducts": True,
            },
        }
    }
    html = (
        '<html><script id="__playPageData__" type="application/json">'
        + json.dumps(payload)
        + "</script></html>"
    )
    parsed = YandexPlayPageParser().parse(html.encode())

    assert parsed.app_id == 438560
    assert parsed.app_version == "1.2.3"
    assert parsed.yandex_rating == 86
    assert parsed.rewarded_ads is True
    assert parsed.fullscreen_ads is False
    assert parsed.sticky_ads is True
    assert parsed.has_products is True


def test_play_page_parser_respects_disabled_sticky_config() -> None:
    payload = {
        "gameData": {
            "appID": 1,
            "settings": {"adv": {"sticky": {"enabled": False}}},
        }
    }
    html = (
        '<html><script id="__playPageData__" type="application/json">'
        + json.dumps(payload)
        + "</script></html>"
    )

    parsed = YandexPlayPageParser().parse(html.encode())

    assert parsed.sticky_ads is False
