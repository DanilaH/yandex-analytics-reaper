# Listing histories review scope

This temporary review note records only the merge-gate scope for the Phase 2 listing-history change:

- `YandexGetGamesParser@4` preserves missing media versus present empty media;
- `YandexListingHistoryNormalizer@1` emits only directly observed presence status plus update/media facts;
- no negative status is inferred from result omission without exact request↔response binding;
- SQLite v9 stores typed update/status/media observations, shared evidence, and field lineage transactionally;
- existing migration regressions must prove upgrade through v9;
- no scheduler, collection-cadence policy, or taxonomy logic belongs in this PR.

This file is not a living specification and should not be needed after the PR review if the final diff is self-explanatory.
