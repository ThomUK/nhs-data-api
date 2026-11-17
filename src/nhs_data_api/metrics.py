"""RTT v1 measures (catalogue/datasets/rtt.yaml), computed from the tidy long table.

Measures are computed for several organisational *views* of the same rows:

- provider views group by where patients are treated (provider, provider's ICB);
- population views group by who commissions their care (sub-ICB location, ICB), so they
  answer "how long are this area's residents waiting, wherever they are treated?".

All counts are additive; ratios and percentiles are always recomputed from band counts
for the group, never averaged.
"""

from __future__ import annotations

import polars as pl

VIEWS: dict[str, dict[str, str | None]] = {
    "national": {"code": None, "name": None},
    "provider": {"code": "provider_org_code", "name": "provider_org_name"},
    "provider_icb": {"code": "provider_parent_org_code", "name": "provider_parent_name"},
    "population_icb": {"code": "commissioner_parent_org_code", "name": "commissioner_parent_name"},
    "population_sub_icb": {"code": "commissioner_org_code", "name": "commissioner_org_name"},
}
LONG_WAIT_THRESHOLDS = (52, 65, 78, 104)
EXPERIMENTAL = ("unreported_removals_like_for_like",)
# Patients whose care is commissioned outside England (Wales, Scotland, Northern Ireland,
# overseas). NHS England's published figures exclude them at every level, so we do too.
NON_ENGLISH_COMMISSIONER = "NONC"
NHSE_DIRECT = ("NHSE", "NHS ENGLAND DIRECT COMMISSIONING (NOT ATTRIBUTED TO AN ICB)")

_KEYS = ["period", "org_code", "org_name", "treatment_function_code"]
_BANDED = pl.col("weeks_lower").is_not_null()  # excludes unknown_clock_start and unbanded


def _part(name: str) -> pl.Expr:
    return pl.col("rtt_part_type") == name


def _with_view(long: pl.DataFrame, view: str) -> pl.DataFrame:
    if view not in VIEWS:
        raise ValueError(f"unknown view {view!r}; expected one of {list(VIEWS)}")
    code, name = VIEWS[view]["code"], VIEWS[view]["name"]
    if code is None:
        return long.with_columns(org_code=pl.lit("ENG"), org_name=pl.lit("ENGLAND"))
    if view == "population_icb":
        # Care commissioned directly by NHS England (specialised commissioning hubs etc.) has
        # no parent ICB. Group it explicitly rather than letting it fall out of the view.
        direct = pl.col(code).is_null()
        return long.with_columns(
            org_code=pl.when(direct).then(pl.lit(NHSE_DIRECT[0])).otherwise(pl.col(code)),
            org_name=pl.when(direct).then(pl.lit(NHSE_DIRECT[1])).otherwise(pl.col(name)),
        )
    return long.with_columns(org_code=pl.col(code),
                             org_name=pl.coalesce(pl.col(name), pl.col(code)))


def percentile(long: pl.DataFrame, keys: list[str], q: float) -> pl.DataFrame:
    """Percentile wait (weeks) by linear interpolation within weekly bands.

    Finds the band containing the q-th patient and interpolates within it. If that band is
    the open-ended top band, returns its lower bound (a floor, not an estimate).
    """
    bands = (
        long.filter(_BANDED & (pl.col("patients") > 0))
        .group_by([*keys, "weeks_lower", "weeks_upper"]).agg(pl.col("patients").sum())
        .sort([*keys, "weeks_lower"])
        .with_columns(
            cum=pl.col("patients").cum_sum().over(keys),
            target=q * pl.col("patients").sum().over(keys),
        )
        .with_columns(prev=pl.col("cum") - pl.col("patients"))
    )
    width = pl.col("weeks_upper") - pl.col("weeks_lower")
    value = pl.when(pl.col("weeks_upper").is_null()).then(pl.col("weeks_lower").cast(pl.Float64))
    value = value.otherwise(
        pl.col("weeks_lower") + width * (pl.col("target") - pl.col("prev")) / pl.col("patients")
    )
    return (
        bands.filter((pl.col("prev") < pl.col("target")) & (pl.col("target") <= pl.col("cum")))
        .group_by(keys).agg(value.first().round(1).alias("value"))
    )


def english_commissioned(long: pl.DataFrame) -> pl.DataFrame:
    """Rows on NHS England's published basis: excludes non-English commissioners (NONC)."""
    return long.filter(pl.col("commissioner_org_code") != NON_ENGLISH_COMMISSIONER)


