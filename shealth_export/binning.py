"""Load and map the high-resolution binning JSON referenced by a CSV row."""

from __future__ import annotations

import json

from . import timeutil
from .csvio import iter_json_shard_path
from .registry import Binning


def load_json(export_dir: str, dir_suffix: str, ref_value: str):
    """Parsed companion JSON for ``ref_value`` or None (missing / bad)."""
    path = iter_json_shard_path(export_dir, dir_suffix, ref_value)
    if not path:
        return None
    try:
        with open(path, encoding='utf-8-sig') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None


def extract_detail(export_dir: str, binning: Binning, ref_value: str,
                   offset_str: str | None, cast_fn,
                   stats: dict | None = None) -> list | None:
    """Return the mapped detail array for one record, or None if absent.

    Each JSON item becomes ``{t: <iso>, <mapped fields...>}`` where ``t`` is
    derived from the item's epoch-ms ``time_key`` (rounded down to the
    second, so sub-second samples can share a ``t``). Items that repeat an
    earlier one exactly (same epoch-ms and values) are dropped and counted
    in ``stats['duplicates_dropped']``.

    The whole detail array belongs to a parent record that already passed
    the window filter, so items are not re-filtered here (a session may
    legitimately start just before local midnight).
    """
    data = load_json(export_dir, binning.dir_suffix, ref_value)
    if not isinstance(data, list):
        return None

    out = []
    for item in data:
        if not isinstance(item, dict):
            continue
        rec: dict = {}
        ms = item.get(binning.time_key)
        sort_key = ms if isinstance(ms, (int, float)) else 0
        if isinstance(ms, (int, float)) and ms > 0:
            rec['t'] = timeutil.epoch_ms_to_iso(int(ms), offset_str)
        mapped = 0
        for fld in binning.fields:
            if fld.raw in item:
                val = cast_fn(item.get(fld.raw), fld.cast)
                if val is not None:
                    rec[fld.out_name()] = val
                    mapped += 1
        if mapped:              # skip timestamp-only points (no measurement)
            out.append((sort_key, rec))
    out.sort(key=lambda x: x[0])        # chronological order
    seen = set()
    result = []
    for ms, rec in out:
        key = (ms, tuple(rec.items()))
        if key in seen:
            if stats is not None:
                stats['duplicates_dropped'] = stats.get(
                    'duplicates_dropped', 0) + 1
            continue
        seen.add(key)
        result.append(rec)
    return result or None
