from fastapi.testclient import TestClient

from nhs_data_api.api import app as app_module
from nhs_data_api.ingest import rtt


def test_catalogue_endpoints():
    c = TestClient(app_module.app)
    assert c.get("/health").json()["status"] == "ok"
    ids = {d["id"] for d in c.get("/v1/datasets").json()["data"]}
    assert "rtt" in ids
    assert c.get("/v1/datasets/nope").status_code == 404


def test_waiting_list_uses_latest_vintage(tmp_path, monkeypatch, rtt_csv):
    long = rtt.tidy(rtt.read_full_csv(rtt_csv))
    rtt.write_vintage(long, tmp_path / "rtt", "2025-11-13")
    revised = long.with_columns(rtt.pl.col("patients") * 2)
    rtt.write_vintage(revised, tmp_path / "rtt", "2025-12-11")
    monkeypatch.setattr(app_module, "PROCESSED_DIR", tmp_path)

    body = TestClient(app_module.app).get("/v1/rtt/waiting-list", params={"provider": "rj1"}).json()
    assert body["data"][0]["incomplete_pathways_total"] == 200  # revised vintage wins
    assert body["meta"]["licence"].startswith("Open Government Licence")
    assert body["meta"]["caveats"]