def compute_view(long: pl.DataFrame, view: str) -> pl.DataFrame:
    """All v1 measures for one view, one row per period x org x treatment function."""
    df = _with_view(english_commissioned(long), view)
    keys = _KEYS
    name = df.group_by(["period", "org_code", "treatment_function_code"]).agg(
        pl.col("org_name").sort().last()
    )
    p2, p2a = _part("Part_2"), _part("Part_2A")
    p1a, p1b, p3 = _part("Part_1A"), _part("Part_1B"), _part("Part_3")
    n = pl.col("patients")
    lo, hi = pl.col("weeks_lower"), pl.col("weeks_upper")

    counts = df.group_by(["period", "org_code", "treatment_function_code"]).agg(
        n.filter(p2).sum().alias("waiting_list_total"),
        n.filter(p2a).sum().alias("waiting_list_dta"),
        n.filter(p2 & (hi <= 18)).sum().alias("_within_18"),
        n.filter(p2 & (lo >= 18)).sum().alias("waiting_over_18_weeks"),
        *[n.filter(p2 & (lo >= w)).sum().alias(f"waiting_over_{w}_weeks")
          for w in LONG_WAIT_THRESHOLDS],
        n.filter(p2 & (lo >= 40) & (hi <= 52)).sum().alias("approaching_52_weeks"),
        n.filter(p3).sum().alias("clock_starts"),
        n.filter(p1a).sum().alias("clock_stops_admitted"),
        n.filter(p1b).sum().alias("clock_stops_non_admitted"),
        n.filter(p1a & _BANDED).sum().alias("_1a_known"),
        n.filter(p1a & (hi <= 18)).sum().alias("_1a_within_18"),
        n.filter(p1b & _BANDED).sum().alias("_1b_known"),
        n.filter(p1b & (hi <= 18)).sum().alias("_1b_within_18"),
        pl.col("provider_org_code").n_unique().alias("providers_submitting"),
    )

    def pct(num: str, den: str) -> pl.Expr:
        return pl.when(pl.col(den) > 0).then((100 * pl.col(num) / pl.col(den)).round(1))

    out = counts.with_columns(
        pct("waiting_list_dta", "waiting_list_total").alias("pct_waiting_list_dta"),
        pct("_within_18", "waiting_list_total").alias("pct_within_18_weeks"),
        (pl.col("clock_stops_admitted") + pl.col("clock_stops_non_admitted"))
        .alias("clock_stops_total"),
        pct("_1a_within_18", "_1a_known").alias("pct_completed_within_18_weeks_admitted"),
        pct("_1b_within_18", "_1b_known").alias("pct_completed_within_18_weeks_non_admitted"),
    ).drop([c for c in counts.columns if c.startswith("_")])

    grp = ["period", "org_code", "treatment_function_code"]
    for alias, part, q in [
        ("median_wait_weeks", "Part_2", 0.5),
        ("p92_wait_weeks", "Part_2", 0.92),
        ("median_wait_completed_admitted_weeks", "Part_1A", 0.5),
        ("median_wait_completed_non_admitted_weeks", "Part_1B", 0.5),
    ]:
        pv = percentile(df.filter(_part(part)), grp, q).rename({"value": alias})
        out = out.join(pv, on=grp, how="left")

    out = out.join(name, on=grp, how="left")
    out = _add_month_on_month(out, df)
    return out.with_columns(view=pl.lit(view)).select(
        ["view", *keys, *[c for c in out.columns if c not in (*keys, "view")]]
    ).sort(keys)


