"""HTTP API (ADR 0011). Minimal first slice: catalogue and RTT summaries."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl
from fastapi import FastAPI, HTTPException, Query

from .. import __version__
from ..catalogue import load_catalogue
from ..metrics import rtt_summary
from ..paths import PROCESSED_DIR

app = FastAPI(
    title="NHS Data API (working title)",
    version=__version__,
    description=(
        "Public NHS England statistics with definitions, sources and caveats attached. "
        "Every response includes a `meta` block citing the source publication and licence."
    ),
)


def _meta(dataset_id: str, **extra) -> dict:
    ds = load_catalogue()[dataset_id]
    return {
        "dataset": ds.id,
        "title": ds.title,
        "source_page": str(ds.source_page),
        "licence": ds.licence.name,
        "attribution": ds.attribution,
        "caveats": [c.model_dump(exclude_none=True) for c in ds.caveats],
        **extra,
    }


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


def _latest_rtt(processed_dir: Path) -> pl.DataFrame:
    """Latest vintage of each period (ADR 0006 'latest' view)."""
    root = processed_dir / "rtt"
    if not any(root.glob("vintage=*/*.parquet")):
        raise HTTPException(503, "no RTT data has been ingested yet")
    return (
        pl.scan_parquet(root / "vintage=*" / "*.parquet", hive_partitioning=True)
        .filter(pl.col("vintage") == pl.col("vintage").max().over("period"))
        .drop("vintage")
        .collect()
    )


@app.get("/v1/rtt/waiting-list")
def rtt_waiting_list(
    provider: str | None = Query(None, description="Provider ODS code, e.g. RJ1"),
    period: date | None = Query(None, description="Month as YYYY-MM-01; default latest"),
    treatment_function: str = Query("C_999", description="Treatment function code; C_999 = total"),
) -> dict:
    """Waiting-list size, % within 18 weeks, 52+ week waiters and median wait (Part_2)."""
    df = _latest_rtt(PROCESSED_DIR)
    period = period or df["period"].max()
    df = df.filter((pl.col("period") == period)
                   & (pl.col("treatment_function_code") == treatment_function))
    if provider:
        df = df.filter(pl.col("provider_org_code") == provider.upper())
    if df.is_empty():
        raise HTTPException(404, "no rows match")
    out = rtt_summary(df, by=["period", "provider_org_code", "provider_org_name"])
    return {"data": out.to_dicts(), "meta": _meta("rtt", period=str(period),
                                                  measures=["incomplete_pathways_total",
                                                            "pct_within_18_weeks",
                                                            "waiting_over_52_weeks",
                                                            "median_wait_weeks"])}
