# 0006. Storage: raw archive, Parquet, vintages

- Status: Accepted
- Date: 2026-11-17

## Context

NHS England revises published figures and occasionally withdraws old files. Analysts care
about both the figure as first published and the latest revised figure. Data volumes for
the chosen datasets are modest (GBs, not TBs) and change at most weekly.

## Decision

Three layers, all plain files:

1. **Raw archive** `data/raw/<dataset>/<publication_date>/<original_filename>`: every
   downloaded file kept unchanged, with a sidecar `.meta.json` recording source URL,
   retrieval time and SHA-256. Never modified or deleted.
2. **Processed** `data/processed/<dataset>/vintage=<publication_date>/*.parquet`: tidy,
   long-format tables, one partition per publication ("vintage").
3. **Serving views** computed over the Parquet (Polars or DuckDB): `latest` (most recent vintage per
   period) and `as_published` (first vintage per period).

No database server.

## Consequences

- Tiny hosting cost; files are portable between providers (0010).
- Every served value can be traced to a raw file and its hash.
- The raw archive itself becomes a valuable asset over time.
- Object storage (S3-compatible) can replace local disk later without changing the layout.
