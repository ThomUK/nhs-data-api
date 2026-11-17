from nhs_data_api.catalogue import load_catalogue


def test_catalogue_loads_and_is_consistent():
    cat = load_catalogue()
    assert {"rtt", "wlmds"} <= set(cat)
    rtt = cat["rtt"]
    dim_ids = {d.id for d in rtt.dimensions}
    assert set(rtt.grain) - {"weeks_band"} <= dim_ids | {"weeks_band"}
    assert rtt.measure("pct_within_18_weeks").unit == "percent"
    for ds in cat.values():
        assert "Open Government Licence" in ds.licence.name  # ADR 0002
