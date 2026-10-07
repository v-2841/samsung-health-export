"""Build the self-describing legend embedded in the output file.

The legend documents every section (description, caveat), every field (unit,
code table, interpretation note) and the general reading rules, so the file is
readable even if the companion INSTRUCTIONS_FOR_AI.md is separated from it.
"""

from __future__ import annotations

from . import enums
from .registry import INCLUDED, Field

NOTES = [
    "Timestamps are ISO-8601 with the local UTC offset (e.g. "
    "2026-07-20T21:00:00+04:00): the source stores UTC wall-clock strings, "
    "here they are already shifted to the local time the person "
    "experienced, using each record's own offset (travel is handled).",
    "Daily records use a 'day' field (local calendar date). The export "
    "day itself is usually incomplete: such rows carry partial_day=true "
    "and metadata.window.end_day_partial says so — never read a partial "
    "day as a low-activity day.",
    "Nested arrays: detail / live_data / recovery_samples / detail_10min "
    "points have 't' (local time); hypnogram items have start/end. "
    "daily_steps[].detail_10min uses the day's offset when Samsung stored "
    "one, otherwise local wall-clock time without an offset.",
    "Missing values are omitted. Samsung's -1 / -1.0 always means 'not "
    "available'. Fields whose 0 is a placeholder are converted to null "
    "(marked zero_is_null in legend.sections); every other 0 is a real "
    "value. A stress score of 0 is a real, very low reading. Exact "
    "duplicate detail points are dropped (counted in the manifest).",
    "Daily tables hold ONE row per day: daily_steps (Samsung's merge of "
    "all devices — the canonical total), steps_daily_trend (cross-check), "
    "activity_daily, calories_daily, floors_daily. steps_intraday is per "
    "device (phone and watch overlap): never sum it across devices.",
    'exercise.sessions[].source separates deliberate workouts '
    '(user_started_workout) from walks the phone/watch logged on its own '
    '(auto_detected); do not count auto-detected walks as training.',
    'Sleep: wake_date = local date of waking; sleep_duration_min includes '
    'awake minutes; staged=false sessions have no stage data; is_nap marks '
    'naps; sessions with merged_into_combined=true are segments of a '
    'sleep.combined night — never add both.',
    'Blood glucose values are stored in mmol/L regardless of the display '
    'unit preference. Nutrition calcium/iron/vitamins are % of the daily '
    'value, not mg.',
    "See coverage_manifest: rows_in_window together with first_record / "
    "last_record distinguishes 'not measured in this period' from "
    "'never recorded'. Do NOT read absence as normal. companion_files "
    "lists every high-resolution file kind and whether it was used.",
]


def _describe(fld: Field) -> dict:
    out: dict = {}
    if fld.unit:
        out['unit'] = fld.unit
    if fld.cast.startswith('enum:'):
        out['codes'] = f'legend.enums.{fld.cast[5:]}'
    if fld.cast in ('posfloat', 'posint', 'kmh_to_mps'):
        out['zero_is_null'] = True
    if fld.note:
        out['note'] = fld.note
    return out


def build() -> dict:
    sections: dict[str, dict] = {}
    for dt in INCLUDED:
        if not dt.subkey:
            continue
        sec: dict = {'description': dt.friendly}
        if dt.note:
            sec['note'] = dt.note
        if dt.time_kind == 'day_time':
            sec['time'] = 'day (local date)'
        elif dt.id == 'com.samsung.shealth.sleep':
            sec['time'] = 'sleep_start / sleep_end (local ISO)'
        elif dt.end_col:
            sec['time'] = 'start_time / end_time (local ISO)'
        else:
            sec['time'] = 'start_time (local ISO)'
        fields = {f.out_name(): _describe(f) for f in dt.fields}
        fields.update({f.out_name(): _describe(f) for f in dt.extra})
        sec['fields'] = fields
        nested: dict = {}
        if dt.binning and dt.binning.fields:
            points = {'t': {'note': 'local time of the point'}}
            points.update({f.out_name(): _describe(f)
                           for f in dt.binning.fields})
            nested[dt.binning.out] = points
        for key, flds in dt.nested:
            nested[key] = {f.out_name(): _describe(f) for f in flds}
        if nested:
            sec['nested'] = nested
        sections[f'{dt.category}.{dt.subkey}'] = sec

    return {
        'notes': NOTES,
        'enums': enums.ALL,
        'sections': sections,
    }
