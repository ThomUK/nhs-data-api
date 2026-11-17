"""Organisation reference data from the public ODS ORD API (ADR 0008)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import httpx

from .ingest.fetch import USER_AGENT

ORD_BASE = "https://directory.spineservices.nhs.uk/ORD/2-0-0"


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


def _operational(dates: list[dict]) -> tuple[date | None, date | None]:
    for d in dates:
        if d.get("Type") == "Operational":
            start, end = d.get("Start"), d.get("End")
            return (date.fromisoformat(start) if start else None,
                    date.fromisoformat(end) if end else None)
    return None, None


def parse_organisation(payload: dict) -> Organisation:
    org = payload["Organisation"]
    start, end = _operational(org.get("Date", []))
    roles = org.get("Roles", {}).get("Role", [])
    primary = next((r["id"] for r in roles if r.get("primaryRole")), None)
    succ = org.get("Succs", {}).get("Succ", [])

    def targets(kind: str) -> list[str]:
        return [s["Target"]["OrgId"]["extension"] for s in succ if s["Type"] == kind]

    return Organisation(
        org_code=org["OrgId"]["extension"],
        name=org["Name"],
        status=org["Status"],
        primary_role=primary,
        operational_start=start,
        operational_end=end,
        successors=targets("Successor"),
        predecessors=targets("Predecessor"),
    )


def fetch_organisation(org_code: str, client: httpx.Client | None = None) -> Organisation:
    own = client is None
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30)
    try:
        resp = client.get(f"{ORD_BASE}/organisations/{org_code}")
        resp.raise_for_status()
        return parse_organisation(resp.json())
    finally:
        if own:
            client.close()


def resolve_current(org_code: str, lookup: dict[str, Organisation], max_hops: int = 10) -> str:
    """Follow successor links to the organisation that carries this one's activity today.

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
