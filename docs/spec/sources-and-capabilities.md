# Sources & Capabilities

A source is not a capability. Analytics depends on capability contracts so one provider can be replaced without pretending it supplies data it does not actually expose.

## Capability contracts

```text
CatalogMetadataProvider
SearchDiscoveryProvider
RecommendationExposureProvider
HistoricalMetricsProvider
StatusHistoryProvider
MediaProvider
TrendProvider
```

A provider may implement only a subset.

## Yandex current structured source

Technically proven in controlled live probes on 2026-08-28.

Current proven capabilities:

```text
CatalogMetadataProvider        yes
SearchDiscoveryProvider        yes
RecommendationExposureProvider yes
HistoricalMetricsProvider      self-snapshot only
StatusHistoryProvider          partial/observational
MediaProvider                  yes
```

Important semantics:

```text
gqRating
= Yandex Games Rating 0–100

rating / ratingCount / score
= player star-rating system

totalGamesCount
= search-result count for a query
≠ canonical competitor count
```

Sponsored feed cards remain separate from organic exposure. `Popular` is treated as platform/editorial featuring evidence, not pure algorithmic recommendation performance.

## Yandex Distribution

Potential official metadata source. Integrate capability-by-capability; do not assume it replaces feed/search/exposure data unless those capabilities are actually available.

## SpyMagic

Potential historical market/backfill source. Estimated installs/revenue remain third-party estimates. Before strict historical use, record whether historical values were available at the claimed time and whether they were later revised/recalculated.

## Game-Analytics / WebGameAnalytics

Potential Yandex-specific historical/status/rating source. For any import record:

```text
snapshot cadence
data lag
timezone
revision policy
historical availability semantics
```

## External trend sources

Wordstat, YouTube, TGStat, Google Trends, Steam/mobile intelligence are enrichment capabilities, not Yandex-native MVP dependencies.

## Source registry fields

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

Evidence quality is observation-specific and belongs to the Evidence Model rather than this registry.
