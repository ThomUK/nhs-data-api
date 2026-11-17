"""Command line: `nda ingest-rtt FILE_OR_URL --vintage YYYY-MM-DD`, `nda catalogue-check`."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from .catalogue import load_catalogue
from .ingest import rtt
from .ingest.fetch import archive_local, archive_url
from .paths import PROCESSED_DIR, RAW_DIR
from .store import build_rtt_metrics, read_rtt_metrics, rebuild_rtt


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="nda")
    sub = p.add_subparsers(dest="cmd", required=True)
    ing = sub.add_parser("ingest-rtt", help="archive and parse one RTT Full CSV file")
    ing.add_argument("source", help="local path or https URL of the Full CSV (zip or csv)")
    ing.add_argument("--vintage", required=True,
                     help="publication date YYYY-MM-DD, or 'auto' to infer it from the zip")
    ing.add_argument("--source-url", help="where a local file was downloaded from (provenance)")
    sub.add_parser("catalogue-check", help="validate catalogue YAML")
    sub.add_parser("build-rtt-metrics", help="recompute RTT measures for all views")
    sub.add_parser("rebuild-rtt", help="regenerate processed RTT data from the raw archive")
    sub.add_parser("fetch-ods", help="snapshot ODS records for every organisation in the data")
    ap = sub.add_parser("archive-push", help="update the manifest and push the raw archive")
    ap.add_argument("-m", "--message", default="Archive update")
    sub.add_parser("archive-verify", help="check archived files against the manifest")
    sub.add_parser("diff-vintages", help="compare archived versions of the same month")
    sub.add_parser("build-docs", help="generate the API documentation subsite (site/api)")
    arc = sub.add_parser("archive", help="copy a manually downloaded file into the raw archive")
    arc.add_argument("files", nargs="+")
    arc.add_argument("--dataset", required=True)
    arc.add_argument("--publication", required=True, help="publication date, YYYY-MM-DD")
    arc.add_argument("--source-url")
    site = sub.add_parser("build-site", help="export JSON for the admin site")
    site.add_argument("--out", default=None, help="output directory (default site/data)")
    rec = sub.add_parser("reconcile-rtt",
                         help="compare our measures with NHS England's Incomplete Provider xlsx")
    rec.add_argument("workbook", help="path to the Incomplete Provider workbook")
    rec.add_argument("--period", required=True, help="month as YYYY-MM-01")
    args = p.parse_args(argv)

    if args.cmd == "catalogue-check":
        for ds in load_catalogue().values():
            print(f"ok  {ds.id:8} {ds.status:6} {len(ds.measures)} measures")
    elif args.cmd == "ingest-rtt":
        src = args.source
        if args.vintage == "auto":
            if src.startswith("https://"):
                sys.exit("--vintage auto needs a local file")
            inferred, stamp = rtt.infer_vintage(Path(src))
            args.vintage = inferred.isoformat()
            print(f"vintage {args.vintage} (inferred from file date {stamp})")
        if src.startswith("https://"):
            archived = archive_url(src, "rtt", args.vintage)
        else:
            archived = archive_local(Path(src), "rtt", args.vintage, args.source_url)
        print(("already archived: " if archived.already_present else "archived: ")
              + str(archived.path))
        src = archived.path
        df = rtt.tidy(rtt.read_full_csv(Path(src)))
        out = rtt.write_vintage(df, PROCESSED_DIR / "rtt", args.vintage)
        print(f"wrote {df.height:,} rows to {out}")
        print("metrics: " + ", ".join(str(p) for p in build_rtt_metrics(PROCESSED_DIR)))
    elif args.cmd == "build-docs":
        from .docsite import build_docs
        for path in build_docs():
            print(f"wrote {path}")
    elif args.cmd == "diff-vintages":
        from .revisions import build_revisions
        out = build_revisions(PROCESSED_DIR)
        report = json.loads(out.read_text())
        for p in report["periods"]:
            note = "" if p["original_archived"] else (
                f"  (original release {p['expected_first_release']} not archived)")
            print(f"{p['period'][:7]}: versions {', '.join(p['vintages'])}{note}")
            for c in p["comparisons"]:
                print(f"    {c['old']} -> {c['new']}: rows changed {c['rows_changed']}, "
                      f"added {c['rows_added']}, removed {c['rows_removed']}, "
                      f"providers changed {c['providers_changed']}")
        print(f"report: {out}")
    elif args.cmd == "archive-push":
        from . import archive
        print(archive.push(RAW_DIR, args.message))
    elif args.cmd == "archive-verify":
        from . import archive
        v = archive.verify(RAW_DIR)
        print(f"checked {v.checked}; missing {v.missing}; changed {v.changed}; "
              f"not yet in manifest {v.unlisted}")
        sys.exit(0 if not (v.missing or v.changed) else 1)
    elif args.cmd == "fetch-ods":
        import polars as pl

        from . import ods
        from .store import latest_rtt_lazy
        cols = ["provider_org_code", "provider_parent_org_code", "commissioner_org_code",
                "commissioner_parent_org_code"]
        codes = set()
        for c in cols:
            codes |= set(latest_rtt_lazy(PROCESSED_DIR).select(pl.col(c).unique())
                         .collect()[c].drop_nulls())
        out = RAW_DIR / "ods" / date.today().isoformat()
        print(f"fetching {len(codes)} codes (plus successors) into {out}")
        ods.fetch_snapshot(codes, out)
        orgs, roles, missing = ods.load_snapshot(out)
        print(f"{len(orgs)} organisations, {len(missing)} not found: {sorted(missing)}")
        print("metrics: " + ", ".join(str(p) for p in build_rtt_metrics(PROCESSED_DIR)))
    elif args.cmd == "rebuild-rtt":
        for path in rebuild_rtt(PROCESSED_DIR, RAW_DIR):
            print(f"wrote {path}")
        print("metrics: " + ", ".join(str(p) for p in build_rtt_metrics(PROCESSED_DIR)))
    elif args.cmd == "build-rtt-metrics":
        print("metrics: " + ", ".join(str(p) for p in build_rtt_metrics(PROCESSED_DIR)))
    elif args.cmd == "archive":
        for f in args.files:
            a = archive_local(Path(f), args.dataset, args.publication, args.source_url)
            print(("already archived: " if a.already_present else "archived: ") + str(a.path))
    elif args.cmd == "build-site":
        from .site import build_site
        for path in build_site(Path(args.out) if args.out else None):
            print(f"wrote {path}")
    elif args.cmd == "reconcile-rtt":
        import polars as pl

        from .ingest.rtt_published import read_provider_workbook, reconcile
        ours = read_rtt_metrics(PROCESSED_DIR).filter(
            (pl.col("view") == "provider") & (pl.col("period") == date.fromisoformat(args.period))
        ).collect()
        result = reconcile(read_provider_workbook(Path(args.workbook)), ours)
        print(result.summary())
        out = PROCESSED_DIR / "validation" / "rtt" / f"{args.period}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result.to_json(args.period, Path(args.workbook).name), indent=2))
        print(f"recorded: {out}")
        for name, frame in result.mismatches.items():
            if not frame.is_empty():
                print(f"\n{name}:\n{frame.head(10)}")
        sys.exit(0 if result.ok else 1)


if __name__ == "__main__":
    main()
