import json
from datetime import date
from pathlib import Path

from nhs_data_api.ods import Organisation, parse_organisation, resolve_current

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_real_ord_payload():
    org = parse_organisation(json.loads((FIXTURES / "ods_RJ1.json").read_text()))
    assert org.org_code == "RJ1"
    assert org.primary_role == "RO197"
    assert org.operational_start == date(1993, 4, 1)
    assert "GN1" in org.predecessors


def _org(code, successors=()):
    return Organisation(code, code, "Inactive", "RO197", None, None, list(successors))


def test_resolve_follows_chain_and_stops_at_splits():
    lookup = {"A": _org("A", ["B"]), "B": _org("B", ["C"]), "C": _org("C"),
              "S": _org("S", ["X", "Y"])}
    assert resolve_current("A", lookup) == "C"
    assert resolve_current("S", lookup) == "S"
    assert resolve_current("UNKNOWN", lookup) == "UNKNOWN"


def test_parse_extended_fields():
    org = parse_organisation(json.loads((FIXTURES / "ods_RJ1.json").read_text()))
    assert org.postcode and org.address_line1
    assert "RO197" in org.roles


def _site(code, postcode, addr, operator):
    return Organisation(code, code, "Active", "RO176", None, None, postcode=postcode,
                        address_line1=addr, operated_by=operator)


def test_recode_candidates_same_address():
    import polars as pl

    from nhs_data_api.ods import recode_candidates
    seen = pl.DataFrame({"period": [date(2026, 7, 1), date(2026, 8, 1), date(2026, 8, 1),
                                    date(2026, 9, 1), date(2026, 9, 1)],
                         "provider_org_code": ["OLD", "OLD", "X", "NEW", "X"]})
    orgs = {"OLD": _site("OLD", "IG3 8YY", "King George Hospital", "NTP"),
            "NEW": _site("NEW", "IG3 8YY", "KING GEORGE HOSPITAL", "N1Y5A"),
            "X": _site("X", "AB1 2CD", "Elsewhere", "Z")}
    cands = recode_candidates(seen, orgs, known={})
    assert [(c["from"], c["to"]) for c in cands] == [("OLD", "NEW")]
    assert cands[0]["operator_change"] == "NTP → N1Y5A" and not cands[0]["applied"]
    assert recode_candidates(seen, orgs, known={"OLD": "NEW"})[0]["applied"]


def test_lineage_map_follows_chains_and_skips_splits():
    from nhs_data_api.ods import LineageLink, lineage_map
    links = [LineageLink("A", "B", None, "ods", ""), LineageLink("B", "C", None, "ods", ""),
             LineageLink("S", "X", None, "ods", ""), LineageLink("S", "Y", None, "ods", "")]
    assert lineage_map(links) == {"A": "C", "B": "C"}


def test_curated_lineage_file_is_valid():
    from nhs_data_api.ods import curated_links
    links = curated_links()
    assert links and all(lk.source == "curated" and lk.evidence for lk in links)
