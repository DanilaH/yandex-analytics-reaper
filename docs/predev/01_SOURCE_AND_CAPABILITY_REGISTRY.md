# Source & Capability Registry v2

## 1. Why source != capability

A source can provide only part of what the system needs.

Example:

```text
Yandex public frontend
  metadata                yes
  search discovery        yes
  recommendation exposure yes
  history                 only from our own snapshots

Yandex Distribution
  metadata                potentially yes
  search discovery        unknown
  recommendation exposure not assumed
  historical metrics      not assumed
```

Therefore analytics must depend on capability interfaces.

---

## 2. Capability contracts

### CatalogMetadataProvider

Returns platform listing identity, title, developer, categories/tags, publication metadata, languages/platforms, media references, and feature flags.

### SearchDiscoveryProvider

Returns query, query result count, ordered listing IDs, pagination metadata, and observation context.

### RecommendationExposureProvider

Returns surface, ordered listing IDs, organic/sponsored/editorial markers, position/page, and context.

### HistoricalMetricsProvider

Returns metric, period, value, measurement kind, and point-in-time integrity.

### StatusHistoryProvider

Returns published/unavailable/deleted/unknown, observation time, and reason if known.

### TrendProvider

Returns theme/mechanic trend series.

---

## 3. Yandex current structured data

**Role:** primary Yandex-native current market observation  
**Status:** technically proven live on 2026-08-28  
**Priority:** P0

Capabilities:

```text
CatalogMetadataProvider        YES
SearchDiscoveryProvider        YES
RecommendationExposureProvider YES
HistoricalMetricsProvider      SELF-SNAPSHOT ONLY
StatusHistoryProvider          PARTIAL / OBSERVATIONAL
MediaProvider                  YES
```

Important semantics:

```text
gqRating
= Yandex Games Rating 0–100

rating / ratingCount / score
= player star-rating system

totalGamesCount
= search-result count for a query
NOT canonical competitor count
```

Sponsored feed cards must remain separate from organic exposure.

`Popular` should be treated as an editorial/platform featuring signal, not pure algorithmic recommendation evidence.

---

## 4. Yandex Distribution

**Role:** possible official metadata provider  
**Priority:** P1 unless it proves broader capabilities

Do not assume it replaces public frontend capabilities.

Potential:

```text
CatalogMetadataProvider        likely
SearchDiscoveryProvider        unknown
RecommendationExposureProvider unknown / unlikely
HistoricalMetricsProvider      unknown
```

Integrate capability-by-capability.

---

## 5. SpyMagic

**Role:** historical market estimates/backfill  
**Priority:** P0 for historical research if export is available

Treat metrics such as estimated installs/revenue as third-party estimates.

Critical historical field:

```text
point_in_time_integrity
```

Before using historical values in strict backtests, determine whether they are immutable historical snapshots or retroactively recalculated with later data. If retroactively recalculated, they cannot be used as strict `T-7` features.

---

## 6. Game-Analytics / WebGameAnalytics

**Role:** Yandex-specific historical market/status/rating dataset  
**Priority:** P0 for historical backfill if accessible

Useful possible fields include gqRating RU/EN, player rating/count, publication date, status/deletion, developer portfolio, rating-count velocity, and historical playersCount if retained.

Also require snapshot cadence, data lag, timezone, revision policy, backfill/recalculation policy, and point-in-time integrity.

---

## 7. Wordstat

**Role:** theme search demand  
**Priority:** P1 after taxonomy validation

Never interpret search demand as game recommendation demand. Use it as one external theme signal.

---

## 8. YouTube

**Role:** theme/media momentum  
**Priority:** P1/P2

Useful signals include videos_7d/30d, median/top views, creator count, view velocity, and acceleration. Track API definition changes over time.

---

## 9. TGStat

**Role:** RU/CIS theme momentum  
**Priority:** P2 until candidate taxonomy narrows tracked themes

Useful signals include mentions, reach, view dynamics, and creator/channel breadth.

---

## 10. Google Trends

**Role:** broader trend confirmation  
**Priority:** optional

Architecture must not depend on access.

---

## 11. Cross-market intelligence

Sensor Tower / Steam / mobile-market sources can help answer whether a mechanic/theme succeeds outside Yandex before Yandex supply catches up. They are enrichment, not MVP dependencies.

---

## 12. Source registry fields

Store:

```text
source_id
name
owner
capabilities[]
access_method
status
data_lag
update_frequency
historical_depth
revision_policy
timezone
rate_limit
cost
notes
```

Do not encode evidence quality here; evidence quality belongs to each observation.
