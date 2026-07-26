"""Build the self-describing legend embedded in the output file.

The legend documents units per field, decodes every enum, and lists the
interpretation caveats (timestamps, sentinels) so the file is readable even if
the companion INSTRUCTIONS_FOR_AI.md is separated from it.
"""

from __future__ import annotations

from . import enums
from .registry import INCLUDED


def build() -> dict:
    fields: dict[str, dict] = {}
    for dt in INCLUDED:
        if not dt.fields and not dt.binning:
            continue
        section = f"{dt.category}.{dt.subkey}" if dt.subkey else dt.category
        units: dict[str, str] = {}
        for fld in dt.fields:
            if fld.unit:
                units[fld.out_name()] = fld.unit
        if dt.binning:
            for fld in dt.binning.fields:
                if fld.unit:
                    units[fld.out_name()] = fld.unit
        if units:
            fields[section] = units

    return {
        "notes": [
            "Timestamps are ISO-8601 with the local UTC offset (e.g. 2026-07-20T21:00:00+04:00). "
            "In the source CSV the wall-clock string is UTC; here it has already been shifted to "
            "the local time the user experienced.",
            "Daily records use a 'day' field (calendar date, local) instead of start/end times.",
            "High-resolution series are nested under a 'detail' array (or 'live_data', "
            "'recovery_samples', 'hypnogram'); each detail point has 't' = local ISO timestamp.",
            "Missing / not-available values were dropped or set to null. Source sentinels -1 and "
            "-1.0 mean 'not available'; a stress score of 0 means 'no valid reading'; "
            "longest_idle_time_ms of 86400000 means a full day with no data.",
            "Blood glucose values are stored in mmol/L regardless of the display unit preference.",
            "A record is placed in the window by its local calendar date. Sleep sessions are "
            "included if either bedtime or wake time falls in the window; 'night_of' is the "
            "date the user went to sleep.",
            "See coverage_manifest: 'rows_in_window' vs 'last_record' distinguishes 'no data in "
            "this period' from 'never recorded'. Do NOT read absence as normal.",
        ],
        "enums": enums.ALL,
        "units_by_section": fields,
    }
