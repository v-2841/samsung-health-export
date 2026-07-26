"""Load and map the high-resolution binning JSON referenced by a CSV row."""

from __future__ import annotations

import json

from . import timeutil
from .csvio import iter_json_shard_path
from .registry import Binning


def _load(export_dir: str, binning: Binning, ref_value: str):
    path = iter_json_shard_path(export_dir, binning.dir_suffix, ref_value)
    if not path:
        return None
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def extract_detail(export_dir: str, binning: Binning, ref_value: str,
                   offset_str: str | None, cast_fn) -> list | None:
    """Return the mapped detail array for one record, or None if absent.

    * ``passthrough`` bindings return the parsed JSON as-is (used for
      recovery-HR curves whose shape we do not remap).
    * Otherwise each JSON item becomes ``{t: <iso>, <mapped fields...>}`` where
      ``t`` is derived from the item's epoch-ms ``time_key``.

    The whole detail array belongs to a parent record that already passed the
    window filter, so items are not re-filtered here (a session may legitimately
    start just before local midnight).
    """
    data = _load(export_dir, binning, ref_value)
    if data is None:
        return None
    if binning.passthrough:
        return data if isinstance(data, list) else [data]
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
            rec["t"] = timeutil.epoch_ms_to_iso(int(ms), offset_str)
        mapped = 0
        for fld in binning.fields:
            if fld.raw in item:
                val = cast_fn(item.get(fld.raw), fld.cast)
                if val is not None:
                    rec[fld.out_name()] = val
                    mapped += 1
        if mapped:                       # skip timestamp-only points with no measurement
            out.append((sort_key, rec))
    out.sort(key=lambda x: x[0])         # chronological order for readability
    return [rec for _, rec in out] or None
