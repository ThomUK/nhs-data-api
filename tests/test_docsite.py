import json

from nhs_data_api.docsite import build_docs
from nhs_data_api.ingest import rtt
from nhs_data_api.store import build_rtt_metrics

from .conftest import make_row, to_csv


def test_build_docs(tmp_path):
    processed, out = tmp_path / "processed", tmp_path / "api"
    rows = [make_row("RJ1", "Part_2", "C_999", {3: 10}, period="RTT-September-2026")]
    rtt.write_vintage(rtt.tidy(rtt.read_full_csv(to_csv(rows))), processed / "rtt", "2026-11-12")
    build_rtt_metrics(processed, raw_dir=tmp_path / "raw")
    import polars as pl
    (processed / "ods").mkdir()
    pl.DataFrame({"org_code": ["RA7"], "name": ["BRISTOL NHS FOUNDATION TRUST"],
                  "sector": ["nhs_trust"]}).write_parquet(
        processed / "ods" / "organisations.parquet")
    files = {p.relative_to(out).as_posix() for p in build_docs(out, processed_dir=processed)}
    assert {"index.html", "reference.html", "objects.html", "errors.html", "datasets.html",
            "openapi.json", "llms.txt",
            "datasets/rtt.html", "datasets/organisations.html", "assets/docs.css"} <= files

    overview = (out / "index.html").read_text()
    assert overview.count("<strong>Response</strong>") == 3  # one per quick-start example
    assert "&quot;org_code&quot;: &quot;RJ1&quot;" in overview
    objects = (out / "objects.html").read_text()
    for anchor in ("measure_row", "meta", "organisation", "submission_record", "non_submitter"):
        assert f"id='{anchor}'" in objects
    assert "field-pct_within_18_weeks" in objects        # measure fields from the catalogue
    errors = (out / "errors.html").read_text()
    assert "id='e404'" in errors and "id='e422'" in errors
    assert "Response · 422" in errors                   # a real error response was rendered
    reference = (out / "reference.html").read_text()
    assert "class=split" in reference and "objects.html#measure_row" in reference
    assert "/v1/rtt/metrics" in reference and ">Response<" in reference  # real example rendered
    assert json.loads((out / "openapi.json").read_text())["paths"]["/v1/rtt/metrics"]
    llms = (out / "llms.txt").read_text()
    assert "`waiting_list_total`" in llms and "meta.attribution" in llms
    rtt_page = (out / "datasets" / "rtt.html").read_text()
    assert "pct_within_18_weeks" in rtt_page and "population_icb" in rtt_page
    # Self-contained: no links into the private admin pages
    for name in files:
        if name.endswith(".html"):
            text = (out / name).read_text()
            assert "timeseries.html" not in text and "validation.html" not in text
