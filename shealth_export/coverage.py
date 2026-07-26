"""Build the coverage manifest.

The manifest is the promise that *nothing is dropped silently*: every datatype
present in the export is listed with its status — included (with row counts and
the date of its newest record), consumed by another section, deliberately
excluded (with a reason), or — importantly — UNKNOWN: a datatype this tool has
never seen, which a future export might introduce.
"""

from __future__ import annotations

import csv

from . import csvio
from .extract import Result
from .registry import CONSUMED, EXCLUDED, by_id


def _count_rows(path: str) -> int:
    try:
        with open(path, encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            next(reader, None)   # metadata
            next(reader, None)   # header
            return sum(1 for r in reader if r)
    except OSError:
        return -1


def build(export_dir: str, timecode: str, results: dict[str, Result]) -> dict:
    present = csvio.list_datatypes(export_dir, timecode)
    included = by_id()
    entries: list[dict] = []
    unknown: list[str] = []

    for dtid in present:
        path = csvio.csv_path(export_dir, dtid, timecode)
        if dtid in included:
            r = results.get(dtid)
            dt = included[dtid]
            if not dt.subkey:   # emitted as the patient_profile header, not a windowed series
                entries.append({
                    "datatype": dtid, "status": "included_header",
                    "category": dt.category,
                    "note": "emitted as patient_profile header; not filtered by the day window",
                    "fields_total": r.rows_total if r else 0,
                })
            else:
                entries.append({
                    "datatype": dtid, "status": "included",
                    "category": dt.category, "section": dt.subkey,
                    "rows_total": r.rows_total if r else 0,
                    "rows_in_window": r.rows_in_window if r else 0,
                    "detail_items_in_window": r.detail_items if r else 0,
                    "last_record": r.last_record if r else None,
                })
        elif dtid in CONSUMED:
            entries.append({
                "datatype": dtid, "status": "consumed",
                "note": CONSUMED[dtid], "rows_total": _count_rows(path),
            })
        elif dtid in EXCLUDED:
            kind, reason = EXCLUDED[dtid]
            entries.append({
                "datatype": dtid, "status": "excluded",
                "exclusion_kind": kind, "reason": reason, "rows_total": _count_rows(path),
            })
        else:
            unknown.append(dtid)
            entries.append({
                "datatype": dtid, "status": "UNKNOWN",
                "note": "datatype not known to this tool version — review manually",
                "rows_total": _count_rows(path),
            })

    # datatypes we expected but that are missing from this export
    missing = [dtid for dtid in included if dtid not in present]
    for dtid in missing:
        entries.append({"datatype": dtid, "status": "missing_from_export"})

    entries.sort(key=lambda e: (e["status"] != "UNKNOWN", e["status"], e["datatype"]))

    incl = [e for e in entries if e["status"] in ("included", "included_header")]
    summary = {
        "datatypes_present": len(present),
        "included": len(incl),
        "included_with_data_in_window": sum(1 for e in incl if e.get("rows_in_window")),
        "consumed": sum(1 for e in entries if e["status"] == "consumed"),
        "excluded": sum(1 for e in entries if e["status"] == "excluded"),
        "unknown": len(unknown),
        "missing_from_export": len(missing),
    }
    if unknown:
        summary["unknown_datatypes"] = unknown
    return {"summary": summary, "datatypes": entries}
