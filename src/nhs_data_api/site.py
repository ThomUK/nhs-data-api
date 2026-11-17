"""Export JSON for the static admin site (site/), served from GitHub Pages.

The data lake is not in git, so the site reads small JSON extracts committed under
site/data/. Everything exported is derived from openly licensed data.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import polars as pl

from . import __version__
from .catalogue import load_catalogue
from .metrics import VIEWS
from .paths import PROCESSED_DIR, RAW_DIR, REPO_ROOT
from .schedule import add_months, publications, unscheduled
from .store import NoDataError, read_rtt_metrics, read_submissions

SITE_DATA = REPO_ROOT / "site" / "data"
ID_COLS = {"view", "period", "org_code", "org_name", "treatment_function_code"}


def _write(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, separators=(",", ":"), default=str))
    return path


def calendar_payload(today: date, raw_dir: Path = RAW_DIR) -> dict:
    start, end = add_months(today, -3), add_months(today, 13)
    return {"today": today.isoformat(), "publications": publications(start, end, raw_dir),
            "unscheduled": unscheduled()}


def timeseries_payloads(metrics: pl.DataFrame) -> dict[str, dict]:
    """One payload per view, columnar: org -> treatment function -> measure -> values.

    Non-national views carry the all-specialty total (C_999) only, to keep files small;
    the national view carries every treatment function.
    """
    measures = [c for c in metrics.columns if c not in ID_COLS]
    periods = sorted(metrics["period"].unique().to_list())
    index = {p: i for i, p in enumerate(periods)}
    out = {}
    for view in VIEWS:
        df = metrics.filter(pl.col("view") == view)
        if view != "national":
            df = df.filter(pl.col("treatment_function_code") == "C_999")
        orgs: dict[str, dict] = {}
        for (code, tf), grp in df.group_by(["org_code", "treatment_function_code"]):
            org = orgs.setdefault(code, {"code": code, "name": None, "series": {}})
            org["name"] = grp.sort("period")["org_name"][-1]
            values = {m: [None] * len(periods) for m in measures}
            for row in grp.iter_rows(named=True):
                i = index[row["period"]]
                for m in measures:
                    values[m][i] = row[m]
            org["series"][tf] = values
        out[view] = {"view": view, "periods": [p.isoformat() for p in periods],
                     "orgs": sorted(orgs.values(), key=lambda o: o["code"])}
    return out


def measures_payload() -> dict:
    ds = load_catalogue()["rtt"]
    tf = next(d for d in ds.dimensions if d.id == "treatment_function_code")
    return {
        "measures": [m.model_dump(mode="json", exclude_none=True) for m in ds.measures
                     if m.computed],
        "views": [v.model_dump(mode="json") for v in ds.views],
        "caveats": [c.model_dump(mode="json", exclude_none=True) for c in ds.caveats],
        "treatment_functions": tf.codes or {},
    }


def lineage_payload(processed_dir: Path, raw_dir: Path) -> dict:
    """Lineage links relevant to the loaded data, proposed links, and recode candidates."""
    import yaml

    from . import ods
    from .paths import CATALOGUE_DIR
    from .store import latest_rtt_lazy

    snap = ods.latest_snapshot(raw_dir)
    if snap is None:
        return {"snapshot": None, "links": [], "proposed": [], "candidates": []}
    orgs, _, _ = ods.load_snapshot(snap)
    try:
        seen = (latest_rtt_lazy(processed_dir).select("period", "provider_org_code")
                .unique().collect())
    except NoDataError:
        seen = pl.DataFrame({"period": [], "provider_org_code": []},
                            schema={"period": pl.Date, "provider_org_code": pl.Utf8})
    in_data = set(seen["provider_org_code"])
    links = ods.lineage_links(orgs, ods.curated_links())
    name = lambda c: orgs[c].name if c in orgs else None  # noqa: E731
    out_links = [{"from": lk.from_code, "from_name": name(lk.from_code), "to": lk.to_code,
                  "to_name": name(lk.to_code), "effective": lk.effective, "source": lk.source,
                  "evidence": lk.evidence.strip()}
                 for lk in links if lk.from_code in in_data or lk.to_code in in_data]
    proposed = [e for e in yaml.safe_load(
        (CATALOGUE_DIR / "organisation_lineage.yaml").read_text()).get("links", [])
        if e.get("status") != "confirmed"]
    for e in proposed:
        e["from_name"], e["to_name"] = name(e["from"]), name(e["to"])
        e["evidence"] = e["evidence"].strip()
    candidates = ods.recode_candidates(seen, orgs, ods.lineage_map(links))
    return {"snapshot": snap.name, "links": out_links, "proposed": proposed,
            "candidates": candidates}


def validation_payload(processed_dir: Path, raw_dir: Path = RAW_DIR) -> dict:
    runs = [json.loads(p.read_text())
            for p in sorted((processed_dir / "validation").glob("*/*.json"))]
    try:
        subs = read_submissions(processed_dir).to_dicts()
    except NoDataError:
        subs = []
    return {"runs": runs, "submissions": subs, "lineage": lineage_payload(processed_dir, raw_dir)}


def build_site(out_dir: Path | None = None, processed_dir: Path = PROCESSED_DIR,
               raw_dir: Path = RAW_DIR, today: date | None = None) -> list[Path]:
    out_dir = out_dir or SITE_DATA
    today = today or date.today()
    written = [
        _write(out_dir / "calendar.json", calendar_payload(today, raw_dir)),
        _write(out_dir / "measures.json", measures_payload()),
        _write(out_dir / "validation.json", validation_payload(processed_dir, raw_dir)),
    ]
    try:
        metrics = read_rtt_metrics(processed_dir).collect()
    except NoDataError:
        metrics = None
    if metrics is not None:
        for view, payload in timeseries_payloads(metrics).items():
            written.append(_write(out_dir / "timeseries" / f"{view}.json", payload))
    written.append(_write(out_dir / "build.json", {
        "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "version": __version__,
        "periods": [] if metrics is None
        else sorted({p.isoformat() for p in metrics["period"].unique()}),
    }))
    return written
