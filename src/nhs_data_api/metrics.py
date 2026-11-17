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


def with_lineage(long: pl.DataFrame, links=None, max_hops: int = 5, offset: str = "1mo",
                 column: str = "provider_lineage_code") -> pl.DataFrame:
    """Add `column`: the provider carrying this one's activity after mergers and recodes.

    `links` are ods.LineageLink-like objects (from_code, to_code, effective). A link applies
    to a row when its period plus `offset` is on or after the link's effective date. With
    "1mo" (as of the following month), June figures of a trust merged in July count towards
    its successor when compared with July; with "0mo" (as of the row's own month) they do
    not. Codes with several outgoing links (splits) are not mapped.
    """
    out = long.with_columns(pl.col("provider_org_code").alias(column))
    if not links:
        return out
    table = pl.DataFrame(
        {"_from": [lk.from_code for lk in links], "_to": [lk.to_code for lk in links],
         "_eff": [lk.effective for lk in links]},
        schema={"_from": pl.Utf8, "_to": pl.Utf8, "_eff": pl.Date},
    ).filter(pl.col("_from").is_unique())
    out = out.with_columns(_cmp=pl.col("period").dt.offset_by(offset))
    for _ in range(max_hops):
        out = out.join(table, left_on=column, right_on="_from", how="left")
        apply = pl.col("_to").is_not_null() & (
            pl.col("_eff").is_null() | (pl.col("_eff") <= pl.col("_cmp")))
        if not out.select(apply.any()).item():
            out = out.drop("_to", "_eff")
            break
        out = out.with_columns(pl.when(apply).then(pl.col("_to")).otherwise(pl.col(column))
                               .alias(column)).drop("_to", "_eff")
    return out.drop("_cmp")


def compute_view(long: pl.DataFrame, view: str, lineage=None) -> pl.DataFrame:
    """All v1 measures for one view, one row per period x org x treatment function."""
    # Two lineage codes per row: as of its own month (when it is the current month of a
    # comparison) and as of the next month (when it is the previous month).
    base = with_lineage(english_commissioned(long), lineage, offset="0mo",
                        column="_lineage_now")
    df = _with_view(with_lineage(base, lineage, offset="1mo", column="_lineage_next"), view)
    # Previous-month grouping key: in the provider view, a predecessor's rows count towards
    # its successor (so a merger is not a like-for-like change); other views are unchanged.
    df = df.with_columns(_mom_key=pl.col("_lineage_next") if view == "provider"
                         else pl.col("org_code"))
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
    # Matching uses lineage codes: a provider and its successor count as the same provider.
    # A current-month row (lineage as of its month) is matched if some previous-month row has
    # the same lineage as of the following month, and vice versa.
    loaded = df["period"].unique()
    in_prev = (df.select("period", pl.col("_lineage_next").alias("_key")).unique()
               .with_columns(pl.col("period").dt.offset_by("1mo"), _in_prev=pl.lit(True)))
    in_next = (df.select("period", pl.col("_lineage_now").alias("_key")).unique()
               .with_columns(pl.col("period").dt.offset_by("-1mo"), _in_next=pl.lit(True)))
    flagged = (df.join(in_prev, left_on=["period", "_lineage_now"], right_on=["period", "_key"],
                       how="left")
               .join(in_next, left_on=["period", "_lineage_next"], right_on=["period", "_key"],
                     how="left"))
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
        flagged.filter(pl.col("_in_next").fill_null(False))
        .with_columns(org_code=pl.col("_mom_key"))
        .group_by(["period", *grp]).agg(
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


def compute_all_views(long: pl.DataFrame, lineage=None) -> pl.DataFrame:
    """All views. `lineage`: ods.LineageLink-like links applied to like-for-like matching."""
    return pl.concat([compute_view(long, v, lineage) for v in VIEWS], how="vertical_relaxed")


def submission_status(seen: pl.DataFrame, links=None,
                      orgs: pl.DataFrame | None = None) -> pl.DataFrame:
    """Per period: providers submitting, why last month's providers are missing, and NHS
    trusts that have been missing for longer.

    `seen` has (period, provider_org_code, provider_org_name). `links` are lineage links
    (mergers and recodes); `orgs` is the ODS organisation table (ods.organisations_frame),
    used for closure dates and to know which providers are NHS trusts.

    Reasons for a provider that submitted last month but not this month:
      merged_or_recoded  its lineage successor is submitting this month
      closed             ODS records it as closed by the end of this month
      not_submitting     anything else (usually a missed submission)
    Persistent non-submitters: NHS trusts (ODS role RO197) seen in an earlier month, missing
    for at least two months, not closed and not carried by a submitting successor.
    """
    seen = seen.unique(["period", "provider_org_code"])
    mapped = with_lineage(seen, links)
    periods = sorted(seen["period"].unique().to_list())
    names = dict(zip(seen["provider_org_code"], seen["provider_org_name"], strict=True))
    closed, trusts = {}, set()
    if orgs is not None:
        closed = {c: d for c, d in zip(orgs["org_code"], orgs["closed_on"], strict=True) if d}
        trusts = set(orgs.filter(pl.col("sector") == "nhs_trust")["org_code"])
    codes = {p: set(seen.filter(pl.col("period") == p)["provider_org_code"]) for p in periods}
    successor = {(r["period"], r["provider_org_code"]): r["provider_lineage_code"]
                 for r in mapped.iter_rows(named=True)}
    last_seen: dict[str, object] = {}
    rows = []
    for i, p in enumerate(periods):
        month_end = (pl.Series([p]).dt.offset_by("1mo").item())
        new, persistent = None, []
        if i > 0:
            prev = periods[i - 1]
            new = []
            for code in sorted(codes[prev] - codes[p]):
                target = successor.get((prev, code), code)
                if target != code and target in codes[p]:
                    reason = "merged_or_recoded"
                elif code in closed and closed[code] < month_end:
                    reason = "closed"
                else:
                    reason = "not_submitting"
                new.append({"code": code, "name": names.get(code), "reason": reason,
                            "successor": target if target != code else None,
                            "closed_on": closed.get(code)})
            for code, seen_at in sorted(last_seen.items()):
                if code in codes[p] or code in codes[prev] or code not in trusts:
                    continue
                if code in closed and closed[code] < month_end:
                    continue
                target = successor.get((seen_at, code), code)
                if target != code and target in codes[p]:
                    continue
                persistent.append({"code": code, "name": names.get(code),
                                   "last_reported": seen_at})
        rows.append({"period": p, "providers_submitting": len(codes[p]),
                     "new_non_submitters": new, "persistent_non_submitters": persistent})
        for code in codes[p]:
            last_seen[code] = p
    item = pl.Struct({"code": pl.Utf8, "name": pl.Utf8, "reason": pl.Utf8,
                      "successor": pl.Utf8, "closed_on": pl.Date})
    pitem = pl.Struct({"code": pl.Utf8, "name": pl.Utf8, "last_reported": pl.Date})
    return pl.DataFrame(rows, schema={"period": pl.Date, "providers_submitting": pl.UInt32,
                                      "new_non_submitters": pl.List(item),
                                      "persistent_non_submitters": pl.List(pitem)})


def submission_changes(seen: pl.DataFrame) -> pl.DataFrame:
    """Backwards-compatible alias: submission status without ODS context."""
    return submission_status(seen)
