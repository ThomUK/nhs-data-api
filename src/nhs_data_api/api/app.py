"""HTTP API (ADR 0011): catalogue and RTT measures."""

from __future__ import annotations

from datetime import date
from typing import Literal

import polars as pl
from fastapi import FastAPI, HTTPException, Query

from .. import __version__
from ..catalogue import load_catalogue
from ..paths import PROCESSED_DIR
from ..store import NoDataError, read_rtt_metrics, read_submissions

app = FastAPI(
    title="NHS Data API (working title)",
    version=__version__,
    description=(
        "Public NHS England statistics with definitions, sources and caveats attached. "
        "Every response includes a `meta` block citing the source publication and licence, "
        "and defining each measure returned."
    ),
)

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
    return {"status": "ok", "version": __version__}


@app.get("/v1/datasets")
def list_datasets() -> dict:
    return {"data": [{"id": d.id, "title": d.title, "status": d.status, "frequency": d.frequency,
                      "summary": d.summary.strip()} for d in load_catalogue().values()]}


@app.get("/v1/datasets/{dataset_id}")
def get_dataset(dataset_id: str) -> dict:
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
    """Providers submitting each month, and providers that submitted last month but not this."""
    try:
        df = read_submissions(PROCESSED_DIR)
    except NoDataError as exc:
        raise HTTPException(503, str(exc)) from exc
    return {"data": df.to_dicts(),
            "meta": _meta("rtt", measures=["providers_submitting", "new_non_submitters"])}
