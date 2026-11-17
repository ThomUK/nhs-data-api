"""Synthetic RTT Full CSV fixtures.

SYNTHETIC: column names follow the published Full CSV layout as understood on 2026-11-17.
They must be checked against a real file (see README "Next steps").
"""

from __future__ import annotations

import csv
import io

import pytest

from nhs_data_api.ingest.rtt import ID_COLUMNS

BAND_COLS = [f"Gt {i:02d} To {i + 1:02d} Weeks SUM 1" for i in range(104)] + ["Gt 104 Weeks SUM 1"]
HEADER = list(ID_COLUMNS) + BAND_COLS + ["Total", "Patients with unknown clock start date",
                                          "Total All"]


def make_row(provider: str, part: str, tf: str, bands: dict[int, int], unknown: int = 0,
             period: str = "RTT-September-2025") -> list[str]:
    counts = [bands.get(i, 0) for i in range(105)]
    total = sum(counts)
    ids = [period, "Y56", "LONDON", provider, f"{provider} TRUST", "QWE", "SE LONDON ICB",
           "72Q", "SE LONDON SUB", part, part.replace("_", " "), tf,
           "Total" if tf == "C_999" else tf]
    return ids + [str(c) for c in counts] + [str(total), str(unknown), str(total + unknown)]


def to_csv(rows: list[list[str]]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(HEADER)
    w.writerows(rows)
    return buf.getvalue().encode()


@pytest.fixture
def rtt_csv() -> bytes:
    return to_csv([
        # 100 waiting: 60 in weeks 0-10, 30 in 18-30, 10 over 52 -> 60% within 18
        make_row("RJ1", "Part_2", "C_999", {5: 60, 20: 30, 60: 10}, unknown=3),
        make_row("RJ1", "Part_1A", "C_999", {2: 40}),
        make_row("RJZ", "Part_2", "C_999", {1: 50, 104: 2}),
    ])
