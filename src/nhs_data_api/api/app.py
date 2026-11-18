"""HTTP API (ADR 0011): catalogue and RTT measures."""

from __future__ import annotations

from datetime import date
from typing import Literal

import polars as pl
from fastapi import FastAPI, HTTPException, Query, Request

from .. import __version__
from ..catalogue import load_catalogue
from ..paths import PROCESSED_DIR
from ..store import NoDataError, read_organisations, read_rtt_metrics, read_submissions

app = FastAPI(
    title="NHS Data API (working title)",
    version=__version__,
    description=(
        "Public NHS England statistics with definitions, sources and caveats attached. "
        "Every response includes a `meta` block citing the source publication and licence, "
        "and defining each measure returned."
    ),
)

# Data changes once a month, so successful responses can be cached. Browsers keep them for
# an hour; the CDN (Cloudflare) for a day, and is purged or expires after each release.
CACHE_CONTROL = "public, max-age=3600, s-maxage=86400"


def _data_version() -> str:
    path = PROCESSED_DIR / "bundle.json"
    try:
        import json
        return json.loads(path.read_text())["data_version"]
    except (FileNotFoundError, KeyError, ValueError):
        return "dev"


@app.middleware("http")
async def cache_headers(request: Request, call_next):
    response = await call_next(request)
    if request.method == "GET" and response.status_code == 200:
        response.headers.setdefault("Cache-Control", CACHE_CONTROL)
    else:
        response.headers.setdefault("Cache-Control", "no-store")
    response.headers["X-Data-Version"] = _data_version()
    return response


View = Literal["national", "provider", "provider_icb", "population_icb", "population_sub_icb"]
MAX_ROWS = 1000


def _meta(dataset_id: str, measures: list[str] | None = None, **extra) -> dict:
    ds = load_catalogue()[dataset_id]
    meta = {
        "dataset": ds.id,
        "title": ds.title,
        "source_page": str(ds.source_page),
        "licence": ds.licence.name,
        "attribution": ds.attribution,
        "caveats": [c.model_dump(exclude_none=True) for c in ds.caveats],
    }
    if measures is not None:
        meta["measures"] = {
            m.id: m.model_dump(exclude_none=True, include={"label", "unit", "definition",
                                                           "status", "caveat", "standard"})
            for m in ds.measures if m.id in measures
        }
    return {**meta, **extra}


@app.get("/health")
def health() -> dict:
    """Service status, code version and data version."""
    return {"status": "ok", "version": __version__, "data_version": _data_version()}


@app.get("/v1/datasets")
def list_datasets() -> dict:
    """Datasets available, with status, frequency and a short summary."""
    return {"data": [{"id": d.id, "title": d.title, "status": d.status, "frequency": d.frequency,
                      "summary": d.summary.strip()} for d in load_catalogue().values()]}


@app.get("/v1/datasets/{dataset_id}")
def get_dataset(dataset_id: str) -> dict:
    """Full catalogue entry for one dataset: measures, views, dimensions, codes and caveats."""
    ds = load_catalogue().get(dataset_id)
    if ds is None:
        raise HTTPException(404, f"unknown dataset {dataset_id!r}")
    return {"data": ds.model_dump(mode="json")}


