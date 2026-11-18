# Deploying the API

Design: [ADR 0010](adr/0010-uk-hosting.md). One container (code plus that month's data) on
the personal London server, behind the existing nginx and Cloudflare. GitHub Actions
rebuilds from the archive, **refuses to release unless the figures reconcile with NHS
England's published workbooks**, pushes the image to GitHub's container registry and deploys
over SSH.

```
Cloudflare (cache, rate limits) → nginx :443 (api.<domain>) → 127.0.0.1:8000 → container
```

Replace `api.YOUR-DOMAIN.uk` with the real host name throughout.

## 1. Server, one-off

```bash
# Docker Engine and the compose plugin (Debian/Ubuntu)
curl -fsSL https://get.docker.com | sh

# A deploy user that can run docker (note: docker access is root-equivalent)
sudo adduser --disabled-password --gecos "" deploy
sudo usermod -aG docker deploy
sudo install -d -o deploy -g deploy /opt/nhs-data-api
sudo cp deploy/docker-compose.yml /opt/nhs-data-api/      # from this repository

# Let the server pull the private image: a classic token with only read:packages
sudo -iu deploy docker login ghcr.io -u ThomUK            # paste the token as password

# Security updates
sudo apt-get install -y unattended-upgrades && sudo dpkg-reconfigure -plow unattended-upgrades
```

Add the public half of a new SSH key (ed25519, used only by GitHub Actions) to
`/home/deploy/.ssh/authorized_keys`.

## 2. Domain and Cloudflare

1. Register the domain and change its nameservers to Cloudflare (free plan).
2. DNS: `A api → <server IPv4>` (and `AAAA` if the server has IPv6), **Proxied**.
3. SSL/TLS mode: **Full (strict)**.
4. Optional: a rate-limiting rule for `api.YOUR-DOMAIN.uk/*` (anonymous access, ADR 0003).

## 3. nginx

```bash
sudo cp deploy/nginx/nhs-data-api.conf /etc/nginx/sites-available/
sudo sed -i 's/api.YOUR-DOMAIN.uk/api.example.uk/g' /etc/nginx/sites-available/nhs-data-api.conf
sudo bash deploy/nginx/update-cloudflare-ips.sh            # writes the Cloudflare snippets
sudo mkdir -p /var/www/certbot
sudo certbot certonly --webroot -w /var/www/certbot -d api.example.uk
sudo ln -s /etc/nginx/sites-available/nhs-data-api.conf /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

Existing sites are untouched. Once requests arrive through Cloudflare, uncomment
`if ($from_cloudflare = 0) { return 403; }` in the site to refuse direct connections, and
add a monthly cron job for `update-cloudflare-ips.sh`. (Alternative to certbot: a Cloudflare
origin certificate.)

## 4. GitHub

Repository → Settings → Secrets and variables → Actions:

| Secret | Value |
|---|---|
| `ARCHIVE_TOKEN` | Fine-grained token, **Contents: read** on `ThomUK/nhs-data-archive` only |
| `DEPLOY_HOST` | Server address |
| `DEPLOY_USER` | `deploy` |
| `DEPLOY_SSH_KEY` | Private half of the deploy SSH key |
| `DEPLOY_KNOWN_HOSTS` | Output of `ssh-keyscan -t ed25519 <server>` |

Optional: Settings → Environments → `production` → required reviewers, to approve each
deploy.

## 5. Releasing

Actions → **Release API** → Run workflow. About 10 minutes:

1. checks archive checksums, runs the tests;
2. rebuilds every month from the archive;
3. **release gate**: reconciles each archived Incomplete Provider workbook (fails on any
   mismatch, so nothing is deployed);
4. bundles the served data (~6 MB) into the image, tagged with the data version
   (e.g. `2026-09.202611181200`) and `latest`;
5. deploys, then checks the server reports the new data version.

Monthly routine: archive the release's files, `st archive-push`, then run the workflow.
Cloudflare may serve cached responses for up to a day; purge its cache after a release if
needed.

## Rollback

```bash
ssh deploy@<server>
cd /opt/nhs-data-api
docker images ghcr.io/thomuk/nhs-data-api      # previous tags are kept for 90 days
echo IMAGE_TAG=<previous tag> > .env && docker compose up -d
```

## Checks

- `curl https://api.YOUR-DOMAIN.uk/health` shows the code and data versions.
- Point a free uptime monitor at `/health`.
- Container: `docker compose ps`, `docker compose logs --tail 100`. It runs read-only, with
  512 MB memory and 1 CPU limits, reachable only from the host (port bound to 127.0.0.1).

Tested 2026-11-18: image builds (521 MB, of which the data is 6 MB); it runs healthy under
the compose restrictions using ~140 MB; nginx 1.27 accepts the site config; through nginx,
direct connections are refused when the Cloudflare check is on, POST is refused, HTTP
redirects to HTTPS.
