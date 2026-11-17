# 0009. Source acquisition and polite fetching

- Status: Accepted
- Date: 2026-11-17

## Context

Tested on 2026-11-17:

- `www.england.nhs.uk` **HTML pages** return HTTP 202 with an AWS WAF JavaScript
  challenge (`x-amzn-waf-action: challenge`) to non-browser clients.
- **Direct file URLs** under `/statistics/wp-content/uploads/...` download normally.
- The ODS ORD API answers normally.

File URLs contain unpredictable suffixes (sizes, IDs), so they cannot be guessed. Discovery
needs the HTML pages.

## Decision

- **Do not circumvent bot protection.** No headless-browser evasion of the WAF challenge.
- Discovery options, in order of preference:
  1. Ask NHS England (statistics team) for a supported machine-readable route or for
     allowlisting of an identified ingestion client. This is also a relationship worth having.
  2. A **source manifest** (`catalogue/sources/*.yaml`) of file URLs, maintained by hand
     from an ordinary browser visit on release day, from which ingestion downloads files.
  3. Other official listings of the same files (e.g. data.gov.uk), if current.
- All requests identify the client with a descriptive User-Agent including a contact URL,
  are rate-limited, and never re-download files whose hash is already archived.

## Consequences

- Release-day ingestion is semi-manual until (1) is resolved. Acceptable at monthly/weekly
  cadence for a side project.
- Good standing with publishers is protected, which matters for the trust positioning.
