# 0005. Python stack

- Status: Accepted
- Date: 2026-11-17

## Context

The author is comfortable in R and Python. The system needs messy spreadsheet parsing,
scheduled ingestion, an HTTP API with an OpenAPI spec, and an MCP server.

## Decision

Python 3.12+, managed with `uv`.

- **Polars** for parsing and transformation.
- **Polars lazy scans** over Parquet at serve time to start; **DuckDB** added when SQL-style
  querying is needed (e.g. ad hoc analysis, bulk export). Both read the same files.
- **FastAPI** for the HTTP API (generates the OpenAPI spec for free).
- The official **MCP Python SDK** for the agent interface.
- **Pydantic** for catalogue and response schemas.
- **pytest** and **ruff** for tests and linting.

## Consequences

- R remains useful for exploratory analysis; an R client package for the API is a natural
  later contribution to the NHS-R community.
- One language across ingestion and serving keeps a solo project manageable.
