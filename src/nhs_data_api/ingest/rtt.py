"""Parse the NHS England RTT "Full CSV data file" into a tidy long table.

The column layout is detected from headers rather than fixed positions, because the
publication has changed shape over time (ADR 0007, known_format_changes).
"""

from __future__ import annotations

import io
import re
import zipfile
from datetime import date
from pathlib import Path

import polars as pl

ID_COLUMNS = {
    "Period": "period_raw",
    "Provider Parent Org Code": "provider_parent_org_code",
    "Provider Parent Name": "provider_parent_name",
    "Provider Org Code": "provider_org_code",
    "Provider Org Name": "provider_org_name",
    "Commissioner Parent Org Code": "commissioner_parent_org_code",
    "Commissioner Parent Name": "commissioner_parent_name",
    "Commissioner Org Code": "commissioner_org_code",
    "Commissioner Org Name": "commissioner_org_name",
    "RTT Part Type": "rtt_part_type",
    "RTT Part Description": "rtt_part_description",
    "Treatment Function Code": "treatment_function_code",
    "Treatment Function Name": "treatment_function_name",
}
_BAND = re.compile(r"^Gt (\d+) To (\d+) Weeks SUM 1$", re.IGNORECASE)
_OPEN_BAND = re.compile(r"^Gt (\d+) Weeks SUM 1$", re.IGNORECASE)
UNKNOWN_START = "Patients with unknown clock start date"
TOTAL = "Total"
_MONTHS = {
    m: i
    for i, m in enumerate(
        ["january", "february", "march", "april", "may", "june", "july",
         "august", "september", "october", "november", "december"],
        start=1,
    )
}

OUTPUT_SCHEMA = {
    "period": pl.Date,
    **{v: pl.Utf8 for k, v in ID_COLUMNS.items() if k != "Period"},
    "weeks_band": pl.Utf8,
    "weeks_lower": pl.Int16,
    "weeks_upper": pl.Int16,
    "patients": pl.Int64,
}


class RttFormatError(ValueError):
    pass


def parse_period(raw: str) -> date:
    """'RTT-September-2025' -> date(2025, 9, 1)."""
    m = re.fullmatch(r"RTT-([A-Za-z]+)-(\d{4})", raw.strip())
    if not m or m.group(1).lower() not in _MONTHS:
        raise RttFormatError(f"unrecognised period {raw!r}")
    return date(int(m.group(2)), _MONTHS[m.group(1).lower()], 1)


def classify_band_columns(columns: list[str]) -> dict[str, tuple[int, int | None]]:
    bands: dict[str, tuple[int, int | None]] = {}
    for col in columns:
        if m := _BAND.match(col.strip()):
            bands[col] = (int(m.group(1)), int(m.group(2)))
        elif m := _OPEN_BAND.match(col.strip()):
            bands[col] = (int(m.group(1)), None)
    return bands


def read_full_csv(source: Path | bytes) -> pl.DataFrame:
    """Read a Full CSV data file (.csv or .zip containing one csv) as all-string columns."""
    data = source if isinstance(source, bytes) else Path(source).read_bytes()
    if data[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            csvs = [n for n in zf.namelist() if n.lower().endswith(".csv")]
            if len(csvs) != 1:
                raise RttFormatError(f"expected one csv in zip, found {csvs}")
            data = zf.read(csvs[0])
    return pl.read_csv(data, infer_schema_length=0, encoding="utf8-lossy")


def tidy(wide: pl.DataFrame) -> pl.DataFrame:
    """Wide publication layout -> long table at the catalogue grain, with validation."""
    wide = wide.rename({c: c.strip() for c in wide.columns})
    missing = [c for c in ID_COLUMNS if c not in wide.columns]
    if missing:
        raise RttFormatError(f"missing identifier columns: {missing}")
    bands = classify_band_columns(wide.columns)
    if not bands:
        raise RttFormatError("no weekly band columns found")

    value_cols = list(bands) + ([UNKNOWN_START] if UNKNOWN_START in wide.columns else [])
    numeric = wide.with_columns(
        pl.col(c).str.strip_chars().cast(pl.Int64, strict=True).fill_null(0)
        for c in value_cols + ([TOTAL] if TOTAL in wide.columns else [])
    )

    if TOTAL in numeric.columns:
        bad = numeric.filter(pl.sum_horizontal(list(bands)) != pl.col(TOTAL))
        if bad.height:
            raise RttFormatError(f"{bad.height} rows where weekly bands do not sum to Total")

    periods = numeric["Period"].unique().to_list()
    period_map = {p: parse_period(p) for p in periods}

    long = (
        numeric.select(list(ID_COLUMNS) + value_cols)
        .rename(ID_COLUMNS)
        .unpivot(index=list(ID_COLUMNS.values()), on=value_cols,
                 variable_name="weeks_band", value_name="patients")
    )
    lower = {c: lo for c, (lo, _) in bands.items()}
    upper = {c: hi for c, (_, hi) in bands.items()}
    long = long.with_columns(
        pl.col("period_raw").replace_strict(period_map, return_dtype=pl.Date).alias("period"),
        pl.col("weeks_band").replace_strict(lower, default=None, return_dtype=pl.Int16)
        .alias("weeks_lower"),
        pl.col("weeks_band").replace_strict(upper, default=None, return_dtype=pl.Int16)
        .alias("weeks_upper"),
        pl.col("weeks_band").replace_strict(
            {**{c: _band_label(*b) for c, b in bands.items()}, UNKNOWN_START: "unknown_clock_start"}
        ),
    )
    return long.select(list(OUTPUT_SCHEMA)).cast(OUTPUT_SCHEMA).filter(pl.col("patients") != 0)


def _band_label(lower: int, upper: int | None) -> str:
    return f"gt{lower:03d}" if upper is None else f"gt{lower:03d}_le{upper:03d}"


def write_vintage(df: pl.DataFrame, out_dir: Path, vintage: str) -> Path:
    target = out_dir / f"vintage={vintage}" / "part-0.parquet"
    target.parent.mkdir(parents=True, exist_ok=True)
    df.sort(["period", "provider_org_code", "rtt_part_type", "treatment_function_code",
             "commissioner_org_code", "weeks_lower"]).write_parquet(target, compression="zstd")
    return target
