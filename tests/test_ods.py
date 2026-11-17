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
