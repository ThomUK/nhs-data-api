# Working on nhs-data-api

Public NHS England statistics served as an agent-ready API. Decisions are in `docs/adr/`;
read `README.md` first.

## Data is not in this repository

- Source files live in the private archive repository `ThomUK/nhs-data-archive`
  (ADR 0012). Everything under `data/` is regenerated from it and git-ignored.
- In a fresh session, restore before doing data work:

  ```bash
  git clone --depth 1 https://github.com/ThomUK/nhs-data-archive ../nhs-data-archive
  export ST_RAW_DIR=$(realpath ../nhs-data-archive) ST_DATA_DIR=<scratch dir>/data
  uv run st archive-verify && uv run st rebuild-rtt
  ```

- New source files: `st archive` / `st ingest-rtt --vintage auto`, then
  `st archive-push -m "..."`. Never edit or delete archived files.

## Conventions

- `uv run pytest` and `uv run ruff check .` must pass before committing.
- Measures must reconcile with NHS England's published figures (`st reconcile-rtt`);
  record results in `docs/validation/`.
- Every measure and caveat is defined in `catalogue/`; the API, docs and admin site read it.
- After data changes, `uv run st build-site` and commit `site/data/` (GitHub Pages deploys
  from `main`).
- Organisation lineage links that ODS does not record go in
  `catalogue/organisation_lineage.yaml` with evidence; only `confirmed` links are applied.
