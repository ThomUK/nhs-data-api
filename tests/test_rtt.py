import zipfile
from datetime import date

import polars as pl
import pytest

from nhs_data_api.ingest import rtt
from nhs_data_api.metrics import new_periods, rtt_summary

from .conftest import make_row, to_csv


def test_parse_period():
    assert rtt.parse_period("RTT-September-2025") == date(2025, 9, 1)
    with pytest.raises(rtt.RttFormatError):
        rtt.parse_period("Sep-25")


def test_band_columns_detected():
    bands = rtt.classify_band_columns(["Gt 00 To 01 Weeks SUM 1", "Gt 104 Weeks SUM 1", "Total"])
    assert bands == {"Gt 00 To 01 Weeks SUM 1": (0, 1), "Gt 104 Weeks SUM 1": (104, None)}


def test_real_sample_parses_and_conserves_totals(real_sample):
    wide = rtt.read_full_csv(real_sample)
    long = rtt.tidy(wide)
    assert long.schema == pl.Schema(rtt.OUTPUT_SCHEMA)
    assert set(long["rtt_part_type"]) == {"Part_1A", "Part_1B", "Part_2", "Part_2A", "Part_3"}
    # every patient in "Total All" ends up in exactly one long row
    expected = wide["Total All"].cast(pl.Int64).sum()
    assert long["patients"].sum() == expected
    assert long.filter(pl.col("weeks_band") == "unknown_clock_start").height > 0
    part3 = long.filter(pl.col("rtt_part_type") == "Part_3")
    assert set(part3["weeks_band"]) == {"unbanded"}


def test_synthetic_layouts(rtt_csv):
    long = rtt.tidy(rtt.read_full_csv(rtt_csv))
    rj1 = long.filter(pl.col("provider_org_code") == "RJ1")
    assert rj1.filter(pl.col("rtt_part_type") == "Part_2")["patients"].sum() == 100
    unknown = rj1.filter(pl.col("weeks_band") == "unknown_clock_start")
    assert unknown["patients"].item() == 3 and unknown["weeks_lower"].item() is None
    assert long.filter(pl.col("weeks_band") == "gt104")["weeks_upper"].item() is None
    assert new_periods(long, ["provider_org_code"]).row(0) == ("RJ1", 25)


def test_rejects_bands_not_matching_total():
    row = make_row("RJ1", "Part_1A", "C_999", {2: 40})
    row[-3] = "41"
    with pytest.raises(rtt.RttFormatError, match="do not sum to Total"):
        rtt.tidy(rtt.read_full_csv(to_csv([row])))


def test_rejects_total_all_mismatch():
    row = make_row("RJ1", "Part_2", "C_999", {2: 40})
    row[-1] = "39"
    with pytest.raises(rtt.RttFormatError, match="Total All"):
        rtt.tidy(rtt.read_full_csv(to_csv([row])))


def test_rejects_missing_columns():
    with pytest.raises(rtt.RttFormatError, match="missing identifier"):
        rtt.tidy(pl.DataFrame({"Period": ["RTT-May-2025"]}))


def test_summary_measures(rtt_csv):
    long = rtt.tidy(rtt.read_full_csv(rtt_csv))
    s = rtt_summary(long, by=["provider_org_code"]).to_dicts()
    rj1 = next(r for r in s if r["provider_org_code"] == "RJ1")
    assert rj1["incomplete_pathways_total"] == 100
    assert rj1["pct_within_18_weeks"] == 60.0
    assert rj1["waiting_over_52_weeks"] == 10
    assert rj1["median_wait_weeks"] == pytest.approx(5.8)  # 50/60 through band (5,6]


def test_write_vintage_roundtrip(tmp_path, rtt_csv):
    long = rtt.tidy(rtt.read_full_csv(rtt_csv))
    out = rtt.write_vintage(long, tmp_path / "rtt", "2025-11-13")
    assert pl.read_parquet(out).height == long.height


def test_zip_input(tmp_path):
    z = tmp_path / "f.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("data.csv", to_csv([make_row("RJ1", "Part_2", "C_999", {0: 1})]))
    assert rtt.read_full_csv(z).height == 1
