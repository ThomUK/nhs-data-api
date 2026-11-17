import openpyxl
import pytest

from nhs_data_api.ingest import rtt
from nhs_data_api.ingest.rtt_published import (
    PublishedFormatError,
    read_provider_workbook,
    reconcile,
)
from nhs_data_api.metrics import compute_view

from .conftest import make_row, to_csv

HEADER = ["Region Code", "Provider Code", "Provider Name", "Treatment Function Code",
          "Treatment Function", ">0-1", "Total number of incomplete pathways",
          "Total within 18 weeks", "% within 18 weeks",
          "Average (median) waiting time (in weeks)", "92nd percentile waiting time (in weeks)",
          "Total 52 plus weeks", "Total 78 plus weeks", "Total 65 plus weeks"]


def _workbook(path, provider_rows, is_rows=()):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, rows in (("Provider", provider_rows), ("IS Provider", is_rows)):
        ws = wb.create_sheet(name)
        ws.append([None, "Title:", "Referral to Treatment (RTT) Waiting Times"])
        ws.append([])
        ws.append(HEADER)
        for r in rows:
            ws.append(r)
    wb.save(path)
    return path


@pytest.fixture
def ours():
    rows = [make_row("RJ1", "Part_2", "C_999", {5: 60, 20: 30, 60: 10}),
            make_row("NT4", "Part_2", "C_999", {1: 3})]
    return compute_view(rtt.tidy(rtt.read_full_csv(to_csv(rows))), "provider")


def test_reconcile_all_match(tmp_path, ours):
    path = _workbook(tmp_path / "p.xlsx",
                     [["Y56", "RJ1", "GSTT", "C_999", "Total", 0, 100, 60, 0.6, 5.83333,
                       60.2, 10, 0, 0],
                      ["Y56", "RJ1", "GSTT", "C_100", "Gen Surg", 0, 0, 0, 0, "-", "-", 0, 0, 0]],
                     [["Y56", "NT4", "IS", "C_999", "Total", 3, 3, 3, 1.0, 1.5, 1.92, 0, 0, 0]])
    result = reconcile(read_provider_workbook(path), ours)
    assert result.rows_published == 2  # zero-list row dropped
    assert result.ok, result.summary()


def test_reconcile_reports_mismatches(tmp_path, ours):
    path = _workbook(tmp_path / "p.xlsx",
                     [["Y56", "RJ1", "GSTT", "C_999", "Total", 0, 101, 60, 0.6, 7.0, 26.2,
                       10, 0, 0],
                      ["Y56", "RXX", "Other", "C_999", "Total", 0, 5, 5, 1, 1, 1, 0, 0, 0]])
    result = reconcile(read_provider_workbook(path), ours)
    assert not result.ok
    assert result.mismatches["waiting_list_total"].height == 1
    assert result.mismatches["median_wait_weeks"].height == 1
    assert result.missing_from_ours["org_code"].to_list() == ["RXX"]
    assert result.missing_from_published["org_code"].to_list() == ["NT4"]


def test_rejects_unexpected_layout(tmp_path):
    wb = openpyxl.Workbook()
    wb.active.title = "Provider"
    wb.save(tmp_path / "bad.xlsx")
    with pytest.raises(PublishedFormatError):
        read_provider_workbook(tmp_path / "bad.xlsx")
