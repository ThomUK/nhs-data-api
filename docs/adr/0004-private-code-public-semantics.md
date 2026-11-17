# 0004. Private code, public semantics

- Status: Accepted
- Date: 2026-11-17

## Context

Open-sourcing everything builds trust and helps public-sector procurement, but lets anyone
run a competing copy. Keeping everything closed undermines trust in a data product.

## Decision

- **Private:** ingestion, parsing, validation, serving and operations code.
- **Public:** the semantic catalogue (dataset and measure definitions, units, caveats,
  sources, licences), organisation lineage mappings, API documentation, OpenAPI spec,
  MCP tool descriptions and `llms.txt`.

## Consequences

- The catalogue (0007) is designed as a publishable artifact from the start: no secrets,
  no internal paths.
- Correctness can be checked by anyone against the original publications, because every
  value cites its source file.
