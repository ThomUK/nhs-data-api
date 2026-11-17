from datetime import date

import polars as pl
import pytest

from nhs_data_api.ingest import rtt
from nhs_data_api.metrics import rtt_summary

from .conftest import make_row, to_csv


def test_parse_period():
    assert rtt.parse_period("RTT-September-2025") == date(2025, 9, 1)
    with pytest.raises(rtt.RttFormatError):
        rtt.parse_period("Sep-25")


def test_band_columns_detected():
    bands = rtt.classify_band_columns(["Gt 00 To 01 Weeks SUM 1", "Gt 104 Weeks SUM 1", "Total"])
    assert bands == {"Gt 00 To 01 Weeks SUM 1": (0, 1), "Gt 104 Weeks SUM 1": (104, None)}


def test_tidy_long_shape(rtt_csv):
    long = rtt.tidy(rtt.read_full_csv(rtt_csv))
    assert long.schema == pl.Schema(rtt.OUTPUT_SCHEMA)
    rj1 = long.filter(
        (pl.col("provider_org_code") == "RJ1") & (pl.col("rtt_part_type") == "Part_2")
    )
    assert rj1["patients"].sum() == 103
    unknown = rj1.filter(pl.col("weeks_band") == "unknown_clock_start")
    assert unknown["patients"].item() == 3 and unknown["weeks_lower"].item() is None
    assert long.filter(pl.col("weeks_band") == "gt104")["weeks_upper"].item() is None


def test_tidy_rejects_inconsistent_totals(rtt_csv):
    bad = rtt_csv.replace(b",100,3,103", b",999,3,1002")
    with pytest.raises(rtt.RttFormatError, match="do not sum"):
        rtt.tidy(rtt.read_full_csv(bad))


def test_tidy_rejects_missing_columns():
    with pytest.raises(rtt.RttFormatError, match="missing identifier"):
        rtt.tidy(pl.DataFrame({"Period": ["RTT-May-2025"]}))


def test_summary_measures(rtt_csv):
    long = rtt.tidy(rtt.read_full_csv(rtt_csv))
    s = rtt_summary(long, by=["provider_org_code"]).to_dicts()
    rj1 = next(r for r in s if r["provider_org_code"] == "RJ1")
    assert rj1["incomplete_pathways_total"] == 100  # unknown clock start excluded
    assert rj1["pct_within_18_weeks"] == 60.0
    assert rj1["waiting_over_52_weeks"] == 10
    assert rj1["median_wait_weeks"] == pytest.approx(5.8)  # 50/60 through band (5,6]


def test_write_vintage_roundtrip(tmp_path, rtt_csv):
    long = rtt.tidy(rtt.read_full_csv(rtt_csv))
    out = rtt.write_vintage(long, tmp_path / "rtt", "2025-11-13")
    assert pl.read_parquet(out).height == long.height


def test_zip_input(tmp_path):
    import zipfile
    z = tmp_path / "f.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("data.csv", to_csv([make_row("RJ1", "Part_2", "C_999", {0: 1})]))
    assert rtt.read_full_csv(z).height == 1
