"""Release steps (ADR 0010): reconcile every archived provider workbook, and bundle the data
the API serves into a small directory that is copied into the container image."""

from __future__ import annotations

import json
import os
import re
import shutil
from datetime import UTC, date, datetime
from pathlib import Path

import polars as pl

from . import __version__
from .schedule import MONTHS

WORKBOOK = re.compile(r"Incomplete-Provider-([A-Za-z]{3})(\d{2})", re.IGNORECASE)
BUNDLE_FILES = ["rtt_metrics/metrics.parquet", "rtt_metrics/submissions.parquet",
                "ods/organisations.parquet"]


def archived_workbooks(raw_dir: Path) -> list[tuple[date, Path]]:
    """(reporting month, path) for every Incomplete Provider workbook in the raw archive."""
    abbrev = {m[:3].lower(): i for i, m in enumerate(MONTHS, start=1)}
    found = []
    for path in sorted((raw_dir / "rtt").glob("*/*.xlsx")):
        m = WORKBOOK.search(path.name)
        if m and m.group(1).lower() in abbrev:
            found.append((date(2000 + int(m.group(2)), abbrev[m.group(1).lower()], 1), path))
    return found


def reconcile_archive(raw_dir: Path, processed_dir: Path) -> list[dict]:
    """Reconcile each archived workbook against the current metrics; record each result."""
    from .ingest.rtt_published import read_provider_workbook, reconcile
    from .store import read_rtt_metrics

    results = []
    for period, path in archived_workbooks(raw_dir):
        ours = read_rtt_metrics(processed_dir).filter(
            (pl.col("view") == "provider") & (pl.col("period") == period)).collect()
        result = reconcile(read_provider_workbook(path), ours)
        record = result.to_json(period.isoformat(), path.name)
        out = processed_dir / "validation" / "rtt" / f"{period.isoformat()}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(record, indent=2))
        results.append(record)
    return results


def build_bundle(processed_dir: Path, out_dir: Path) -> Path:
    """Copy the files the API reads into out_dir, with a bundle.json describing them."""
    if out_dir.exists():
        shutil.rmtree(out_dir)
    for rel in BUNDLE_FILES:
        src = processed_dir / rel
        if not src.exists():
            raise FileNotFoundError(f"{src} missing: run rebuild-rtt (and fetch-ods) first")
        (out_dir / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, out_dir / rel)
    periods = pl.read_parquet(out_dir / "rtt_metrics/metrics.parquet", columns=["period"])["period"]
    info = {
        "data_version": f"{periods.max():%Y-%m}.{datetime.now(UTC):%Y%m%d%H%M}",
        "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "code_version": __version__,
        "git_sha": os.environ.get("GITHUB_SHA", ""),
        "rtt_periods": [str(periods.min()), str(periods.max())],
    }
    (out_dir / "bundle.json").write_text(json.dumps(info, indent=2))
    return out_dir
