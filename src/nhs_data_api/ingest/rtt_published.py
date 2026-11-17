"""Reconcile our RTT measures against NHS England's published provider workbook.

The "Incomplete Provider" workbook (published alongside the Full CSV) gives, for every
provider and treatment function, the waiting list, the number within 18 weeks, 52/65/78+
week waits, and the median and 92nd percentile. Matching it exactly is our monthly proof
that parsing, basis (English commissioners only) and percentile method are right.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import openpyxl
import polars as pl

SHEETS = ("Provider", "IS Provider")
COLUMNS = {
    "Provider Code": "org_code",
    "Treatment Function Code": "treatment_function_code",
    "Total number of incomplete pathways": "waiting_list_total",
    "Total within 18 weeks": "within_18_weeks",
    "Total 52 plus weeks": "waiting_over_52_weeks",
    "Total 65 plus weeks": "waiting_over_65_weeks",
    "Total 78 plus weeks": "waiting_over_78_weeks",
    "Average (median) waiting time (in weeks)": "median_wait_weeks",
    "92nd percentile waiting time (in weeks)": "p92_wait_weeks",
}
COUNTS = ["waiting_list_total", "within_18_weeks", "waiting_over_52_weeks",
          "waiting_over_65_weeks", "waiting_over_78_weeks"]
PERCENTILES = ["median_wait_weeks", "p92_wait_weeks"]
# We publish percentiles to 1 dp; NHS England publishes them unrounded.
PERCENTILE_TOLERANCE = 0.05 + 1e-9


class PublishedFormatError(ValueError):
    pass


def read_provider_workbook(path: Path) -> pl.DataFrame:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    frames = []
    for name in SHEETS:
        if name not in wb.sheetnames:
            raise PublishedFormatError(f"sheet {name!r} not found in {path.name}")
        rows = wb[name].iter_rows(values_only=True)
        for header in rows:
            if header and "Provider Code" in header:
                break
        else:
            raise PublishedFormatError(f"no header row in sheet {name!r}")
        missing = [c for c in COLUMNS if c not in header]
        if missing:
            raise PublishedFormatError(f"sheet {name!r} missing columns {missing}")
        idx = {c: header.index(c) for c in COLUMNS}
        records = [{COLUMNS[c]: None if r[i] is None else str(r[i]) for c, i in idx.items()}
                   for r in rows if r and r[idx["Provider Code"]]]
        frames.append(pl.DataFrame(records, schema=dict.fromkeys(COLUMNS.values(), pl.Utf8)))
    return pl.concat(frames).with_columns(
        [pl.col(c).cast(pl.Float64).cast(pl.Int64) for c in COUNTS]
        + [pl.col(c).replace("-", None).cast(pl.Float64) for c in PERCENTILES]
    ).filter(pl.col("waiting_list_total") > 0)


@dataclass
class Reconciliation:
    rows_published: int
    rows_compared: int
    missing_from_ours: pl.DataFrame
    missing_from_published: pl.DataFrame
    mismatches: dict[str, pl.DataFrame]

    @property
    def ok(self) -> bool:
        return (self.missing_from_ours.is_empty() and self.missing_from_published.is_empty()
                and all(m.is_empty() for m in self.mismatches.values()))

    def to_json(self, period: str, workbook: str, sample: int = 25) -> dict:
        """Serialisable record of this run, for the admin site."""
        from datetime import UTC, datetime
        return {
            "dataset": "rtt",
            "check": "incomplete_provider_workbook",
            "period": period,
            "workbook": workbook,
            "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "ok": self.ok,
            "rows_published": self.rows_published,
            "rows_compared": self.rows_compared,
            "missing_from_ours": self.missing_from_ours.height,
            "missing_from_published": self.missing_from_published.height,
            "checks": [
                {"measure": k, "mismatches": v.height,
                 "tolerance": PERCENTILE_TOLERANCE if k in PERCENTILES else 0,
                 "sample": v.head(sample).to_dicts()}
                for k, v in self.mismatches.items()
            ],
        }

    def summary(self) -> str:
        lines = [f"published rows (non-zero list): {self.rows_published}",
                 f"compared: {self.rows_compared}",
                 f"published but not ours: {self.missing_from_ours.height}",
                 f"ours but not published: {self.missing_from_published.height}"]
        lines += [f"{k}: {v.height} mismatches" for k, v in self.mismatches.items()]
        lines.append("RESULT: " + ("all match" if self.ok else "MISMATCHES FOUND"))
        return "\n".join(lines)


def reconcile(published: pl.DataFrame, provider_metrics: pl.DataFrame) -> Reconciliation:
    """Compare published rows with our provider-view metrics for the same period."""
    keys = ["org_code", "treatment_function_code"]
    ours = provider_metrics.filter(pl.col("waiting_list_total") > 0).select(
        *keys, *[c for c in COUNTS if c != "within_18_weeks"], *PERCENTILES,
        (pl.col("waiting_list_total") - pl.col("waiting_over_18_weeks")).alias("within_18_weeks"),
    )
    joined = published.join(ours, on=keys, how="inner", suffix="_ours")
    mismatches = {
        c: joined.filter(pl.col(c) != pl.col(f"{c}_ours")).select(*keys, c, f"{c}_ours")
        for c in COUNTS
    }
    for c in PERCENTILES:
        mismatches[c] = joined.filter(
            pl.col(c).is_not_null()
            & ((pl.col(c) - pl.col(f"{c}_ours")).abs() > PERCENTILE_TOLERANCE)
        ).select(*keys, c, f"{c}_ours")
    return Reconciliation(
        rows_published=published.height,
        rows_compared=joined.height,
        missing_from_ours=published.join(ours, on=keys, how="anti").select(keys),
        missing_from_published=ours.join(published, on=keys, how="anti").select(keys),
        mismatches=mismatches,
    )
