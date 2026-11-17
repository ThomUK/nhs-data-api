import json
from datetime import date

import polars as pl

from nhs_data_api.ingest import rtt
from nhs_data_api.schedule import nth_weekday, publications
from nhs_data_api.site import build_site
from nhs_data_api.store import build_rtt_metrics

from .conftest import make_row, to_csv


def test_second_thursday():
    assert nth_weekday(2026, 11, 3, 2) == date(2026, 11, 12)  # confirmed by the SPN
    assert nth_weekday(2026, 10, 3, 2) == date(2026, 10, 8)
    assert nth_weekday(2027, 1, 3, 2) == date(2027, 1, 14)


def test_publications_report_received_files(tmp_path):
    folder = tmp_path / "rtt" / "2026-11-12"
    folder.mkdir(parents=True)
    (folder / "b892c40a-Full-CSV-data-file-Sep26-ZIP-3M-ojyW5x.zip").write_bytes(b"x")
    (folder / "b892c40a-Full-CSV-data-file-Sep26-ZIP-3M-ojyW5x.zip.meta.json").write_text("{}")
    (folder / "random-notes.txt").write_text("x")
    pubs = publications(date(2026, 11, 1), date(2026, 11, 30), raw_dir=tmp_path)
    rtt_pub = next(p for p in pubs if p["dataset"] == "rtt")
    assert rtt_pub["publication_date"] == "2026-11-12"
    assert rtt_pub["data_period"] == "2026-09-01"
    assert rtt_pub["date_status"] == "confirmed"
    files = {f["id"]: f["received"] for f in rtt_pub["files"]}
    assert files["full_csv"] == ["b892c40a-Full-CSV-data-file-Sep26-ZIP-3M-ojyW5x.zip"]
    assert files["incomplete_provider"] == []
    assert rtt_pub["unmatched_files"] == ["random-notes.txt"]
    # Not-yet-onboarded datasets still appear, with no files
    assert any(p["dataset"] == "diagnostics" and not p["files"] for p in pubs)


def test_build_site(tmp_path):
    processed, out = tmp_path / "processed", tmp_path / "site"
    for period, vintage, n in [("RTT-August-2025", "2025-10-09", 10), ("RTT-September-2025",
                                                                       "2025-11-13", 12)]:
        rows = [make_row("RJ1", "Part_2", "C_999", {3: n}, period=period),
                make_row("RJ1", "Part_2", "C_100", {3: n}, period=period)]
        rtt.write_vintage(rtt.tidy(rtt.read_full_csv(to_csv(rows))), processed / "rtt", vintage)
    build_rtt_metrics(processed)
    build_site(out, processed_dir=processed, raw_dir=tmp_path / "raw", today=date(2025, 11, 17))

    names = {p.relative_to(out).as_posix() for p in out.rglob("*.json")}
    assert {"calendar.json", "measures.json", "validation.json", "build.json",
            "timeseries/national.json", "timeseries/provider.json"} <= names
    prov = json.loads((out / "timeseries/provider.json").read_text())
    assert prov["periods"] == ["2025-08-01", "2025-09-01"]
    rj1 = prov["orgs"][0]
    assert rj1["code"] == "RJ1" and list(rj1["series"]) == ["C_999"]  # totals only
    assert rj1["series"]["C_999"]["waiting_list_total"] == [10, 12]
    national = json.loads((out / "timeseries/national.json").read_text())
    assert set(national["orgs"][0]["series"]) == {"C_999", "C_100"}
    measures = json.loads((out / "measures.json").read_text())
    assert pl.Series([m["id"] for m in measures["measures"]]).is_unique().all()
