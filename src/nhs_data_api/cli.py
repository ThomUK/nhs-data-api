"""Command line: `nda ingest-rtt FILE_OR_URL --vintage YYYY-MM-DD`, `nda catalogue-check`."""

from __future__ import annotations

import argparse
from pathlib import Path

from .catalogue import load_catalogue
from .ingest import rtt
from .ingest.fetch import archive_url
from .paths import PROCESSED_DIR


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="nda")
    sub = p.add_subparsers(dest="cmd", required=True)
    ing = sub.add_parser("ingest-rtt", help="archive and parse one RTT Full CSV file")
    ing.add_argument("source", help="local path or https URL of the Full CSV (zip or csv)")
    ing.add_argument("--vintage", required=True, help="publication date, YYYY-MM-DD")
    sub.add_parser("catalogue-check", help="validate catalogue YAML")
    args = p.parse_args(argv)

    if args.cmd == "catalogue-check":
        for ds in load_catalogue().values():
            print(f"ok  {ds.id:8} {ds.status:6} {len(ds.measures)} measures")
    elif args.cmd == "ingest-rtt":
        src = args.source
        if src.startswith("https://"):
            archived = archive_url(src, "rtt", args.vintage)
            print(("already archived: " if archived.already_present else "archived: ")
                  + str(archived.path))
            src = archived.path
        df = rtt.tidy(rtt.read_full_csv(Path(src)))
        out = rtt.write_vintage(df, PROCESSED_DIR / "rtt", args.vintage)
        print(f"wrote {df.height:,} rows to {out}")


if __name__ == "__main__":
    main()