def _add_month_on_month(out: pl.DataFrame, df: pl.DataFrame) -> pl.DataFrame:
    """Month-on-month changes, simple and like-for-like, and experimental unexplained removals.

    Simple changes difference the published totals, so a provider that misses a submission
    or is recoded shows up as a fall (or rise). Like-for-like measures use only providers
    that submitted in both months. All are null where the previous month is not loaded.
    """
    grp = ["org_code", "treatment_function_code"]
    present = df.select("period", "provider_org_code").unique()
    loaded = present["period"].unique()
    # Rows whose provider also submitted in the previous / next month
    in_prev = present.with_columns(pl.col("period").dt.offset_by("1mo"), _in_prev=pl.lit(True))
    in_next = present.with_columns(pl.col("period").dt.offset_by("-1mo"), _in_next=pl.lit(True))
    flagged = (df.join(in_prev, on=["period", "provider_org_code"], how="left")
               .join(in_next, on=["period", "provider_org_code"], how="left"))
    n, p2 = pl.col("patients"), _part("Part_2")
    stops = _part("Part_1A") | _part("Part_1B")
    m_lo = pl.col("weeks_lower") >= 52
    now = flagged.filter(pl.col("_in_prev").fill_null(False)).group_by(["period", *grp]).agg(
        pl.lit(True).alias("_matched"),
        n.filter(p2).sum().alias("_list_m"),
        n.filter(p2 & m_lo).sum().alias("_52_m"),
        n.filter(_part("Part_3")).sum().alias("_starts_m"),
        n.filter(stops).sum().alias("_stops_m"),
    )
    before = (
        flagged.filter(pl.col("_in_next").fill_null(False)).group_by(["period", *grp]).agg(
            n.filter(p2).sum().alias("_prev_list_m"),
            n.filter(p2 & m_lo).sum().alias("_prev_52_m"),
        ).with_columns(pl.col("period").dt.offset_by("1mo"))
    )
    simple_prev = out.select(
        pl.col("period").dt.offset_by("1mo"), *grp,
        pl.col("waiting_list_total").alias("_prev_list"),
        pl.col("waiting_over_52_weeks").alias("_prev_52"),
    )
    has_prev = pl.col("period").dt.offset_by("-1mo").is_in(loaded.implode())
    # Matched components: absence from a month means zero. Simple previous totals stay null
    # when the org/specialty did not appear last month, so a new provider gets no "change".
    z = ["_list_m", "_52_m", "_starts_m", "_stops_m", "_prev_list_m", "_prev_52_m"]
    out = (out.join(simple_prev, on=["period", *grp], how="left")
           .join(now, on=["period", *grp], how="left")
           .join(before, on=["period", *grp], how="left")
           # An org/specialty absent from one month genuinely had zero there
           .with_columns(pl.when(has_prev).then(pl.col(c).fill_null(0)) for c in z))
    like_for_like = ["waiting_list_change_mom_like_for_like",
                     "waiting_over_52_weeks_change_mom_like_for_like",
                     "unreported_removals_like_for_like"]
    return out.with_columns(
        (pl.col("waiting_list_total") - pl.col("_prev_list")).alias("waiting_list_change_mom"),
        (pl.col("_prev_list") + pl.col("clock_starts") - pl.col("clock_stops_total")
         - pl.col("waiting_list_total")).alias("unreported_removals"),
        (pl.col("waiting_over_52_weeks") - pl.col("_prev_52"))
        .alias("waiting_over_52_weeks_change_mom"),
        (pl.col("_list_m") - pl.col("_prev_list_m"))
        .alias("waiting_list_change_mom_like_for_like"),
        (pl.col("_52_m") - pl.col("_prev_52_m"))
        .alias("waiting_over_52_weeks_change_mom_like_for_like"),
        (pl.col("_prev_list_m") + pl.col("_starts_m") - pl.col("_stops_m") - pl.col("_list_m"))
        .alias("unreported_removals_like_for_like"),
    ).with_columns(
        # No provider in the group submitted in both months: like-for-like is undefined
        pl.when(pl.col("_matched")).then(pl.col(c)).alias(c) for c in like_for_like
    ).drop([*z, "_matched", "_prev_list", "_prev_52"])


def compute_all_views(long: pl.DataFrame) -> pl.DataFrame:
    return pl.concat([compute_view(long, v) for v in VIEWS], how="vertical_relaxed")


def submission_changes(long: pl.DataFrame) -> pl.DataFrame:
    """Per period: providers submitting, and providers present last month but missing now."""
    seen = long.select("period", "provider_org_code", "provider_org_name").unique()
    by_period = seen.group_by("period").agg(
        pl.col("provider_org_code").n_unique().alias("providers_submitting")
    )
    prev = seen.with_columns(pl.col("period").dt.offset_by("1mo"))
    periods = by_period["period"].to_list()
    missing = (
        prev.filter(pl.col("period").is_in(periods))
        .join(seen, on=["period", "provider_org_code"], how="anti")
        .group_by("period").agg(
            pl.struct(code="provider_org_code", name="provider_org_name")
            .alias("new_non_submitters")
        )
    )
    has_prev = prev["period"].unique().to_list()
    return (
        by_period.join(missing, on="period", how="left")
        .with_columns(
            pl.when(pl.col("period").is_in(has_prev))
            .then(pl.col("new_non_submitters").fill_null([]))
            .alias("new_non_submitters")
        )
        .sort("period")
    )
