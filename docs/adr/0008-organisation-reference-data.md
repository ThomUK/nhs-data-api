# 0008. Organisation reference data from the public ODS ORD API

- Status: Accepted
- Date: 2026-11-17

## Context

Joining data over time needs organisation history: trust mergers, the CCG→ICB transition,
provider/commissioner hierarchies. NHS England's ODS FHIR API requires onboarding as a
registered consumer. The older **ODS ORD API** (`directory.spineservices.nhs.uk/ORD/2-0-0`)
was confirmed on 2026-11-17 to answer without a key, and returns roles, relationships and
successor/predecessor links (`Succs`).

## Decision

- Build the organisation table from the **ORD API**, plus the organisation codes and names
  that appear in the statistical publications themselves.
- Store snapshots in the raw archive like any other source.
- Model organisations as: `org_code`, name, primary role, status, open/close dates, parent
  relationships, and successor edges. Provide a `resolve(org_code, as_at)` function that
  follows successors.
- Move to the ODS FHIR API once registered as a consumer, behind the same interface.

## Consequences

- No registration dependency for the first release.
- **Risk:** the ORD API may be deprecated in favour of FHIR. Check its status before
  relying on it in production; the interface boundary keeps the switch cheap.
