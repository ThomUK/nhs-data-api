# 0007. Semantic catalogue as single source of truth

- Status: Accepted
- Date: 2026-11-17

## Context

Docs, OpenAPI descriptions, MCP tool descriptions and `llms.txt` all need the same
definitions. Hand-maintaining them separately guarantees drift. Agents need definitions,
units and caveats alongside numbers.

## Decision

`catalogue/` holds one YAML file per dataset describing:

- dataset metadata: publisher, source page, licence, attribution, frequency, geography,
  coverage start, known format changes;
- dimensions and their code lists;
- measures: id, label, definition, unit, aggregation rule, related standards (e.g. the 92%
  18-week standard);
- caveats: dated, scoped known issues (e.g. an organisation's missing submission).

The catalogue is validated by Pydantic models in `nhs_data_api.catalogue` and generates the
docs, API descriptions, MCP descriptions and `llms.txt`. API responses include the relevant
caveats and source citations.

## Consequences

- Adding a dataset starts with writing its catalogue entry.
- The catalogue is public (0004), so it must be written for an outside reader.
