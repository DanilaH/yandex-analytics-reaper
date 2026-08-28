# Yandex Pre-launch Data Feasibility — 2026-08-28

This document preserves the factual findings that justified the current Yandex adapter.

## Live endpoints confirmed

The user's local probes on 2026-08-28 successfully received HTTP 200 responses from:

```text
GET  https://yandex.ru/games/api/catalogue/v2/feed/
GET  https://yandex.ru/games/api/catalogue/v2/search
POST https://yandex.ru/games/api/catalogue/v2/get_games
GET  https://yandex.ru/games/app/<appID>
```

## Feed/search behavior confirmed

The v2 probe confirmed:

```text
feed pagination
search pagination
search totalGamesCount
organic/sponsored separation
```

A three-page feed probe returned 72 unique cards (63 organic, 9 clearly sponsored in that observation). Search examples returned `totalGamesCount` values such as 411 for `merge` and 393 for `obby`; these values are query-result counts, not canonical mechanic competitor counts.

## Rich game metadata confirmed

Current responses exposed fields including:

```text
appID
title
developer id/name
categoryIDs/categoriesNames
tagIDs
rating
ratingCount
score[1..5]
gqRating
firstPublished
publishedTime
appVersion
minLoadTime
languages/platforms/orientation/cloud_save
media
leaderboards
purchases/hasProducts
advUsedBlocks
```

The older reverse-engineered `playersCount` field was not present in the tested current responses.

## Rating semantics confirmed

For tested game pages the value in `gqRating` matched the server-rendered label `Рейтинг Яндекс Игр`, while `rating` represented the 1–5 player rating and `ratingCount` the vote count. `score[1..5]` represented the star-vote distribution and summed to `ratingCount` in the checked batch.

## `__playPageData__` confirmed

The separate `__playPageData__.gameData` object was present on 10/10 checked pages and exposed additional useful metadata such as:

```text
appVersion
publishedTime
advUsedBlocks.rewarded
advUsedBlocks.fullscreen
settings.adv.sticky
extraFeatures leaderboards/purchases/hasProducts
```

Some pages also exposed counter/goal configuration. Such configuration is metadata only and must not be represented as actual competitor performance.

## Interpretation rules

```text
gqRating            first-party public quality/engagement proxy
rating/ratingCount  player-review signal
feed exposure        contextual observation
sponsored exposure   not organic recommendation evidence
search result count  supply/discovery signal, not competitor count
minLoadTime          Yandex-provided load-time metadata, not our benchmark
```

## What remains unavailable directly

The current public data does not directly expose exact competitor DAU, sessions/day, D1/D7 retention, average session duration, playtime/player, recommendation impressions, CTR, revenue, ARPDAU, or ad impressions.

These gaps are handled using explicit proxy/evidence semantics rather than pretending they are measured values.
