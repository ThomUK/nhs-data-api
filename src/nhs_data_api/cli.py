"""Command line: `nda ingest-rtt FILE_OR_URL --vintage YYYY-MM-DD`, `nda catalogue-check`."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from .catalogue import load_catalogue
from .ingest import rtt
from .ingest.fetch import archive_local, archive_url
from .paths import PROCESSED_DIR
from .store import build_rtt_metrics, read_rtt_metrics


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="nda")
    sub = p.add_subparsers(dest="cmd", required=True)
    ing = sub.add_parser("ingest-rtt", help="archive and parse one RTT Full CSV file")
    ing.add_argument("source", help="local path or https URL of the Full CSV (zip or csv)")
    ing.add_argument("--vintage", required=True, help="publication date, YYYY-MM-DD")
    ing.add_argument("--source-url", help="where a local file was downloaded from (provenance)")
    sub.add_parser("catalogue-check", help="validate catalogue YAML")
    sub.add_parser("build-rtt-metrics", help="recompute RTT measures for all views")
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
    elif args.cmd == "build-rtt-metrics":
        print("metrics: " + ", ".join(str(p) for p in build_rtt_metrics(PROCESSED_DIR)))
    elif args.cmd == "reconcile-rtt":
        import polars as pl

        from .ingest.rtt_published import read_provider_workbook, reconcile
        ours = read_rtt_metrics(PROCESSED_DIR).filter(
            (pl.col("view") == "provider") & (pl.col("period") == date.fromisoformat(args.period))
        ).collect()
        result = reconcile(read_provider_workbook(Path(args.workbook)), ours)
        print(result.summary())
        for name, frame in result.mismatches.items():
            if not frame.is_empty():
                print(f"\n{name}:\n{frame.head(10)}")
        sys.exit(0 if result.ok else 1)


if __name__ == "__main__":
    main()
