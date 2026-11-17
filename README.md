# NHS Data API (working title)

Public NHS England performance statistics served from modern API endpoints, built to be
equally useful to AI agents and human programmers. Every number comes back with its
definition, source publication, licence and known caveats.

**Status:** early spike. RTT parsing and a minimal API work against the real Aug and Sep 2026
RTT files.

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
src/nhs_data_api/
  catalogue.py      catalogue models and loader
  ingest/fetch.py   polite downloader into the immutable raw archive
  ingest/rtt.py     RTT Full CSV -> tidy long Parquet
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
uv run nda catalogue-check
uv run nda ingest-rtt path/to/Full-CSV-data-file.zip --vintage 2026-11-13
uv run nda build-rtt-metrics                         # also runs after each ingest
uv run uvicorn nhs_data_api.api.app:app --reload   # then open /docs
```

## API (first slice)

- `GET /v1/datasets`, `GET /v1/datasets/{id}`: catalogue, definitions and caveats.
- `GET /v1/rtt/metrics`: the RTT v1 measures.
  - `view`: `national`, `provider`, `provider_icb`, `population_icb` (residents, wherever
    treated), `population_sub_icb`
  - `org`, `period` or `period_from`, `treatment_function` (default `C_999`, all specialties)
  - `measures` (comma-separated), `include_experimental`
- `GET /v1/rtt/submissions`: providers submitting each month, and new non-submitters.

## Next steps

1. Check the derived national measures against NHS England's published headline figures
   (see `docs/validation/rtt-2026-09.md`).
2. Contact the NHS England statistics team about a supported machine-readable route
   ([ADR 0009](docs/adr/0009-source-acquisition.md)).
3. Build the organisation table from ODS ([ADR 0008](docs/adr/0008-organisation-reference-data.md)).
4. Inspect WLMDS files and complete `catalogue/datasets/wlmds.yaml`.
5. MCP server over the API ([ADR 0011](docs/adr/0011-agent-interface.md)), API keys and metering.

## Attribution

Contains public sector information licensed under the Open Government Licence v3.0.
