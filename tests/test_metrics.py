import polars as pl
import pytest

from nhs_data_api.ingest import rtt
from nhs_data_api.metrics import VIEWS, compute_all_views, compute_view, submission_changes

from .conftest import make_row, to_csv

AUG, SEP = "RTT-August-2025", "RTT-September-2025"


@pytest.fixture
def two_months() -> pl.DataFrame:
    rows = [
        # August: RJ1 has 100 waiting; RX1 has 50; nothing else
        make_row("RJ1", "Part_2", "C_999", {5: 60, 20: 30, 60: 10}, period=AUG),
        make_row("RX1", "Part_2", "C_999", {3: 50}, period=AUG),
        # September: RJ1 has 20 new, 15 treated, so 105 waiting would mean 0 unexplained;
        # it has 98, so 7 removed without a recorded clock stop.
        make_row("RJ1", "Part_2", "C_999", {5: 50, 20: 35, 60: 8, 70: 5}, period=SEP),
        make_row("RJ1", "Part_2A", "C_999", {20: 10}, period=SEP),
        make_row("RJ1", "Part_3", "C_999", None, unknown=20, period=SEP),
        make_row("RJ1", "Part_1A", "C_999", {10: 5}, period=SEP),
        make_row("RJ1", "Part_1B", "C_999", {2: 8, 30: 2}, unknown=1, period=SEP),
        # RX1 misses September; NEW appears; NHS England commissions some of RJ1's care
        make_row("NEW", "Part_2", "C_999", {1: 40}, period=SEP),
        make_row("RJ1", "Part_2", "C_999", {1: 4}, period=SEP, commissioner="14A",
                 commissioner_parent=""),
    ]
    return rtt.tidy(rtt.read_full_csv(to_csv(rows)))


def _row(df: pl.DataFrame, org: str, period: str = "2025-09-01") -> dict:
    return df.filter((pl.col("org_code") == org)
                     & (pl.col("period").cast(pl.Utf8) == period)).to_dicts()[0]


def test_snapshot_measures(two_months):
    p = _row(compute_view(two_months, "provider"), "RJ1")
    assert p["waiting_list_total"] == 102
    assert p["waiting_list_dta"] == 10 and p["pct_waiting_list_dta"] == pytest.approx(9.8)
    assert p["pct_within_18_weeks"] == pytest.approx(52.9)  # 54 of 102
    assert p["waiting_over_18_weeks"] == 48
    assert (p["waiting_over_52_weeks"], p["waiting_over_65_weeks"]) == (13, 5)
    assert p["approaching_52_weeks"] == 0
    assert p["clock_starts"] == 20
    assert (p["clock_stops_admitted"], p["clock_stops_non_admitted"]) == (5, 11)
    assert p["clock_stops_total"] == 16
    assert p["pct_completed_within_18_weeks_non_admitted"] == 80.0  # 8 of 10 known
    assert p["median_wait_weeks"] == pytest.approx(5.9)  # 51st of 102 in band (5,6] of 50+4


def test_percentiles_interpolate_and_floor_open_band():
    rows = [make_row("A", "Part_2", "C_999", {0: 10}), make_row("B", "Part_2", "C_999", {104: 3})]
    m = compute_view(rtt.tidy(rtt.read_full_csv(to_csv(rows))), "provider")
    a, b = _row(m, "A"), _row(m, "B")
    assert a["median_wait_weeks"] == 0.5 and a["p92_wait_weeks"] == pytest.approx(0.9)
    assert b["median_wait_weeks"] == 104.0  # open-ended band: lower bound


def test_month_on_month_simple_vs_like_for_like(two_months):
    nat = _row(compute_view(two_months, "national"), "ENG")
    # simple: RJ1 102 (incl. 4 NHSE-commissioned) + NEW 40 = 142 now, vs 150 in August
    assert nat["waiting_list_change_mom"] == 142 - 150
    # like-for-like: only RJ1 submitted both months: 102 vs 100
    assert nat["waiting_list_change_mom_like_for_like"] == 2
    assert nat["waiting_over_52_weeks_change_mom_like_for_like"] == 13 - 10
    # 100 + 20 starts - 16 stops - 102 = 2
    assert nat["unexplained_removals"] == 2


def test_month_on_month_null_without_history(two_months):
    prov = compute_view(two_months, "provider")
    assert _row(prov, "RJ1", "2025-08-01")["waiting_list_change_mom"] is None
    new = _row(prov, "NEW")
    assert new["waiting_list_change_mom"] is None
    assert new["waiting_list_change_mom_like_for_like"] is None
    assert new["unexplained_removals"] is None


def test_population_view_groups_nhse_direct_commissioning(two_months):
    pop = compute_view(two_months, "population_icb")
    assert _row(pop, "NHSE")["waiting_list_total"] == 4
    assert _row(pop, "QKK")["waiting_list_total"] == 138


def test_all_views_reconcile_to_national(two_months):
    m = compute_all_views(two_months).filter(pl.col("period").cast(pl.Utf8) == "2025-09-01")
    additive = ["waiting_list_total", "clock_starts", "clock_stops_total",
                "waiting_list_change_mom_like_for_like", "unexplained_removals"]
    national = m.filter(pl.col("view") == "national").select(additive).row(0)
    for view in VIEWS:
        sums = m.filter(pl.col("view") == view).select(pl.col(additive).sum()).row(0)
        assert sums == national, view


def test_submission_changes(two_months):
    s = submission_changes(two_months).to_dicts()
    assert s[0]["new_non_submitters"] is None  # no earlier month loaded
    assert s[1]["providers_submitting"] == 2
    assert [x["code"] for x in s[1]["new_non_submitters"]] == ["RX1"]


def test_metric_columns_match_catalogue(two_months):
    from nhs_data_api.catalogue import load_catalogue
    m = compute_view(two_months, "national")
    computed = {x.id for x in load_catalogue()["rtt"].measures if x.computed}
    assert computed == set(m.columns) - {"view", "period", "org_code", "org_name",
                                         "treatment_function_code"}
