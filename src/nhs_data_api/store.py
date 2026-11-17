"""Reading and writing the processed layer (ADR 0006)."""

from __future__ import annotations

from pathlib import Path

import polars as pl

from .metrics import compute_all_views, submission_changes


class NoDataError(LookupError):
    pass


def latest_rtt(processed_dir: Path) -> pl.DataFrame:
    """Latest vintage of each period (the 'latest' view)."""
    root = processed_dir / "rtt"
    if not any(root.glob("vintage=*/*.parquet")):
        raise NoDataError("no RTT data has been ingested yet")
    return (
        pl.scan_parquet(root / "vintage=*" / "*.parquet", hive_partitioning=True)
        .filter(pl.col("vintage") == pl.col("vintage").max().over("period"))
        .drop("vintage")
        .collect()
    )


def metrics_dir(processed_dir: Path) -> Path:
    return processed_dir / "rtt_metrics"


def build_rtt_metrics(processed_dir: Path) -> tuple[Path, Path]:
    """Recompute all measures for all views from the latest vintages. Cheap; run after ingest."""
    long = latest_rtt(processed_dir)
    out = metrics_dir(processed_dir)
    out.mkdir(parents=True, exist_ok=True)
    m, s = out / "metrics.parquet", out / "submissions.parquet"
    compute_all_views(long).write_parquet(m, compression="zstd")
    submission_changes(long).write_parquet(s, compression="zstd")
    return m, s


def read_rtt_metrics(processed_dir: Path) -> pl.LazyFrame:
    path = metrics_dir(processed_dir) / "metrics.parquet"
    if not path.exists():
        raise NoDataError("RTT metrics have not been built yet")
    return pl.scan_parquet(path)


def read_submissions(processed_dir: Path) -> pl.DataFrame:
    path = metrics_dir(processed_dir) / "submissions.parquet"
    if not path.exists():
        raise NoDataError("RTT metrics have not been built yet")
    return pl.read_parquet(path)
