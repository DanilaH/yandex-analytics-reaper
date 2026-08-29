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

`sessions/` is operational local state for reusable HTTP profiles. Persistent anonymous profiles may contain raw cookie values required to reuse the same browser-like identity across probes. These files are not analytical evidence: never commit, publish, or share them. Raw snapshots and SQLite provenance must contain only safe session metadata such as the profile label, cookie-state fingerprint, and profile age.
