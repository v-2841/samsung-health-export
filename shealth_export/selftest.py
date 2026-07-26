"""Self-checks: pure time logic + an empirical timezone proof against real data.

Run via ``python3 export_health.py --selftest``. The empirical check re-derives
the "CSV strings are UTC" fact by comparing a heart-rate row's start_time
string with the minimum epoch-ms in its own binning JSON.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone

from . import timeutil
from .csvio import csv_path, iter_json_shard_path, read_table
from .discovery import Export


def _check(name: str, cond: bool, detail: str = "") -> bool:
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return cond


def unit_checks() -> bool:
    ok = True
    tz = timeutil.parse_offset("UTC+0400")
    ok &= _check("parse_offset UTC+0400", tz is not None and tz.utcoffset(None).total_seconds() == 4 * 3600)
    ok &= _check("negative offset UTC-0500",
                 timeutil.parse_offset("UTC-0500").utcoffset(None).total_seconds() == -5 * 3600)

    iso = timeutil.utc_string_to_iso("2025-01-08 21:00:00.000", "UTC+0400")
    ok &= _check("utc string -> local iso (+4h shift)", iso == "2025-01-09T01:00:00+04:00", iso)

    d = timeutil.utc_string_to_local_date("2025-01-08 21:00:00.000", "UTC+0400")
    ok &= _check("local date crosses midnight", d == date(2025, 1, 9), str(d))

    w = timeutil.Window.last_n_days(date(2026, 7, 22), 14)
    ok &= _check("window length inclusive",
                 w.start_date == date(2026, 7, 9) and w.end_date == date(2026, 7, 22))
    ok &= _check("window contains/excludes",
                 w.contains(date(2026, 7, 10)) and not w.contains(date(2026, 7, 8)))
    return bool(ok)


def timezone_proof(export: Export) -> bool:
    path = csv_path(export.path, "com.samsung.shealth.tracker.heart_rate", export.timecode)
    if not path:
        return _check("timezone proof", False, "heart_rate table missing")
    table = read_table(path, "com.samsung.health.heart_rate.")
    for row in table.rows[:200]:
        ref = row.get("binning_data")
        start = row.get("start_time")
        jp = iter_json_shard_path(export.path, "com.samsung.shealth.tracker.heart_rate", ref)
        if not (ref and start and jp):
            continue
        with open(jp, encoding="utf-8-sig") as f:
            arr = json.load(f)
        epochs = [e["start_time"] for e in arr if isinstance(e, dict) and "start_time" in e]
        if not epochs:
            continue
        utc_str = datetime.fromtimestamp(min(epochs) / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
        return _check("CSV start_time string equals UTC rendering of binning epoch-ms",
                      start[:16] == utc_str, f"csv={start[:16]} utc={utc_str}")
    return _check("timezone proof", False, "no resolvable binning row found")


def run(export: Export | None) -> int:
    print("Unit checks:")
    ok = unit_checks()
    if export:
        print("Empirical checks (real data):")
        ok = timezone_proof(export) and ok
    else:
        print("  (no export found — skipping empirical checks)")
    print("OK" if ok else "FAILURES DETECTED")
    return 0 if ok else 1
