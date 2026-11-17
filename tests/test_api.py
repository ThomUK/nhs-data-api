import pytest
from fastapi.testclient import TestClient

from nhs_data_api.api import app as app_module
from nhs_data_api.ingest import rtt
from nhs_data_api.store import build_rtt_metrics

from .conftest import make_row, to_csv


@pytest.fixture
def client(tmp_path, monkeypatch):
    aug = [make_row("RJ1", "Part_2", "C_999", {5: 60, 20: 40}, period="RTT-August-2025")]
    sep = [make_row("RJ1", "Part_2", "C_999", {5: 70, 20: 40}),
           make_row("RJZ", "Part_2", "C_999", {1: 50})]
    rtt.write_vintage(rtt.tidy(rtt.read_full_csv(to_csv(aug))), tmp_path / "rtt", "2025-10-09")
    first = rtt.tidy(rtt.read_full_csv(to_csv(sep)))
    rtt.write_vintage(first, tmp_path / "rtt", "2025-11-13")
    # A later publication revises September: RJ1 doubles
    revised = first.with_columns(
        rtt.pl.when(rtt.pl.col("provider_org_code") == "RJ1")
        .then(rtt.pl.col("patients") * 2).otherwise(rtt.pl.col("patients")))
    rtt.write_vintage(revised, tmp_path / "rtt", "2025-12-11")
    build_rtt_metrics(tmp_path)
    monkeypatch.setattr(app_module, "PROCESSED_DIR", tmp_path)
    return TestClient(app_module.app)


def test_catalogue_endpoints():
    c = TestClient(app_module.app)
    assert c.get("/health").json()["status"] == "ok"
    ids = {d["id"] for d in c.get("/v1/datasets").json()["data"]}
    assert "rtt" in ids
    assert c.get("/v1/datasets/nope").status_code == 404


def test_metrics_latest_vintage_and_meta(client):
    body = client.get("/v1/rtt/metrics", params={"view": "provider", "org": "rj1"}).json()
    row = body["data"][0]
    assert row["period"] == "2025-09-01"
    assert row["waiting_list_total"] == 220  # revised vintage wins
    assert row["waiting_list_change_mom"] == 120
    assert "unreported_removals_like_for_like" not in row  # experimental: opt-in
    assert "unreported_removals" in row
    meta = body["meta"]
    assert meta["licence"].startswith("Open Government Licence")
    assert meta["measures"]["pct_within_18_weeks"]["standard"].startswith("NHS Constitution")


def test_metrics_selection_views_and_ranges(client):
    r = client.get("/v1/rtt/metrics", params={"view": "national", "measures": "waiting_list_total",
                                              "period_from": "2025-08-01"}).json()
    assert [d["waiting_list_total"] for d in r["data"]] == [100, 270]
    assert set(r["data"][0]) == {"period", "org_code", "org_name", "treatment_function_code",
                                 "waiting_list_total"}
    exp = client.get("/v1/rtt/metrics", params={"view": "national",
                                                "include_experimental": True}).json()
    assert "unreported_removals_like_for_like" in exp["data"][0]
    assert exp["meta"]["measures"]["unreported_removals_like_for_like"]["status"] == "experimental"
    assert client.get("/v1/rtt/metrics", params={"measures": "nope"}).status_code == 422
    assert client.get("/v1/rtt/metrics", params={"view": "bogus"}).status_code == 422


def test_missing_period_for_known_org_explains_why(client):
    r = client.get("/v1/rtt/metrics", params={"org": "RJZ", "period": "2025-08-01"})
    assert r.status_code == 404 and "submissions" in r.json()["detail"]


def test_submissions(client):
    data = client.get("/v1/rtt/submissions").json()["data"]
    assert data[-1]["providers_submitting"] == 2


def test_organisation_endpoints(tmp_path, monkeypatch):
    import polars as pl
    (tmp_path / "ods").mkdir()
    pl.DataFrame({"org_code": ["RA7", "RVJ", "NTP15"],
                  "name": ["BRISTOL NHS FOUNDATION TRUST", "NORTH BRISTOL NHS TRUST",
                           "PRACTICE PLUS GROUP HOSPITAL - ILFORD"],
                  "sector": ["nhs_trust", "nhs_trust", "independent_sector"],
                  "successors": [[], ["RA7"], []], "predecessors": [["RVJ"], [], []]}
                 ).write_parquet(tmp_path / "ods" / "organisations.parquet")
    monkeypatch.setattr(app_module, "PROCESSED_DIR", tmp_path)
    c = TestClient(app_module.app)
    found = c.get("/v1/organisations", params={"q": "bristol"}).json()
    assert [o["org_code"] for o in found["data"]] == ["RA7", "RVJ"]
    assert found["meta"]["licence"].startswith("Open Government Licence")
    sector = c.get("/v1/organisations", params={"sector": "independent_sector"}).json()
    assert sector["meta"]["rows"] == 1
    one = c.get("/v1/organisations/ntp15").json()["data"]
    assert one["curated_lineage"][0]["to"] == "F0U7A"
    assert c.get("/v1/organisations/XXX").status_code == 404
