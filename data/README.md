# Local data directory

Runtime data belongs here and is intentionally ignored by Git.

Expected layout:

```text
data/
  raw/
  normalized/
  reports/
```

Raw snapshots are immutable once written. Never commit collected market data to the repository.
