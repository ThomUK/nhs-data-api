import json
from datetime import date

import openpyxl
import pytest
from fastapi.testclient import TestClient

from nhs_data_api.api import app as app_module
from nhs_data_api.ingest import rtt
from nhs_data_api.release import archived_workbooks, build_bundle, reconcile_archive
from nhs_data_api.store import build_rtt_metrics

from .conftest import make_row, to_csv
from .test_reconcile import HEADER


@pytest.fixture
def processed(tmp_path):
    rows = [make_row("RJ1", "Part_2", "C_999", {5: 60, 20: 30, 60: 10},
                     period="RTT-September-2026")]
    rtt.write_vintage(rtt.tidy(rtt.read_full_csv(to_csv(rows))), tmp_path / "p" / "rtt",
                      "2026-11-12")
    build_rtt_metrics(tmp_path / "p", raw_dir=tmp_path / "raw")
    (tmp_path / "p" / "ods").mkdir()
    import polars as pl
    pl.DataFrame({"org_code": ["RJ1"], "name": ["GSTT"], "sector": ["nhs_trust"]}).write_parquet(
        tmp_path / "p" / "ods" / "organisations.parquet")
    return tmp_path / "p"


def _workbook(path, total):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name in ("Provider", "IS Provider"):
        ws = wb.create_sheet(name)
        ws.append(HEADER)
        if name == "Provider":
            ws.append(["Y56", "RJ1", "GSTT", "C_999", "Total", 0, total, 60, 0.6, 5.83333,
                       60.2, 10, 0, 0])
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def test_reconcile_archive_gate(tmp_path, processed):
    raw = tmp_path / "raw"
    _workbook(raw / "rtt" / "2026-11-12" / "x-Incomplete-Provider-Sep26-XLSX-9M.xlsx", 100)
    assert archived_workbooks(raw)[0][0] == date(2026, 9, 1)
    assert [r["ok"] for r in reconcile_archive(raw, processed)] == [True]
    assert (processed / "validation" / "rtt" / "2026-09-01.json").exists()
    _workbook(raw / "rtt" / "2026-11-12" / "x-Incomplete-Provider-Sep26-XLSX-9M.xlsx", 999)
    assert [r["ok"] for r in reconcile_archive(raw, processed)] == [False]


def test_bundle_and_served_headers(tmp_path, processed, monkeypatch):
    out = build_bundle(processed, tmp_path / "bundle")
    info = json.loads((out / "bundle.json").read_text())
    assert info["data_version"].startswith("2026-09.")
    assert {p.relative_to(out).as_posix() for p in out.rglob("*.parquet")} == {
        "rtt_metrics/metrics.parquet", "rtt_metrics/submissions.parquet",
        "ods/organisations.parquet"}
    monkeypatch.setattr(app_module, "PROCESSED_DIR", out)
    c = TestClient(app_module.app)
    ok = c.get("/v1/rtt/metrics", params={"view": "provider", "org": "RJ1"})
    assert ok.status_code == 200
    assert ok.headers["cache-control"].startswith("public")
    assert ok.headers["x-data-version"] == info["data_version"]
    assert c.get("/health").json()["data_version"] == info["data_version"]
    missing = c.get("/v1/organisations/XXX")
    assert missing.status_code == 404 and missing.headers["cache-control"] == "no-store"
