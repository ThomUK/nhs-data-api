# secondthursday

Public NHS England performance statistics served from modern API endpoints, built to be
equally useful to AI agents and human programmers. Every number comes back with its
definition, source publication, licence and known caveats.

**Status:** early spike. RTT ingestion, 28 measures and the API work on the real Aug and Sep
2026 files, and match NHS England's published figures exactly
([validation](docs/validation/rtt-2026-09.md)).

## Principles

- Open data only (OGL), England only. See [ADR 0002](docs/adr/0002-scope-open-data-england-only.md).
- Trustworthy and citable: provenance and caveats in every response.
- Code private, semantics public: [ADR 0004](docs/adr/0004-private-code-public-semantics.md).
- Near-zero running cost: plain files (raw archive + Parquet), no database server.

All decisions are in [`docs/adr/`](docs/adr/README.md).

## Layout

```
catalogue/          public semantic catalogue: datasets, measures, caveats, source manifests
docs/adr/           architecture decision records
site/               static admin site (GitHub Pages); data exported by `st build-site`
src/nhs_data_api/
  catalogue.py      catalogue models and loader
  ingest/fetch.py   polite downloader into the immutable raw archive
  ingest/rtt.py     RTT Full CSV -> tidy long Parquet
  ingest/rtt_published.py  reconcile against NHS England's published provider workbook
  metrics.py        RTT v1 measures for all views (provider and population)
  store.py          reading/writing the processed layer and precomputed metrics
  ods.py            organisation reference data (ODS ORD API) and successor resolution
  api/app.py        FastAPI app
tests/
data/               local data lake (git-ignored)
```

## Getting started

```bash
uv sync
uv run pytest
uv run st catalogue-check
uv run st ingest-rtt path/to/Full-CSV-data-file.zip --vintage 2026-11-13
uv run st build-rtt-metrics                         # also runs after each ingest
uv run st reconcile-rtt Incomplete-Provider.xlsx --period 2026-09-01
uv run uvicorn nhs_data_api.api.app:app --reload   # then open /docs
```

## Data storage and restore

Source files are kept in a private archive repository
([ADR 0012](docs/adr/0012-durable-raw-archive.md)); everything else is rebuilt from it.

```bash
git clone https://github.com/ThomUK/nhs-data-archive ../nhs-data-archive
export ST_RAW_DIR=../nhs-data-archive ST_DATA_DIR=/path/to/scratch/data
uv run st archive-verify          # every file matches MANIFEST.csv
uv run st rebuild-rtt             # processed layer + metrics (~3 minutes)
uv run st build-site
```

After adding files each month: `uv run st archive-push -m "RTT October 2026"`.

## Deployment

One container per release (code plus that month's data) on a London server behind nginx and
Cloudflare; GitHub Actions rebuilds from the archive, blocks the release unless figures
reconcile with NHS England, then deploys. Runbook: [docs/deploy.md](docs/deploy.md);
decision: [ADR 0010](docs/adr/0010-uk-hosting.md).

## API documentation

Generated into [`site/api/`](site/api/index.html) by `uv run st build-docs` (also run by
`st build-site`): overview, endpoint reference from the OpenAPI spec with real example
responses, dataset and measure pages from the catalogue, `openapi.json` and `llms.txt`.
It is self-contained so it can be hosted publicly on its own.

## Admin site

A static admin site in [`site/`](site/README.md) (GitHub Pages): publication calendar with the
files to collect on each date, RTT time series with anomaly flags, and validation results
(reconciliation, submissions, organisation lineage and revisions; `st diff-vintages`).
Rebuild its data with `uv run st build-site`.

## API (first slice)

- `GET /v1/datasets`, `GET /v1/datasets/{id}`: catalogue, definitions and caveats.
- `GET /v1/rtt/metrics`: the RTT v1 measures.
  - `view`: `national`, `provider`, `provider_icb`, `population_icb` (residents, wherever
    treated), `population_sub_icb`
  - `org`, `period` or `period_from`, `treatment_function` (default `C_999`, all specialties)
  - `measures` (comma-separated), `include_experimental`
- `GET /v1/rtt/submissions`: providers submitting each month, why providers stopped reporting
  (merged or recoded, closed, not submitted), and NHS trusts still not submitting.
- `GET /v1/organisations?q=&sector=`, `GET /v1/organisations/{code}`: ODS organisation table
  with successor and curated lineage links.

## Next steps

1. Each month: ingest the Full CSV, then `st reconcile-rtt` against the Incomplete Provider
   workbook before publishing.
2. Contact the NHS England statistics team about a supported machine-readable route
   ([ADR 0009](docs/adr/0009-source-acquisition.md)).
3. Refresh the ODS snapshot (`st fetch-ods`) when new organisations appear, and review lineage
   candidates on the admin site's validation page.
4. Inspect WLMDS files and complete `catalogue/datasets/wlmds.yaml`.
5. MCP server over the API ([ADR 0011](docs/adr/0011-agent-interface.md)), API keys and metering.

## Attribution

Contains public sector information licensed under the Open Government Licence v3.0.
