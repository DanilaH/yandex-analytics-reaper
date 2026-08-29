# Local data directory

Runtime data belongs here and is intentionally ignored by Git.

Expected layout:

```text
data/
  raw/
  normalized/
  reports/
  sessions/
```

Raw snapshots are immutable once written. Never commit collected market data to the repository.

`sessions/` is operational local state for reusable HTTP profiles. Persistent anonymous profiles may contain raw cookie values required to reuse the same browser-like identity across probes. These files are not analytical evidence: never commit, publish, or share them. Raw snapshots and SQLite provenance must contain only safe session metadata such as the profile label, stable non-secret local profile-instance ID, cookie-state fingerprint, and profile age. The instance ID is cohort provenance for one local persistent profile and is not a Yandex account/user identifier or credential.
