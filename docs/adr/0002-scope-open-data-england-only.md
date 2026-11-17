# 0002. Scope: open data, England only

- Status: Accepted
- Date: 2026-11-17

## Context

Most NHS England statistics are published under the Open Government Licence v3 (OGL),
which permits commercial reuse with attribution. Some adjacent data (SNOMED CT and dm+d via
TRUD, NHS website syndication content, patient-level data such as HES) carries other terms
or is not public at all. Scotland, Wales and Northern Ireland have separate statistical
systems with different definitions.

## Decision

- Serve **only openly licensed (OGL or equivalent) data**. Nothing that needs a data-sharing
  agreement, registration-gated licence or patient-level access.
- **England only.**
- Initial datasets, in order:
  1. Referral to Treatment (RTT) waiting times (monthly)
  2. Waiting List Minimum Data Set (WLMDS) (weekly)
  3. Diagnostics waiting times and activity (DM01) (monthly)
  4. NHS workforce statistics (monthly)

## Consequences

- Every dataset entry in the catalogue must record its licence and attribution statement.
- Licensing is never a blocker to commercial use later.
- Adding a non-OGL source requires a new ADR.
