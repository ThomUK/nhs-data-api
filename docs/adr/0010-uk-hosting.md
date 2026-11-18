# 0010. Hosting: one container on a London server, behind Cloudflare

- Status: Accepted
- Date: 2026-11-18 (proposed 2026-11-17)

## Context

UK residency matters for messaging. The served data changes once a month, is read-only and
small (about 6 MB of precomputed measures and organisation data), so no database or
autoscaling platform is needed. The author already runs a personal server in London with
nginx. Options considered: Google Cloud Run (London; near-free at low traffic, cold starts,
per-use billing), a DigitalOcean droplet (London; about $6 a month), and the existing server.

## Decision

- Run the API as **one Docker container on the existing personal London server**, bound to
  127.0.0.1 and served by the existing nginx as `api.<domain>`, with read-only filesystem
  and memory/CPU limits so it cannot affect other sites on the host.
- Put **Cloudflare** in front: caching (responses carry `Cache-Control`; data version in
  `X-Data-Version`), rate limiting and DDoS protection. nginx can refuse connections that
  bypass Cloudflare.
- **Each release is an immutable image** containing the code and that month's data bundle,
  built by GitHub Actions and stored in GitHub's container registry. Releases are blocked
  unless every archived NHS England provider workbook reconciles exactly. Rollback is
  redeploying a previous image tag.
- The server holds no state: everything is rebuilt from the archive (ADR 0012) and the
  registry, so it needs no backups and can be replaced by following `docs/deploy.md`.
- Public docs and the admin site are hosted separately (static), not on this server.

## Consequences

- Marginal cost about zero (existing server), plus a domain.
- Honest claim: "served from London". The container is portable to a UK-owned provider
  without changes if a stronger UK-hosting claim is needed.
- Single machine, no redundancy: an outage means downtime. Acceptable at this stage.
- Before public launch: API keys and per-key usage (ADR 0003), a product name and domain.
