"""RTT fixtures.

`rtt_sep26_sample.csv` is real data: every row for one provider (ACES Chelmsford, H3W7Q)
plus three completed-pathway rows with unknown clock starts, from NHS England's
September 2026 RTT Full CSV. Open Government Licence v3.0.

`make_row`/`to_csv` build small synthetic files in the same layout for targeted cases.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
REAL_SAMPLE = FIXTURES / "rtt_sep26_sample.csv"
HEADER = REAL_SAMPLE.read_text().splitlines()[0].split(",")
N_BANDS = 105


def make_row(provider: str, part: str, tf: str, bands: dict[int, int] | None,
             unknown: int | None = None, period: str = "RTT-September-2025") -> list[str]:
    """One row laid out as the real file does for that pathway type."""
    ids = [period, "Y56", "LONDON", provider, f"{provider} TRUST", "QWE", "SE LONDON ICB",
           "72Q", "SE LONDON SUB", part, part, tf, "Total" if tf == "C_999" else tf]
    if bands is None:  # Part_3: only Total All
        return ids + [""] * N_BANDS + ["", "", str(unknown or 0)]
    counts = [bands.get(i, 0) for i in range(N_BANDS)]
    s = sum(counts)
    if part in ("Part_2", "Part_2A"):  # Total and unknown blank
        return ids + [str(c) for c in counts] + ["", "", str(s)]
    u = "" if unknown is None else str(unknown)
    return ids + [str(c) for c in counts] + [str(s), u, str(s + (unknown or 0))]


def to_csv(rows: list[list[str]]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(HEADER)
    w.writerows(rows)
    return buf.getvalue().encode()


@pytest.fixture
def rtt_csv() -> bytes:
    return to_csv([
        # 100 waiting: 60 in week 5-6, 30 in 20-21, 10 in 60-61 -> 60% within 18
        make_row("RJ1", "Part_2", "C_999", {5: 60, 20: 30, 60: 10}),
        make_row("RJ1", "Part_1A", "C_999", {2: 40}, unknown=3),
        make_row("RJ1", "Part_3", "C_999", None, unknown=25),
        make_row("RJZ", "Part_2", "C_999", {1: 50, 104: 2}),
    ])


@pytest.fixture
def real_sample() -> Path:
    return REAL_SAMPLE