@app.get("/v1/rtt/metrics")
def rtt_metrics(
    view: View = Query("provider", description=(
        "provider / provider_icb: where patients are treated. "
        "population_icb / population_sub_icb: where patients' care is commissioned "
        "(residents, wherever treated). national: England.")),
    org: str | None = Query(None, description="ODS code within the view, e.g. RJ1 or QKK"),
    period: date | None = Query(None, description="Month as YYYY-MM-01; default latest"),
    period_from: date | None = Query(None, description="Start of a range (inclusive)"),
    treatment_function: str = Query("C_999", description="Treatment function code; C_999 = all"),
    measures: str | None = Query(None, description="Comma-separated measure ids; default all"),
    include_experimental: bool = Query(False, description="Include experimental measures"),
) -> dict:
    """RTT v1 measures for one view, filtered by organisation, period and specialty."""
    try:
        lf = read_rtt_metrics(PROCESSED_DIR)
    except NoDataError as exc:
        raise HTTPException(503, str(exc)) from exc
    ds = load_catalogue()["rtt"]
    available = {m.id: m for m in ds.measures if m.computed}
    if measures:
        wanted = [m.strip() for m in measures.split(",")]
        unknown = [m for m in wanted if m not in available]
        if unknown:
            raise HTTPException(422, f"unknown measures {unknown}; see /v1/datasets/rtt")
    else:
        wanted = [m for m, spec in available.items()
                  if include_experimental or spec.status != "experimental"]

    lf = lf.filter((pl.col("view") == view)
                   & (pl.col("treatment_function_code") == treatment_function))
    if org:
        lf = lf.filter(pl.col("org_code") == org.upper())
    latest = lf.select(pl.col("period").max()).collect().item()
    if latest is None:
        raise HTTPException(404, "no rows match")
    if period_from:
        lf = lf.filter(pl.col("period").is_between(period_from, period or latest))
    else:
        lf = lf.filter(pl.col("period") == (period or latest))
    df = (lf.select(["period", "org_code", "org_name", "treatment_function_code", *wanted])
          .sort(["period", "org_code"]).collect())
    if df.is_empty():
        if org:
            raise HTTPException(404, (
                f"{org.upper()} has data in this view, but not for the requested period. "
                "If it is a provider, it may not have submitted that month, or may have been "
                "recoded; see /v1/rtt/submissions."))
        raise HTTPException(404, "no rows match")
    truncated = df.height > MAX_ROWS
    return {
        "data": df.head(MAX_ROWS).to_dicts(),
        "meta": _meta("rtt", measures=wanted, view=view, rows=df.height, truncated=truncated),
    }


@app.get("/v1/rtt/submissions")
def rtt_submissions() -> dict:
    """Providers submitting each month; why last month's providers are missing (merged or
    recoded, closed, not submitted); and NHS trusts that have not submitted for longer."""
    try:
        df = read_submissions(PROCESSED_DIR)
    except NoDataError as exc:
        raise HTTPException(503, str(exc)) from exc
    return {"data": df.to_dicts(),
            "meta": _meta("rtt", measures=["providers_submitting", "new_non_submitters"])}


def _org_record(row: dict) -> dict:
    keep = ["org_code", "name", "sector", "primary_role", "primary_role_name", "status",
            "operational_start", "operational_end", "legal_start", "legal_end", "closed_on",
            "postcode", "address_line1", "town", "operated_by", "successors", "predecessors"]
    return {k: row.get(k) for k in keep}


@app.get("/v1/organisations")
def list_organisations(
    q: str | None = Query(None, description="Search name or ODS code, e.g. 'bristol' or 'RA7'"),
    sector: Literal["nhs_trust", "independent_sector", "commissioner", "other"] | None = None,
    limit: int = Query(50, ge=1, le=500),
) -> dict:
    """Organisations that appear in the statistics, from the ODS snapshot."""
    try:
        df = read_organisations(PROCESSED_DIR)
    except NoDataError as exc:
        raise HTTPException(503, str(exc)) from exc
    if q:
        needle = q.strip().upper()
        df = df.filter(pl.col("org_code").str.to_uppercase().eq(needle)
                       | pl.col("name").str.to_uppercase().str.contains(needle, literal=True))
    if sector:
        df = df.filter(pl.col("sector") == sector)
    rows = df.sort("name").head(limit).to_dicts()
    return {"data": [_org_record(r) for r in rows],
            "meta": _meta("organisations", rows=df.height, truncated=df.height > limit)}


@app.get("/v1/organisations/{org_code}")
def get_organisation(org_code: str) -> dict:
    """One organisation, with ODS successor/predecessor links and curated lineage links."""
    from .. import ods
    try:
        df = read_organisations(PROCESSED_DIR)
    except NoDataError as exc:
        raise HTTPException(503, str(exc)) from exc
    code = org_code.upper()
    row = df.filter(pl.col("org_code") == code)
    if row.is_empty():
        raise HTTPException(404, f"{code} is not an organisation in the statistics")
    curated = [{"from": lk.from_code, "to": lk.to_code, "effective": lk.effective,
                "evidence": lk.evidence.strip()}
               for lk in ods.curated_links() if code in (lk.from_code, lk.to_code)]
    return {"data": {**_org_record(row.to_dicts()[0]), "curated_lineage": curated},
            "meta": _meta("organisations")}
