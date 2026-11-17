"""Parse the NHS England RTT "Full CSV data file" into a tidy long table.

The column layout is detected from headers rather than fixed positions, because the
publication has changed shape over time (ADR 0007, known_format_changes).

How the totals are populated differs by pathway type (checked against the Aug and Sep 2026
files):

    Part_1A/1B  bands; Total = sum(bands); unknown clock start sometimes;
                Total All = Total + unknown
    Part_2/2A   bands, Total and unknown blank, Total All = sum(bands)
    Part_3      no bands at all; Total All is the only figure

Blank means "not applicable", not zero, so blanks are kept as nulls until validated.
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
TOTAL_ALL = "Total All"
UNBANDED = "unbanded"
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
    wide = wide.rename({c: c.strip().lstrip("\ufeff") for c in wide.columns})
    missing = [c for c in [*ID_COLUMNS, TOTAL_ALL] if c not in wide.columns]
    if missing:
        raise RttFormatError(f"missing identifier columns: {missing}")
    bands = classify_band_columns(wide.columns)
    if not bands:
        raise RttFormatError("no weekly band columns found")
    band_cols = list(bands)
    optional = [c for c in (TOTAL, UNKNOWN_START) if c in wide.columns]

    num = wide.with_columns(
        pl.col(c).str.strip_chars().replace("", None).cast(pl.Int64, strict=True)
        for c in [*band_cols, *optional, TOTAL_ALL]
    )
    for c in (TOTAL, UNKNOWN_START):
        if c not in num.columns:
            num = num.with_columns(pl.lit(None, pl.Int64).alias(c))
    num = num.with_columns(
        pl.any_horizontal(pl.col(band_cols).is_not_null()).alias("_has_bands"),
        pl.sum_horizontal(band_cols).alias("_band_sum"),
    )
    _validate(num)

    period_map = {p: parse_period(p) for p in num["Period"].unique().to_list()}
    ids = list(ID_COLUMNS.values())
    banded = (
        num.filter("_has_bands")
        .select([*ID_COLUMNS, *band_cols, UNKNOWN_START])
        .rename(ID_COLUMNS)
        .unpivot(index=ids, variable_name="weeks_band", value_name="patients")
    )
    unbanded = (
        num.filter(~pl.col("_has_bands"))
        .select([*ID_COLUMNS, TOTAL_ALL])
        .rename({**ID_COLUMNS, TOTAL_ALL: "patients"})
        .with_columns(pl.lit(UNBANDED).alias("weeks_band"))
        .select([*ids, "weeks_band", "patients"])
    )
    long = pl.concat([banded, unbanded])

    lower = {c: lo for c, (lo, _) in bands.items()}
    upper = {c: hi for c, (_, hi) in bands.items()}
    labels = {**{c: _band_label(*b) for c, b in bands.items()},
              UNKNOWN_START: "unknown_clock_start", UNBANDED: UNBANDED}
    long = long.with_columns(
        pl.col("period_raw").replace_strict(period_map, return_dtype=pl.Date).alias("period"),
        pl.col("weeks_band").replace_strict(lower, default=None, return_dtype=pl.Int16)
        .alias("weeks_lower"),
        pl.col("weeks_band").replace_strict(upper, default=None, return_dtype=pl.Int16)
        .alias("weeks_upper"),
        pl.col("weeks_band").replace_strict(labels),
    )
    return (
        long.select(list(OUTPUT_SCHEMA)).cast(OUTPUT_SCHEMA)
        .filter(pl.col("patients").is_not_null() & (pl.col("patients") != 0))
    )


def _validate(num: pl.DataFrame) -> None:
    """Check internal consistency of every row; raise with a count and example on failure."""
    unknown = pl.col(UNKNOWN_START).fill_null(0)
    rules = {
        "weekly bands do not sum to Total": pl.col("_has_bands") & pl.col(TOTAL).is_not_null()
        & (pl.col("_band_sum") != pl.col(TOTAL)),
        "Total All is not Total + unknown clock start": pl.col("_has_bands")
        & (pl.col(TOTAL_ALL) != pl.coalesce(TOTAL, "_band_sum") + unknown),
        "row has no bands and no Total All": ~pl.col("_has_bands") & pl.col(TOTAL_ALL).is_null(),
        "negative count": pl.any_horizontal(
            [pl.col(c) < 0 for c in num.columns if c.endswith("SUM 1") or c == TOTAL_ALL]
        ),
    }
    for message, failing in rules.items():
        bad = num.filter(failing.fill_null(False))
        if bad.height:
            example = bad.select("Provider Org Code", "RTT Part Type",
                                 "Treatment Function Code").row(0)
            raise RttFormatError(f"{bad.height} rows: {message} (e.g. {example})")


def _band_label(lower: int, upper: int | None) -> str:
    return f"gt{lower:03d}" if upper is None else f"gt{lower:03d}_le{upper:03d}"


def infer_vintage(source: Path) -> tuple[date, date]:
    """Infer the publication date of a Full CSV zip from the timestamp of the file inside.

    NHS England publishes on the second Thursday of the month and builds the file a few days
    before, so the publication is the first second-Thursday on or after the file's date. This
    also places revised files at the release they were republished with, not their original
    release. Returns (inferred publication date, file timestamp date).
    """
    from ..schedule import add_months, nth_weekday

    with zipfile.ZipFile(source) as zf:
        stamp = date(*zf.infolist()[0].date_time[:3])
    for offset in (0, 1):
        month = add_months(stamp, offset)
        candidate = nth_weekday(month.year, month.month, 3, 2)
        if candidate >= stamp:
            return candidate, stamp
    raise AssertionError("unreachable")


def write_vintage(df: pl.DataFrame, out_dir: Path, vintage: str) -> Path:
    """Write one reporting month as published at `vintage`.

    One file per (vintage, period): a single publication can carry several months (for
    example revised files republished together), and they must not overwrite each other.
    """
    periods = df["period"].unique().to_list()
    if len(periods) != 1:
        raise RttFormatError(f"expected one period per file, found {periods}")
    target = out_dir / f"vintage={vintage}" / f"period-{periods[0]:%Y-%m}.parquet"
    target.parent.mkdir(parents=True, exist_ok=True)
    df.sort(["period", "provider_org_code", "rtt_part_type", "treatment_function_code",
             "commissioner_org_code", "weeks_lower"]).write_parquet(target, compression="zstd")
    return target
