"""Command-line entry point.

Interactive by default: if ``--days`` is not supplied, the tool asks how many
days back to include. It locates the newest export under ``--data-dir`` (default
``data/``) unless an explicit ``--folder`` is given.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime

from . import assemble, selftest
from .discovery import Export, as_export, find_latest_export
from .timeutil import timecode_to_date


def _prompt_days() -> int:
    while True:
        try:
            raw = input("How many days back should be exported? ").strip()
        except EOFError:
            print("No input received.", file=sys.stderr)
            sys.exit(2)
        if raw.isdigit() and int(raw) > 0:
            return int(raw)
        print("Please enter a positive whole number of days (e.g. 14).")


def _resolve_export(args) -> Export | None:
    if args.folder:
        return as_export(args.folder)
    return find_latest_export(args.data_dir)


def _anchor_date(export: Export, args) -> date:
    if args.anchor:
        try:
            return datetime.strptime(args.anchor, "%Y-%m-%d").date()
        except ValueError:
            print(f"Invalid --anchor '{args.anchor}'; expected YYYY-MM-DD.", file=sys.stderr)
            sys.exit(2)
    return timecode_to_date(export.timecode) or date.today()


def _print_summary(document: dict, manifest: dict, out_path: str, size: int,
                   min_path: str | None = None, min_size: int = 0) -> None:
    md = document["metadata"]
    win = md["window"]
    print(f"\nExport written: {out_path}  ({size / 1_000_000:.2f} MB)")
    if min_path:
        print(f"Minified:       {min_path}  ({min_size / 1_000_000:.2f} MB)")
    print(f"Source: {md['source_export']}")
    print(f"Window: {win['start_date']} .. {win['end_date']} "
          f"({win['n_days']} days, {win['primary_utc_offset']})")
    s = manifest["summary"]
    print(f"Datatypes present: {s['datatypes_present']} | included: {s['included']} "
          f"(with data in window: {s['included_with_data_in_window']}) | "
          f"consumed: {s['consumed']} | excluded: {s['excluded']} | unknown: {s['unknown']}")

    with_data = [e for e in manifest["datatypes"]
                 if e["status"] == "included" and e.get("rows_in_window")]
    if with_data:
        print("\nWith data in window:")
        for e in sorted(with_data, key=lambda x: -x["rows_in_window"]):
            extra = f" (+{e['detail_items_in_window']} detail pts)" if e.get("detail_items_in_window") else ""
            print(f"  {e['datatype']:52} {e['rows_in_window']:>7} rows{extra}")

    stale = [e for e in manifest["datatypes"]
             if e["status"] == "included" and not e.get("rows_in_window") and e.get("last_record")]
    if stale:
        print("\nIn export but NOT in window (last record shown — not 'normal', just old/absent):")
        for e in sorted(stale, key=lambda x: x["last_record"] or ""):
            print(f"  {e['datatype']:52} last: {e['last_record']}")

    if s.get("unknown"):
        print("\n⚠ UNKNOWN datatypes (new to this tool — review manually):")
        for dtid in s.get("unknown_datatypes", []):
            print(f"  {dtid}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="export_health",
        description="Export Samsung Health data for the last N days into one JSON file.")
    p.add_argument("--data-dir", default="data",
                   help="directory that contains the export folder(s) (default: data)")
    p.add_argument("--folder", help="explicit path to an export folder (overrides --data-dir)")
    p.add_argument("--days", type=int, help="number of days back to include (asked interactively if omitted)")
    p.add_argument("--anchor", help="anchor date YYYY-MM-DD (default: the export's own date)")
    p.add_argument("--out", help="output JSON filename or path (default: health_export_<start>_to_<end>.json)")
    p.add_argument("--out-dir",
                   help="directory to write the result into (created if missing; default: current directory)")
    p.add_argument("--no-minify", action="store_true",
                   help="do not also write a compact <out>.min.json companion")
    p.add_argument("--selftest", action="store_true", help="run self-checks and exit")
    args = p.parse_args(argv)

    export = _resolve_export(args)

    if args.selftest:
        return selftest.run(export)

    if export is None:
        where = args.folder or args.data_dir
        print(f"No Samsung Health export folder found in: {where}", file=sys.stderr)
        return 2

    days = args.days if args.days and args.days > 0 else _prompt_days()
    anchor = _anchor_date(export, args)

    document, manifest = assemble.build_document(export, days, anchor)
    win = document["metadata"]["window"]
    out_name = args.out or f"health_export_{win['start_date']}_to_{win['end_date']}.json"
    if args.out_dir:
        os.makedirs(args.out_dir, exist_ok=True)
        out_path = os.path.join(args.out_dir, os.path.basename(out_name))
    else:
        out_path = out_name
    size, min_path, min_size = assemble.write(document, out_path, minify=not args.no_minify)
    _print_summary(document, manifest, out_path, size, min_path, min_size)
    return 0
