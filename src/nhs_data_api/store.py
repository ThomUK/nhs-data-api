"""Reading and writing the processed layer (ADR 0006)."""

from __future__ import annotations

from pathlib import Path

import polars as pl

from .metrics import compute_all_views, submission_changes


class NoDataError(LookupError):
    pass


def latest_rtt_lazy(processed_dir: Path) -> pl.LazyFrame:
    """Latest vintage of each period (the 'latest' view), unevaluated."""
    root = processed_dir / "rtt"
    if not any(root.glob("vintage=*/*.parquet")):
        raise NoDataError("no RTT data has been ingested yet")
    return (
        pl.scan_parquet(root / "vintage=*" / "*.parquet", hive_partitioning=True)
        .filter(pl.col("vintage") == pl.col("vintage").max().over("period"))
        .drop("vintage")
    )


def latest_rtt(processed_dir: Path) -> pl.DataFrame:
    return latest_rtt_lazy(processed_dir).collect()


def metrics_dir(processed_dir: Path) -> Path:
    return processed_dir / "rtt_metrics"


def build_rtt_metrics(processed_dir: Path) -> tuple[Path, Path]:
    """Recompute all measures for all views from the latest vintages. Cheap; run after ingest."""
    lf = latest_rtt_lazy(processed_dir)
    periods = sorted(lf.select(pl.col("period").unique()).collect()["period"].to_list())
    # Month-on-month measures only need the previous month, so compute each month from a
    # two-month window instead of holding every month in memory at once.
    frames = []
    for i, period in enumerate(periods):
        window = periods[max(0, i - 1): i + 1]
        if len(window) == 2 and (window[1].year * 12 + window[1].month) - (
                window[0].year * 12 + window[0].month) != 1:
            window = [period]  # previous calendar month not loaded
        long = lf.filter(pl.col("period").is_in(window)).collect()
        frames.append(compute_all_views(long).filter(pl.col("period") == period))
        del long
    out = metrics_dir(processed_dir)
    out.mkdir(parents=True, exist_ok=True)
    m, s = out / "metrics.parquet", out / "submissions.parquet"
    pl.concat(frames, how="vertical_relaxed").write_parquet(m, compression="zstd")
    seen = lf.select("period", "provider_org_code", "provider_org_name").unique().collect()
    submission_changes(seen).write_parquet(s, compression="zstd")
    return m, s


def rebuild_rtt(processed_dir: Path, raw_dir: Path) -> list[Path]:
    """Regenerate the processed RTT layer from every Full CSV in the raw archive."""
    import shutil

    from .ingest import rtt

    target = processed_dir / "rtt"
    if target.exists():
        shutil.rmtree(target)
    written = []
    for folder in sorted((raw_dir / "rtt").iterdir()):
        for f in sorted(folder.glob("*Full-CSV-data-file*.zip")):
            df = rtt.tidy(rtt.read_full_csv(f))
            written.append(rtt.write_vintage(df, target, folder.name))
            del df
    return written


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
