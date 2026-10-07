"""Self-checks: pure logic + an empirical timezone proof against real data.

Run via ``python3 export_health.py --selftest``. The empirical check
re-derives the "CSV strings are UTC" fact on every table with per-minute
detail: the first epoch-ms point of each row's JSON must fall within an
hour AFTER the row's CSV start string read as UTC — never hours before or
after, which is what a wrong timezone assumption would produce.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from . import enums, timeutil
from .binning import load_json
from .csvio import csv_path, read_table
from .discovery import Export
from .extract import cast_value

# (datatype, column prefix, binning column)
_TZ_TABLES = (
    ('com.samsung.shealth.tracker.heart_rate',
     'com.samsung.health.heart_rate.', 'binning_data'),
    ('com.samsung.health.hrv', '', 'binning_data'),
    ('com.samsung.shealth.stress', '', 'binning_data'),
    ('com.samsung.health.movement', '', 'binning_data'),
    ('com.samsung.shealth.tracker.oxygen_saturation',
     'com.samsung.health.oxygen_saturation.', 'binning'),
)


def _check(name: str, cond: bool, detail: str = '') -> bool:
    status = 'PASS' if cond else 'FAIL'
    print(f'  [{status}] {name}' + (f' — {detail}' if detail else ''))
    return cond


def unit_checks() -> bool:
    ok = True
    tz = timeutil.parse_offset('UTC+0400')
    ok &= _check('parse_offset UTC+0400', tz is not None
                 and tz.utcoffset(None).total_seconds() == 4 * 3600)
    ok &= _check('negative offset UTC-0500', timeutil.parse_offset(
        'UTC-0500').utcoffset(None).total_seconds() == -5 * 3600)
    ok &= _check('offset variants UTC+04:00 / UTC+4', all(
        timeutil.parse_offset(s) == tz for s in ('UTC+04:00', 'UTC+4')))
    ok &= _check('garbage offset rejected',
                 timeutil.parse_offset('XYZ') is None)

    iso = timeutil.utc_string_to_iso('2025-01-08 21:00:00.000', 'UTC+0400')
    ok &= _check('utc string -> local iso (+4h shift)',
                 iso == '2025-01-09T01:00:00+04:00', iso)
    d = timeutil.utc_string_to_local_date('2025-01-08 21:00:00.000',
                                          'UTC+0400')
    ok &= _check('local date crosses midnight', d == date(2025, 1, 9),
                 str(d))

    w = timeutil.Window.last_n_days(date(2026, 7, 22), 14)
    ok &= _check('window length inclusive',
                 w.start_date == date(2026, 7, 9)
                 and w.end_date == date(2026, 7, 22))
    ok &= _check('window contains/excludes',
                 w.contains(date(2026, 7, 10))
                 and not w.contains(date(2026, 7, 8)))

    ok &= _check('glucose codes follow the Samsung SDK',
                 enums.GLUCOSE_MEAL_TYPE['80001'] == 'fasting'
                 and enums.GLUCOSE_MEAL_TYPE['80011'] == 'before_meal')
    ok &= _check('-1 is null for every numeric cast', all(
        cast_value(v, k) is None for v in ('-1', '-1.0', -1)
        for k in ('int', 'float', 'posfloat', 'nonneg')))
    ok &= _check('0 placeholder -> null only for pos* casts',
                 cast_value('0.0', 'posfloat') is None
                 and cast_value('0.0', 'float') == 0.0)
    ok &= _check('enum "-1" (not defined) -> null',
                 cast_value('-1', 'enum:glucose_measurement_type') is None)
    return bool(ok)


def timezone_proof(export: Export) -> bool:
    ok = True
    for datatype, prefix, ref_col in _TZ_TABLES:
        path = csv_path(export.path, datatype, export.timecode)
        if not path:
            continue
        table = read_table(path, prefix)
        good = bad = 0
        for row in table.rows[:300]:
            start = timeutil.parse_utc_string(row.get('start_time'))
            data = load_json(export.path, datatype, row.get(ref_col))
            if not start or not isinstance(data, list):
                continue
            epochs = [e['start_time'] for e in data
                      if isinstance(e, dict)
                      and isinstance(e.get('start_time'), (int, float))]
            if not epochs:
                continue
            first = datetime.fromtimestamp(min(epochs) / 1000,
                                           tz=timezone.utc)
            lag_min = (first - start).total_seconds() / 60
            if 0 <= lag_min <= 60:
                good += 1
            else:
                bad += 1
        if good + bad == 0:
            continue
        short = datatype.rsplit('.', 1)[-1]
        ok &= _check(f'{short}: CSV start string is UTC',
                     bad == 0, f'{good} rows consistent, {bad} not')
    return bool(ok)


def units_proof(export: Export) -> bool:
    """10-minute step bins store speed in km/h: speed / (distance / time)
    must be ~3.6 — if Samsung ever switches to m/s this check fails."""
    datatype = 'com.samsung.shealth.tracker.pedometer_day_summary'
    path = csv_path(export.path, datatype, export.timecode)
    if not path:
        return True
    ratios = []
    for row in read_table(path).rows[:200]:
        data = load_json(export.path, datatype, row.get('binning_data'))
        for b in data if isinstance(data, list) else []:
            if not isinstance(b, dict):
                continue
            dist, act = b.get('mDistance'), b.get('mTotalActiveTime')
            speed = b.get('mSpeed')
            if dist and act and speed and dist > 0 and act > 0:
                ratios.append(speed / (dist / (act / 1000.0)))
    if not ratios:
        return True
    ratios.sort()
    median = ratios[len(ratios) // 2]
    return _check('step-bin speed is km/h (converted to m/s)',
                  3.4 <= median <= 3.8, f'median ratio {median:.3f}')


def run(export: Export | None) -> int:
    print('Unit checks:')
    ok = unit_checks()
    if export:
        print('Empirical checks (real data):')
        ok = timezone_proof(export) and ok
        ok = units_proof(export) and ok
    else:
        print('  (no export found — skipping empirical checks)')
    print('OK' if ok else 'FAILURES DETECTED')
    return 0 if ok else 1
