# 0012. Durable raw archive in a private git repository

- Status: Accepted
- Date: 2026-11-17

## Context

The raw archive (ADR 0006) is the only irreplaceable data: NHS England replaces files when it
revises them (originals of 10 of the first 18 RTT months loaded were already superseded),
and everything processed can be regenerated from it (`st rebuild-rtt`, `st fetch-ods`
snapshot). Until now it lived only in an ephemeral working environment.

It is small: compressed zips of a few MB each, about 4 MB a month for RTT, 76 MB in
November 2026, and expected to stay well under 1 GB for years with all four datasets.

## Decision

- Store the raw archive in a **private GitHub repository** (`ThomUK/nhs-data-archive`), as
  plain git (files are far below GitHub's 100 MB limit; no LFS needed).
- Layout as ADR 0006: `<dataset>/<publication date>/<original file>` with `.meta.json`
  sidecars, plus `MANIFEST.csv` (path, bytes, SHA-256, source URL, retrieval) and a README.
- `ST_RAW_DIR` points the code at the archive checkout. `st archive-push` refreshes the
  manifest, refuses to continue if any archived file changed or disappeared, then commits and
  pushes. `st archive-verify` checks every file against the manifest and sidecars.
- Processed data is not stored; it is rebuilt from the archive.
- Revisit when the public API is deployed: move to UK-region or UK-owned object storage
  (ADR 0010). Code reads only `ST_RAW_DIR`, so the move needs no code changes.

## Consequences

- Free, versioned, and restorable in minutes: clone, then rebuild.
- Hosted by GitHub (US). Acceptable for an internal archive of open data; not used for any
  "UK hosted" claim about the service.
- Archive pushes are a manual step in the monthly routine, after ingest.
