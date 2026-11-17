"""Organisation reference data from the public ODS ORD API (ADR 0008).

Builds an organisation table for every code that appears in the statistics, a lineage map
(which organisation carries another's activity after mergers and recodes), and candidate
recodes that ODS itself does not record as successions.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path

import httpx
import polars as pl
import yaml

from .ingest.fetch import USER_AGENT
from .paths import CATALOGUE_DIR

ORD_BASE = "https://directory.spineservices.nhs.uk/ORD/2-0-0"
REQUEST_INTERVAL = 0.1  # seconds between ORD requests; it is a public API, stay gentle
NHS_TRUST_ROLE = "RO197"
NON_ORGANISATION_CODES = {"NONC"}  # pseudo-codes used in the statistics


@dataclass
class Organisation:
    org_code: str
    name: str
    status: str
    primary_role: str | None
    operational_start: date | None
    operational_end: date | None
    successors: list[str] = field(default_factory=list)
    predecessors: list[str] = field(default_factory=list)
    successor_dates: dict[str, date | None] = field(default_factory=dict)
    legal_start: date | None = None
    legal_end: date | None = None
    roles: list[str] = field(default_factory=list)
    postcode: str | None = None
    address_line1: str | None = None
    town: str | None = None
    operated_by: str | None = None  # active RE6 relationship (parent organisation)

    @property
    def closed_on(self) -> date | None:
        """Earliest operational or legal end date, if any."""
        ends = [d for d in (self.operational_end, self.legal_end) if d]
        return min(ends) if ends else None


def _dates(dates: list[dict], kind: str) -> tuple[date | None, date | None]:
    for d in dates:
        if d.get("Type") == kind:
            start, end = d.get("Start"), d.get("End")
            return (date.fromisoformat(start) if start else None,
                    date.fromisoformat(end) if end else None)
    return None, None


def parse_organisation(payload: dict) -> Organisation:
    org = payload["Organisation"]
    op_start, op_end = _dates(org.get("Date", []), "Operational")
    legal_start, legal_end = _dates(org.get("Date", []), "Legal")
    roles = org.get("Roles", {}).get("Role", [])
    primary = next((r["id"] for r in roles if r.get("primaryRole")), None)
    succ = org.get("Succs", {}).get("Succ", [])

    def targets(kind: str) -> list[str]:
        return [s["Target"]["OrgId"]["extension"] for s in succ if s["Type"] == kind]

    successor_dates = {}
    for s in succ:
        if s["Type"] == "Successor":
            start = (s.get("Date") or [{}])[0].get("Start")
            successor_dates[s["Target"]["OrgId"]["extension"]] = (
                date.fromisoformat(start) if start else None)
    loc = org.get("GeoLoc", {}).get("Location", {})
    rels = org.get("Rels", {}).get("Rel", [])
    operated_by = next((r["Target"]["OrgId"]["extension"] for r in rels
                        if r.get("id") == "RE6" and r.get("Status") == "Active"), None)
    return Organisation(
        org_code=org["OrgId"]["extension"],
        name=org["Name"],
        status=org["Status"],
        primary_role=primary,
        operational_start=op_start,
        operational_end=op_end,
        successors=targets("Successor"),
        predecessors=targets("Predecessor"),
        successor_dates=successor_dates,
        legal_start=legal_start,
        legal_end=legal_end,
        roles=[r["id"] for r in roles],
        postcode=loc.get("PostCode"),
        address_line1=loc.get("AddrLn1"),
        town=loc.get("Town"),
        operated_by=operated_by,
    )


# ---------------------------------------------------------------- fetching and snapshots

def fetch_snapshot(codes: set[str], out_dir: Path, follow_successors: bool = True,
                   client: httpx.Client | None = None) -> Path:
    """Fetch ORD records for `codes` (and their successors) into a JSON Lines snapshot.

    Writes out_dir/organisations.jsonl (one raw ORD payload per line, or a not-found marker)
    and out_dir/roles.json. The snapshot is the raw archive record (ADR 0006).
    """
    own = client is None
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30)
    out_dir.mkdir(parents=True, exist_ok=True)
    todo = sorted(c for c in codes if c and c not in NON_ORGANISATION_CODES)
    seen: set[str] = set()
    try:
        with (out_dir / "organisations.jsonl").open("w") as fh:
            while todo:
                code = todo.pop(0)
                if code in seen:
                    continue
                seen.add(code)
                time.sleep(REQUEST_INTERVAL)
                resp = client.get(f"{ORD_BASE}/organisations/{code}")
                if resp.status_code == 404:
                    fh.write(json.dumps({"org_code": code, "not_found": True}) + "\n")
                    continue
                resp.raise_for_status()
                payload = resp.json()
                fh.write(json.dumps({"org_code": code, "payload": payload}) + "\n")
                if follow_successors:
                    todo.extend(s for s in parse_organisation(payload).successors
                                if s not in seen)
        roles = client.get(f"{ORD_BASE}/roles")
        roles.raise_for_status()
        (out_dir / "roles.json").write_text(roles.text)
    finally:
        if own:
            client.close()
    return out_dir


def load_snapshot(snapshot_dir: Path) -> tuple[dict[str, Organisation], dict[str, str], set[str]]:
    """Parse a snapshot: organisations by code, role names by id, and codes not found."""
    orgs, missing = {}, set()
    for line in (snapshot_dir / "organisations.jsonl").read_text().splitlines():
        rec = json.loads(line)
        if rec.get("not_found"):
            missing.add(rec["org_code"])
        else:
            org = parse_organisation(rec["payload"])
            orgs[org.org_code] = org
    roles = {r["id"]: r["displayName"]
             for r in json.loads((snapshot_dir / "roles.json").read_text())["Roles"]}
    return orgs, roles, missing


def latest_snapshot(raw_dir: Path) -> Path | None:
    snaps = sorted(p for p in (raw_dir / "ods").glob("*") if (p / "organisations.jsonl").exists())
    return snaps[-1] if snaps else None


def sector(org: Organisation, role_names: dict[str, str]) -> str:
    if org.primary_role == NHS_TRUST_ROLE:
        return "nhs_trust"
    name = role_names.get(org.primary_role or "", "")
    if "INDEPENDENT SECTOR" in name:
        return "independent_sector"
    if "COMMISSIONING" in name or "INTEGRATED CARE BOARD" in name or "SUB ICB" in name:
        return "commissioner"
    return "other"


def organisations_frame(orgs: dict[str, Organisation], role_names: dict[str, str]) -> pl.DataFrame:
    rows = []
    for o in orgs.values():
        d = asdict(o)
        d.pop("successor_dates")
        d["primary_role_name"] = role_names.get(o.primary_role or "")
        d["sector"] = sector(o, role_names)
        d["closed_on"] = o.closed_on
        rows.append(d)
    return pl.DataFrame(rows, schema_overrides={
        "operational_start": pl.Date, "operational_end": pl.Date, "legal_start": pl.Date,
        "legal_end": pl.Date, "closed_on": pl.Date,
        "successors": pl.List(pl.Utf8), "predecessors": pl.List(pl.Utf8),
        "roles": pl.List(pl.Utf8)}, infer_schema_length=None).sort("org_code")


# ------------------------------------------------------------------------------- lineage

@dataclass(frozen=True)
class LineageLink:
    from_code: str
    to_code: str
    effective: date | None
    source: str      # "ods" or "curated"
    evidence: str


@lru_cache
def curated_links(path: Path = CATALOGUE_DIR / "organisation_lineage.yaml") -> tuple:
    """Confirmed links that ODS does not record (catalogue/organisation_lineage.yaml)."""
    if not path.exists():
        return ()
    entries = yaml.safe_load(path.read_text()).get("links", [])
    return tuple(
        LineageLink(e["from"], e["to"], e.get("effective"), "curated", e["evidence"])
        for e in entries if e.get("status") == "confirmed")


def lineage_links(orgs: dict[str, Organisation], curated: tuple = ()) -> list[LineageLink]:
    links = [LineageLink(o.org_code, o.successors[0], o.successor_dates.get(o.successors[0]),
                         "ods", "ODS successor record")
             for o in orgs.values() if len(o.successors) == 1]
    return links + list(curated)


def resolve_current(org_code: str, lookup: dict[str, Organisation], max_hops: int = 10) -> str:
    """Follow ODS successor links to the organisation carrying this one's activity today.

    Where an organisation split into several successors, the chain stops and returns the
    original code: splits need an explicit apportionment rule, not a silent guess.
    """
    code = org_code
    for _ in range(max_hops):
        org = lookup.get(code)
        if org is None or len(org.successors) != 1:
            return code
        code = org.successors[0]
    raise RuntimeError(f"successor chain from {org_code} exceeds {max_hops} hops")


def lineage_map(links: list[LineageLink], max_hops: int = 10) -> dict[str, str]:
    """Map every linked code to the end of its chain (only codes that change are included)."""
    nxt: dict[str, set[str]] = {}
    for link in links:
        nxt.setdefault(link.from_code, set()).add(link.to_code)
    out = {}
    for start in nxt:
        code = start
        for _ in range(max_hops):
            targets = nxt.get(code)
            if not targets or len(targets) != 1:
                break
            code = next(iter(targets))
        if code != start:
            out[start] = code
    return out


def recode_candidates(seen: pl.DataFrame, orgs: dict[str, Organisation],
                      known: dict[str, str]) -> list[dict]:
    """Providers that stop reporting as a new code starts at the same site address.

    `seen` has one row per (period, provider_org_code). Exact postcode plus first address
    line is required, the new code must first appear in the month the old one stops (or the
    month after), and links already known (ODS or curated) are reported as such.
    """
    periods = sorted(seen["period"].unique().to_list())
    by_period = {p: set(seen.filter(pl.col("period") == p)["provider_org_code"])
                 for p in periods}
    first = {c: p for p in reversed(periods) for c in by_period[p]}
    out = []
    for i in range(1, len(periods)):
        gone = by_period[periods[i - 1]] - by_period[periods[i]]
        window = periods[i:i + 2]
        new = {c for c, p in first.items() if p in window and p != periods[0]}
        for old in gone:
            o = orgs.get(old)
            if not o or not o.postcode:
                continue
            for cand in new:
                c = orgs.get(cand)
                if (c and c.postcode == o.postcode
                        and (c.address_line1 or "").upper() == (o.address_line1 or "").upper()):
                    out.append({
                        "from": old, "from_name": o.name, "to": cand, "to_name": c.name,
                        "last_reported": periods[i - 1].isoformat(),
                        "first_reported": first[cand].isoformat(),
                        "address": f"{o.address_line1}, {o.postcode}",
                        "operator_change": f"{o.operated_by} → {c.operated_by}"
                        if o.operated_by != c.operated_by else None,
                        "applied": known.get(old) == cand,
                    })
    return out
