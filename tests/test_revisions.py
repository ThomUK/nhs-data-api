from datetime import date

import polars as pl

from nhs_data_api.ingest import rtt
from nhs_data_api.revisions import build_revisions, compare, expected_first_release

from .conftest import make_row, to_csv


def _month(rows):
    return rtt.tidy(rtt.read_full_csv(to_csv(rows)))


def test_expected_first_release():
    assert expected_first_release(date(2026, 9, 1)) == date(2026, 11, 12)
    assert expected_first_release(date(2025, 4, 1)) == date(2025, 6, 12)


def test_compare_reports_rows_and_measures():
    old = _month([make_row("RJ1", "Part_2", "C_999", {3: 60, 30: 40}),
                  make_row("RX1", "Part_2", "C_999", {1: 10})])
    new = _month([make_row("RJ1", "Part_2", "C_999", {3: 60, 30: 45}),   # resubmitted
                  make_row("RX1", "Part_2", "C_999", {1: 10}),
                  make_row("RW5", "Part_2", "C_999", {2: 7})])           # late submitter
    summary, changes = compare(old, new)
    assert (summary["rows_changed"], summary["rows_added"], summary["rows_removed"]) == (1, 1, 0)
    assert summary["providers_changed"] == 2
    national = {c["measure"]: c for c in summary["national_changes"]}
    assert national["waiting_list_total"]["change"] == 12
    is_list = pl.col("measure") == "waiting_list_total"
    rj1 = changes.filter((pl.col("org_code") == "RJ1") & is_list)
    assert rj1.select("old", "new").row(0) == (100.0, 105.0)
    assert changes.filter(pl.col("org_code") == "RX1").is_empty()


def test_build_revisions(tmp_path):
    first = _month([make_row("RJ1", "Part_2", "C_999", {3: 10})])
    revised = _month([make_row("RJ1", "Part_2", "C_999", {3: 12})])
    rtt.write_vintage(first, tmp_path / "rtt", "2025-11-13")     # on time: original
    rtt.write_vintage(revised, tmp_path / "rtt", "2026-02-12")   # later revision
    only_rev = _month([make_row("RJ1", "Part_2", "C_999", {3: 9}, period="RTT-August-2025")])
    rtt.write_vintage(only_rev, tmp_path / "rtt", "2026-02-12")
    import json
    report = json.loads(build_revisions(tmp_path).read_text())
    by = {p["period"]: p for p in report["periods"]}
    sep, aug = by["2025-09-01"], by["2025-08-01"]
    assert sep["original_archived"] and len(sep["comparisons"]) == 1
    assert sep["comparisons"][0]["top_provider_changes"][0]["change"] == 2
    assert not aug["original_archived"] and aug["comparisons"] == []
