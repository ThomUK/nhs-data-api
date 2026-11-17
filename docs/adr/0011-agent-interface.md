# 0011. Agent interface: OpenAPI, MCP, llms.txt

- Status: Accepted
- Date: 2026-11-17

## Context

Agents discover and call APIs through tool definitions (MCP), OpenAPI specs, or plain-text
guides. They work best with task-shaped tools, small responses (token budgets) and explicit
provenance.

## Decision

One core HTTP API, exposed three ways, all described from the catalogue (0007):

1. **REST + OpenAPI** for human programmers and generic agent frameworks.
2. **Remote MCP server** (streamable HTTP) as a thin layer over the REST API, with
   task-shaped tools, e.g. `find_organisation`, `get_rtt_performance`,
   `compare_organisations`, `describe_measure`.
3. **`llms.txt`** and per-dataset markdown summaries.

Response conventions:

- Every response carries a `meta` block: dataset, vintage, source file URL, licence and
  attribution, and any caveats that apply to the rows returned.
- Small by default (pagination, sensible default filters); bulk access is a separate route.
- Stable identifiers: ODS codes, ISO dates for periods, catalogue measure ids.

## Consequences

- MCP and REST cannot drift, because MCP calls REST and both read the catalogue.
