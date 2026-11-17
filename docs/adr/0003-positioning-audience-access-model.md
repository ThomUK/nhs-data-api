# 0003. Positioning, audience and access model

- Status: Accepted
- Date: 2026-11-17

## Context

The data is free to reuse, so ownership of data is not a business. The value is in the
work between raw publications and a trustworthy answer: organisation history across mergers,
consistent time series across format changes, preserved revisions, fast loading after
release, and explicit provenance and caveats.

The project is a solo, unfunded side project. The near-term goal is **reputation and
trust** (being known as a reliable NHS data source ahead of national data-platform
procurement over the next two years), not revenue. Commercial options must remain open.

AI agents are a new and growing consumer. An agent's main risk with health data is
confident error, so responses that carry citations and caveats are worth more to agents
than raw files.

## Decision

- **Positioning:** "the trustworthy, citable source of NHS England performance data, for
  humans and agents." A product brand, visibly backed by a named NHS analyst.
- **Access model, phase 1 (now):** free.
  - Anonymous access at a low rate limit, so agents can try it with no sign-up.
  - Free API keys for higher limits, issued from day one, so we know who uses it and can
    contact them.
  - Usage metered per key from day one, so later pricing decisions use real data.
- **Phase 2 (deferred):** paid tiers on volume, history depth, bulk export, webhooks,
  freshness guarantees and SLA. Enterprise: support and custom work.
- The metering layer stays independent of payment method, so per-call agent payments
  (HTTP 402-style) can be added later without redesign.
- **Distribution:** short, neutral release-day commentary drives reputation more than the
  API alone. The API and agent tools are the evidence behind it.

## Consequences

- Running costs must stay near zero (see 0006, 0010).
- The author must confirm their employment contract permits this outside work and public
  commentary, and keep it on their own time and equipment.
- Commentary stays factual and politically neutral.
