"""Compare archived versions (vintages) of the same reporting month.

NHS England revises earlier months by republishing them. Every archived version is kept
(ADR 0006), so for any month with two or more versions this module reports what changed:
rows added, removed and changed at the publication's own grain, and the change in each
snapshot measure for England and every provider.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import polars as pl

from .catalogue import load_catalogue
from .metrics import compute_view
from .schedule import add_months, nth_weekday

GRAIN = ["provider_org_code", "commissioner_org_code", "rtt_part_type",
         "treatment_function_code", "weeks_band"]
TOP_N = 25


def snapshot_measures() -> list[str]:
    """Measures that depend on one month only (month-on-month measures are excluded)."""
    return [m.id for m in load_catalogue()["rtt"].measures
            if m.computed and not m.requires_previous_month]


def expected_first_release(period: date) -> date:
    """Second Thursday of the month two months after the reporting month."""
    month = add_months(period, 2)
    return nth_weekday(month.year, month.month, 3, 2)


def archived_vintages(processed_dir: Path) -> pl.DataFrame:
    """(period, vintage) for every processed file."""
    rows = []
    for f in sorted((processed_dir / "rtt").glob("vintage=*/period-*.parquet")):
        vintage = date.fromisoformat(f.parent.name.split("=", 1)[1])
        y, m = f.stem.removeprefix("period-").split("-")
        rows.append({"period": date(int(y), int(m), 1), "vintage": vintage, "path": str(f)})
    return pl.DataFrame(rows, schema={"period": pl.Date, "vintage": pl.Date, "path": pl.Utf8})


def compare(old: pl.DataFrame, new: pl.DataFrame) -> tuple[dict, pl.DataFrame]:
    """Compare two versions of one month. Returns (summary, measure changes)."""
    keyed_old = old.group_by(GRAIN).agg(pl.col("patients").sum().alias("old"))
    keyed_new = new.group_by(GRAIN).agg(pl.col("patients").sum().alias("new"))
    rows = keyed_old.join(keyed_new, on=GRAIN, how="full", coalesce=True)
    added = rows.filter(pl.col("old").is_null()).height
    removed = rows.filter(pl.col("new").is_null()).height
    changed = rows.filter(pl.col("old").is_not_null() & pl.col("new").is_not_null()
                          & (pl.col("old") != pl.col("new"))).height
    by_part = (rows.group_by("rtt_part_type")
               .agg(pl.col("old").sum(), pl.col("new").sum())
               .with_columns((pl.col("new") - pl.col("old")).alias("change"))
               .sort("rtt_part_type"))

    measures = snapshot_measures()
    keys = ["org_code", "org_name", "treatment_function_code"]
    frames = []
    for view in ("national", "provider"):
        a = compute_view(old, view).select(*keys, *measures)
        b = compute_view(new, view).select(*keys, *measures)
        joined = a.join(b, on=["org_code", "treatment_function_code"], how="full",
                        coalesce=True, suffix="_new")
        long = []
        for m in measures:
            long.append(joined.select(
                pl.lit(view).alias("view"), "org_code",
                pl.coalesce("org_name", "org_name_new").alias("org_name"),
                "treatment_function_code", pl.lit(m).alias("measure"),
                pl.col(m).cast(pl.Float64).alias("old"),
                pl.col(f"{m}_new").cast(pl.Float64).alias("new")))
        frames.append(pl.concat(long))
    changes = (pl.concat(frames)
               .filter(~(pl.col("old").eq_missing(pl.col("new"))))
               .with_columns((pl.col("new") - pl.col("old")).alias("change")))
    summary = {
        "rows_compared": rows.height, "rows_added": added, "rows_removed": removed,
        "rows_changed": changed,
        "patients_by_part": by_part.to_dicts(),
        "providers_changed": changes.filter(pl.col("view") == "provider")["org_code"].n_unique(),
        "national_changes": changes.filter((pl.col("view") == "national")
                                           & (pl.col("treatment_function_code") == "C_999"))
                                   .select("measure", "old", "new", "change").to_dicts(),
    }
    return summary, changes


def build_revisions(processed_dir: Path) -> Path:
    """Write processed/revisions/rtt.json (and per-comparison parquet details)."""
    versions = archived_vintages(processed_dir)
    out_dir = processed_dir / "revisions" / "rtt"
    out_dir.mkdir(parents=True, exist_ok=True)
    periods = []
    for (period,), grp in versions.sort("period").group_by(["period"], maintain_order=True):
        grp = grp.sort("vintage")
        first = expected_first_release(period)
        vintages = grp["vintage"].to_list()
        entry = {"period": period, "vintages": vintages, "expected_first_release": first,
                 "original_archived": vintages[0] <= first, "comparisons": []}
        paths = grp["path"].to_list()
        for i in range(1, len(vintages)):
            old, new = pl.read_parquet(paths[i - 1]), pl.read_parquet(paths[i])
            summary, changes = compare(old, new)
            detail = out_dir / f"{period:%Y-%m}_{vintages[i - 1]}_{vintages[i]}.parquet"
            changes.write_parquet(detail)
            top = (changes.filter((pl.col("view") == "provider")
                                  & (pl.col("treatment_function_code") == "C_999")
                                  & (pl.col("measure") == "waiting_list_total"))
                   .sort(pl.col("change").abs(), descending=True).head(TOP_N))
            entry["comparisons"].append({"old": vintages[i - 1], "new": vintages[i],
                                         **summary, "top_provider_changes": top.to_dicts()})
        periods.append(entry)
    out = processed_dir / "revisions" / "rtt.json"
    out.write_text(json.dumps({"dataset": "rtt", "periods": periods}, indent=2, default=str))
    return out
