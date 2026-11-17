# 0010. UK hosting, portable deployment

- Status: Proposed
- Date: 2026-11-17

## Context

UK residency matters for messaging, especially if the pitch is about UK alternatives in
national NHS data infrastructure. There is a difference between:

- **UK-resident:** hyperscaler or US-owned provider in a London region (AWS eu-west-2,
  Azure UK South, GCP europe-west2, DigitalOcean LON1, Fly.io lhr).
- **UK-sovereign:** UK-owned provider operating UK data centres.

## Decision

- Package the service as a container with file-based storage (0006) so the provider can
  change without rework.
- Start on the cheapest acceptable UK-resident option; evaluate UK-owned providers before
  any public "UK sovereign" claim.
- Any CDN/edge in front must be described honestly ("UK-hosted origin").

## Consequences

- Hosting choice is deferred to the first public deployment; open questions recorded here.
