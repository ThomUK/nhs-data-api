"""Derived RTT measures computed from band counts (see catalogue/datasets/rtt.yaml)."""

from __future__ import annotations

import polars as pl

KNOWN = pl.col("weeks_band") != "unknown_clock_start"


def rtt_summary(long: pl.DataFrame, by: list[str]) -> pl.DataFrame:
    """Waiting-list summary for incomplete pathways (Part_2), grouped by `by`."""
    inc = long.filter((pl.col("rtt_part_type") == "Part_2") & KNOWN)
    summary = inc.group_by(by).agg(
        pl.col("patients").sum().alias("incomplete_pathways_total"),
        pl.col("patients").filter(pl.col("weeks_upper") <= 18).sum().alias("_within_18"),
        pl.col("patients").filter(pl.col("weeks_lower") >= 52).sum().alias("waiting_over_52_weeks"),
    )
    medians = (
        inc.group_by(by + ["weeks_lower", "weeks_upper"]).agg(pl.col("patients").sum())
        .group_by(by).agg(pl.struct("weeks_lower", "weeks_upper", "patients").alias("_bands"))
        .with_columns(pl.col("_bands").map_elements(_median_from_bands, return_dtype=pl.Float64)
                      .alias("median_wait_weeks"))
        .drop("_bands")
    ) if by else None
    summary = summary.with_columns(
        (100 * pl.col("_within_18") / pl.col("incomplete_pathways_total"))
        .round(1).alias("pct_within_18_weeks")
    ).drop("_within_18")
    if medians is not None:
        summary = summary.join(medians, on=by, how="left")
    return summary.sort(by)


def _median_from_bands(bands: list[dict] | pl.Series) -> float | None:
    rows = sorted(list(bands), key=lambda r: r["weeks_lower"])
    total = sum(r["patients"] for r in rows)
    if total == 0:
        return None
    half, cum = total / 2, 0
    for r in rows:
        if cum + r["patients"] >= half:
            if r["weeks_upper"] is None:
                return float(r["weeks_lower"])
            width = r["weeks_upper"] - r["weeks_lower"]
            return round(r["weeks_lower"] + width * (half - cum) / r["patients"], 1)
        cum += r["patients"]
    return None
