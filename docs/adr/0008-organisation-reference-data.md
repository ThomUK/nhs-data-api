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

## Update 2026-11-17: implemented

- `st fetch-ods` snapshots ORD records for every organisation code in the loaded statistics
  (734 in November 2026, about three minutes at a gentle request rate) into
  `raw/ods/<date>/organisations.jsonl`, plus the ORD role list. The organisation table
  (`processed/ods/organisations.parquet`) adds sector (NHS trust, independent sector,
  commissioner), address, operator (RE6) and closure dates.
- **Lineage** combines ODS successor records with curated links in
  `catalogue/organisation_lineage.yaml`. Curated links are needed because a change of
  operator issues new site codes without a successor record (Practice Plus Group sites,
  September 2026). Only `confirmed` links are applied; `proposed` links and automatically
  detected candidates (a provider stops as a new code starts at the same address) are listed
  on the admin site's validation page for review.
- Links take effect from their effective date, and each row carries two lineage codes (as of
  its own month and as of the next month), so a merger only joins the two months that span
  it. Like-for-like measures and submission checks use lineage; published figures always stay
  under the publisher's codes.
- Submission status classifies each provider that stops reporting (merged or recoded, closed,
  not submitted) and lists NHS trusts missing for two months or more.
- `/v1/organisations` and `/v1/organisations/{code}` serve the table.
