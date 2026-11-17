# Admin site

Static pages served from GitHub Pages (`.github/workflows/pages.yml`):

- `index.html`: publication calendar and files to collect, with received status.
- `timeseries.html`: RTT measures over time per organisation, plus an anomaly scan.
- `validation.html`: reconciliation runs against NHS England's published figures.

No build step: plain HTML, CSS and ES modules. Data is exported to `site/data/` by
`uv run nda build-site` after ingesting or reconciling, then committed.

Preview locally:

```bash
uv run nda build-site
python -m http.server -d site 8000   # http://localhost:8000
```

Monthly routine: archive the files listed on the calendar (`nda archive ... --publication
YYYY-MM-DD`), `nda ingest-rtt`, `nda reconcile-rtt`, `nda build-site`, commit, merge to main.

Scaling note: `timeseries/provider.json` is ~0.6 MB for two months. Before loading many
years, split it per organisation so pages fetch only what they show.

Screenshots (November 2026, two months of data):
[calendar](../docs/screenshots/admin-calendar.png) ·
[time series](../docs/screenshots/admin-timeseries.png) ·
[anomaly scan](../docs/screenshots/admin-anomaly-scan.png) ·
[validation](../docs/screenshots/admin-validation.png)
