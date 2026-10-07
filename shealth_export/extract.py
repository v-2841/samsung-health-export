"""Turn CSV tables into clean, window-filtered record lists.

Most datatypes go through :meth:`Extractor.generic` (optionally with one row
per day via ``Datatype.dedup``). A few need cross-table logic and get a
dedicated handler: ``sleep`` (hypnogram, naps, merged nights),
``daily_steps`` (the all-devices row + 10-minute bins), ``exercise``
(resting HR, running dynamics), ``recovery_hr`` (link to the workout),
``food_intake`` (food names), ``step_daily_trend`` and ``user_profile``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import NamedTuple

from . import binning as binning_mod
from . import enums, timeutil
from .csvio import Row, Table, csv_path, read_table
from .registry import Datatype

# device_profile.device_group -> device class (ids never leave the tool)
_DEVICE_GROUP = {'0': 'combined', '360001': 'phone', '360003': 'watch'}

_EXERCISE = 'com.samsung.shealth.exercise'
_EXERCISE_PREFIX = 'com.samsung.health.exercise.'


@dataclass
class Context:
    export_dir: str
    timecode: str
    window: timeutil.Window
    primary_offset: str
    anchor_date: date
    export_date: date | None = None     # the day the export was taken
    # offset -> [first local date, last local date, rows] inside the window
    offsets: dict = field(default_factory=dict)
    cutoff: tuple | None = None         # (newest UTC instant, its offset)


@dataclass
class Result:
    payload: object                 # list of records, or dict (profile)
    rows_total: int = 0
    rows_in_window: int = 0         # records emitted
    source_rows_in_window: int = 0  # source rows in the window (pre-dedup)
    detail_items: int = 0
    first_record: str | None = None  # ISO date of the oldest record
    last_record: str | None = None   # ISO date of the newest record
    offset_assumed: int = 0          # rows whose UTC offset was guessed
    duplicates_dropped: int = 0      # exact duplicate detail points

    def note(self, d: date | None) -> None:
        if d is None:
            return
        s = d.isoformat()
        if self.first_record is None or s < self.first_record:
            self.first_record = s
        if self.last_record is None or s > self.last_record:
            self.last_record = s


class _Times(NamedTuple):
    start_date: date | None
    end_date: date | None
    start_iso: str | None
    end_iso: str | None
    offset: str | None
    instant: datetime | None        # newest UTC instant of the row


_SENTINELS = {'', '-1', '-1.0'}


def cast_value(value, kind: str):
    if value is None:
        return None
    if kind.startswith('enum:'):
        name = kind[5:]
        return enums.decode(enums.ALL.get(name, {}), value, name)
    if kind in ('str', 'raw'):
        return value if value != '' else None
    if isinstance(value, str):
        if value.strip() in _SENTINELS:
            return None
    elif value == -1:
        return None
    try:
        if kind in ('int', 'posint', 'nonneg'):
            v = int(float(value))
            if kind == 'posint' and v <= 0:
                return None
            if kind == 'nonneg' and v < 0:
                return None
            return v
        v = float(value)             # float / posfloat / default
        if kind == 'kmh_to_mps':
            return round(v / 3.6, 4) if v > 0 else None
        if kind == 'posfloat' and v <= 0:
            return None
        return v
    except (TypeError, ValueError):
        return None          # a "numeric" field is always numeric-or-null


def _to_float(v):
    if v in (None, '', '-1', '-1.0'):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class Extractor:
    def __init__(self, ctx: Context):
        self.ctx = ctx
        self._cache: dict[str, Table | None] = {}
        self._devices: dict[str, str] | None = None

    # -- helpers ---------------------------------------------------------
    def table(self, datatype: str, prefix: str = '') -> Table | None:
        if datatype not in self._cache:
            path = csv_path(self.ctx.export_dir, datatype, self.ctx.timecode)
            self._cache[datatype] = read_table(path, prefix) if path else None
        return self._cache[datatype]

    def device_of(self, uuid: str) -> str | None:
        """'phone' / 'watch' / 'combined' for a deviceuuid, else None."""
        if self._devices is None:
            self._devices = {}
            t = self.table('com.samsung.health.device_profile')
            for row in t.rows if t else []:
                group = row.get('device_group')
                self._devices[row.get('deviceuuid')] = _DEVICE_GROUP.get(
                    group, 'other')
        return self._devices.get(uuid)

    def _offset(self, dt: Datatype, row: Row, res: Result) -> str:
        """Row's UTC offset; the export's primary offset if empty/invalid."""
        raw = row.get(dt.offset_col) if dt.offset_col else ''
        if raw and timeutil.parse_offset(raw):
            return raw
        res.offset_assumed += 1
        return self.ctx.primary_offset

    def _times(self, dt: Datatype, row: Row, res: Result) -> _Times:
        if dt.time_kind == 'day_time':
            d = timeutil.parse_day_time(row.get(dt.time_col))
            return _Times(d, None, d.isoformat() if d else None, None,
                          None, None)
        offset = self._offset(dt, row, res)
        start = timeutil.parse_utc_string(row.get(dt.time_col))
        end = (timeutil.parse_utc_string(row.get(dt.end_col))
               if dt.end_col else None)
        tz = timeutil.parse_offset(offset)
        local_start = start.astimezone(tz).replace(microsecond=0) \
            if start else None
        local_end = end.astimezone(tz).replace(microsecond=0) \
            if end else None
        return _Times(
            local_start.date() if local_start else None,
            local_end.date() if local_end else None,
            local_start.isoformat() if local_start else None,
            local_end.isoformat() if local_end else None,
            offset, end or start)

    def _in_window(self, dt: Datatype, t: _Times, overlap=False) -> bool:
        w = self.ctx.window
        inside = w.contains(t.start_date) or (
            (overlap or dt.window_overlap) and w.contains(t.end_date))
        if inside and t.offset:
            d = t.start_date or t.end_date
            e = self.ctx.offsets.setdefault(t.offset, [d, d, 0])
            e[0], e[1], e[2] = min(e[0], d), max(e[1], d), e[2] + 1
            if t.instant and (self.ctx.cutoff is None
                              or t.instant > self.ctx.cutoff[0]):
                self.ctx.cutoff = (t.instant, t.offset)
        return inside

    def _map_fields(self, dt: Datatype, row: Row) -> dict:
        out = {}
        for fld in dt.fields:
            v = cast_value(row.get(fld.raw), fld.cast)
            if v is not None:
                out[fld.out_name()] = v
        return out

    def _record(self, dt: Datatype, row: Row, t: _Times) -> dict | None:
        rec: dict = {}
        if dt.time_kind == 'day_time':
            rec['day'] = t.start_iso
        else:
            if t.start_iso:
                rec['start_time'] = t.start_iso
            if t.end_iso:
                rec['end_time'] = t.end_iso
        if dt.device:
            dev = self.device_of(row.get('deviceuuid'))
            if dev:
                rec['device'] = dev
        mapped = self._map_fields(dt, row)
        if dt.skip_empty and not mapped:
            return None
        rec.update(mapped)
        if dt.zero_day_fields and not any(
                rec.get(name) for name in dt.zero_day_fields):
            rec['no_movement_recorded'] = True
        if (dt.time_kind == 'day_time' and t.start_date
                and t.start_date == self.ctx.export_date):
            rec['partial_day'] = True
        return rec

    def _attach_detail(self, dt: Datatype, row: Row, rec: dict,
                       offset: str | None, res: Result) -> None:
        if not dt.binning:
            return
        stats: dict = {}
        detail = binning_mod.extract_detail(
            self.ctx.export_dir, dt.binning, row.get(dt.binning.ref),
            offset, cast_value, stats)
        res.duplicates_dropped += stats.get('duplicates_dropped', 0)
        if detail:
            rec[dt.binning.out] = detail

    @staticmethod
    def _count(payload: list, *keys: str) -> int:
        return sum(len(r.get(k) or ()) for r in payload for k in keys)

    @staticmethod
    def _dedup_key(dt: Datatype, rec: dict, row: Row):
        name = dt.dedup.split(':', 1)[1]
        return (rec.get(name) or 0, row.get('update_time'))

    # -- dispatch --------------------------------------------------------
    def run(self, dt: Datatype) -> Result:
        return getattr(self, dt.handler)(dt)

    # -- generic ---------------------------------------------------------
    def generic(self, dt: Datatype, enrich=None) -> Result:
        table = self.table(dt.id, dt.prefix)
        res = Result(payload=[])
        if not table:
            return res
        best: dict[str, tuple] = {}
        for row in table.rows:
            res.rows_total += 1
            t = self._times(dt, row, res)
            res.note(t.start_date)
            if not self._in_window(dt, t):
                continue
            res.source_rows_in_window += 1
            rec = self._record(dt, row, t)
            if rec is None:
                continue
            if dt.dedup:
                key = self._dedup_key(dt, rec, row)
                if t.start_iso not in best or key > best[t.start_iso][0]:
                    best[t.start_iso] = (key, row, rec, t)
                continue
            self._finish(dt, row, rec, t, enrich, res)
            res.payload.append(rec)
        for day in sorted(best):
            _, row, rec, t = best[day]
            self._finish(dt, row, rec, t, enrich, res)
            res.payload.append(rec)
        res.rows_in_window = len(res.payload)
        if dt.binning:
            res.detail_items = self._count(res.payload, dt.binning.out)
        return res

    def _finish(self, dt, row, rec, t, enrich, res) -> None:
        if enrich:
            enrich(dt, row, rec, t)
        self._attach_detail(dt, row, rec, t.offset, res)

    # -- sleep (hypnogram, naps, merged nights) ---------------------------
    def sleep(self, dt: Datatype) -> Result:
        table = self.table(dt.id, dt.prefix)
        res = Result(payload=[])
        if not table:
            return res
        hypno = self._hypnograms()
        nap_starts = self._nap_starts()
        for row in table.rows:
            res.rows_total += 1
            t = self._times(dt, row, res)
            wake = t.end_date or t.start_date
            res.note(wake)
            # in scope if either bedtime or wake time lands in the window
            if not self._in_window(dt, t, overlap=True):
                continue
            res.source_rows_in_window += 1
            rec = {'wake_date': wake.isoformat() if wake else None,
                   'sleep_start': t.start_iso, 'sleep_end': t.end_iso}
            rec.update(self._map_fields(dt, row))
            stages = hypno.get(row.get('datauuid'))
            rec['staged'] = bool(stages)
            nap_score = cast_value(row.get('nap_score'), 'posint')
            if nap_score or row.get(dt.time_col) in nap_starts:
                rec['is_nap'] = True
            if row.get('combined_id'):
                rec['merged_into_combined'] = True
            if stages:
                rec['hypnogram'] = stages
            res.payload.append(rec)
        res.rows_in_window = len(res.payload)
        res.detail_items = self._count(res.payload, 'hypnogram')
        return res

    def _hypnograms(self) -> dict[str, list]:
        table = self.table('com.samsung.health.sleep_stage')
        out: dict[str, list] = {}
        if not table:
            return out
        for row in table.rows:
            sid = row.get('sleep_id')
            if not sid:
                continue
            offset = row.get('time_offset')
            if not timeutil.parse_offset(offset):
                offset = self.ctx.primary_offset
            start = row.get('start_time')
            ms = timeutil.parse_utc_string(start)
            out.setdefault(sid, []).append({
                '_sort': ms.timestamp() if ms else 0,
                'stage': enums.decode(enums.SLEEP_STAGE, row.get('stage'),
                                      'stage'),
                'start': timeutil.utc_string_to_iso(start, offset),
                'end': timeutil.utc_string_to_iso(row.get('end_time'),
                                                  offset),
            })
        for stages in out.values():
            stages.sort(key=lambda s: s.pop('_sort'))
        return out

    def _nap_starts(self) -> set[str]:
        table = self.table('com.samsung.shealth.vitality.nap_data')
        return {r.get('start_time') for r in table.rows} if table else set()

    # -- daily steps (all-devices row + 10-minute bins) ------------------
    def daily_steps(self, dt: Datatype) -> Result:
        table = self.table(dt.id, dt.prefix)
        res = Result(payload=[])
        if not table:
            return res
        best: dict[str, tuple] = {}
        for row in table.rows:
            res.rows_total += 1
            t = self._times(dt, row, res)
            res.note(t.start_date)
            if not self._in_window(dt, t):
                continue
            res.source_rows_in_window += 1
            merged = (self.device_of(row.get('deviceuuid')) == 'combined'
                      or bool(row.get('source_info')))
            key = (merged, _to_float(row.get('step_count')) or 0,
                   row.get('update_time'))
            if t.start_iso not in best or key > best[t.start_iso][0]:
                best[t.start_iso] = (key, row, t)
        for day in sorted(best):
            key, row, t = best[day]
            rec = self._record(dt, row, t)
            if not key[0]:
                rec['all_devices_merged'] = False
            bins = self._ten_minute_bins(dt, row, t.start_date)
            if bins:
                rec[dt.binning.out] = bins
            res.payload.append(rec)
        res.rows_in_window = len(res.payload)
        res.detail_items = self._count(res.payload, dt.binning.out)
        return res

    def _ten_minute_bins(self, dt: Datatype, row: Row, day: date) -> list:
        data = binning_mod.load_json(self.ctx.export_dir,
                                     dt.binning.dir_suffix,
                                     row.get(dt.binning.ref))
        if not isinstance(data, list) or not day:
            return []
        midnight = datetime.combine(day, time())
        unit_ms = 600000
        if data and isinstance(data[0], dict):
            unit_ms = data[0].get('mTimeUnit') or unit_ms
        tz = _bin_timezone(data, midnight, unit_ms)
        out = []
        for i, item in enumerate(data):
            if not isinstance(item, dict):
                continue
            rec = {}
            for fld in dt.binning.fields:
                v = cast_value(item.get(fld.raw), fld.cast)
                if v is not None:
                    rec[fld.out_name()] = v
            if not rec.get('steps'):
                continue
            start = midnight + timedelta(milliseconds=unit_ms * i)
            if tz:
                start = start.replace(tzinfo=tz)
            out.append({'t': start.isoformat(), **rec})
        return out

    # -- exercise (generic + resting HR + running dynamics) --------------
    def exercise(self, dt: Datatype) -> Result:
        return self.generic(dt, enrich=self._exercise_extras)

    def _exercise_extras(self, dt: Datatype, row: Row, rec: dict,
                         t: _Times) -> None:
        status = binning_mod.load_json(self.ctx.export_dir, _EXERCISE,
                                       row.get('sensing_status'))
        if isinstance(status, dict):
            hr = status.get('heart_rate')
            rhr = cast_value(hr.get('rhr'), 'posint') if isinstance(
                hr, dict) else None
            if rhr:
                rec['resting_hr'] = rhr
        dyn = _running_dynamics(binning_mod.load_json(
            self.ctx.export_dir, _EXERCISE, row.get('additional_internal')))
        if dyn:
            rec['running_dynamics'] = dyn

    # -- recovery heart rate (flatten chart_data curve) -----------------
    def recovery_hr(self, dt: Datatype) -> Result:
        table = self.table(dt.id, dt.prefix)
        res = Result(payload=[])
        if not table:
            return res
        workouts = self._workout_starts()
        for row in table.rows:
            res.rows_total += 1
            t = self._times(dt, row, res)
            res.note(t.start_date)
            if not self._in_window(dt, t):
                continue
            res.source_rows_in_window += 1
            rec = {'start_time': t.start_iso, 'end_time': t.end_iso}
            linked = workouts.get(row.get('exercise_id'))
            if linked:
                rec['exercise_start_time'] = linked
            samples = self._recovery_samples(dt, row.get(dt.binning.ref),
                                             t.offset)
            if samples:
                rec['recovery_samples'] = samples
            res.payload.append(rec)
        res.rows_in_window = len(res.payload)
        res.detail_items = self._count(res.payload, 'recovery_samples')
        return res

    def _workout_starts(self) -> dict[str, str]:
        table = self.table(_EXERCISE, _EXERCISE_PREFIX)
        out = {}
        for row in table.rows if table else []:
            offset = row.get('time_offset')
            if not timeutil.parse_offset(offset):
                offset = self.ctx.primary_offset
            iso = timeutil.utc_string_to_iso(row.get('start_time'), offset)
            if iso:
                out[row.get('datauuid')] = iso
        return out

    def _recovery_samples(self, dt: Datatype, ref: str,
                          offset: str | None) -> list:
        data = binning_mod.load_json(self.ctx.export_dir,
                                     dt.binning.dir_suffix, ref)
        blocks = data if isinstance(data, list) else [data]
        out = []
        for block in blocks:
            if not isinstance(block, dict):
                continue
            for pt in block.get('chart_data', []):
                if not isinstance(pt, dict):
                    continue
                ms = pt.get('start_time')
                ok = isinstance(ms, (int, float)) and ms > 0
                out.append({
                    't': timeutil.epoch_ms_to_iso(int(ms), offset)
                    if ok else None,
                    'elapsed_ms': pt.get('elapsed_time'),
                    'hr': cast_value(pt.get('heart_rate'), 'float'),
                })
        return out

    # -- food intake (resolve names) ------------------------------------
    def food_intake(self, dt: Datatype) -> Result:
        names = self._food_names()

        def enrich(dt, row, rec, t):
            if rec.get('food_name'):
                return
            food_id = row.get('food_info_id')
            resolved = names.get(food_id)
            if resolved:
                rec['food_name'] = resolved
            elif food_id.startswith('meal_'):
                rec['food_name'] = 'quick add (calories only)'

        return self.generic(dt, enrich=enrich)

    def _food_names(self) -> dict[str, str]:
        table = self.table('com.samsung.health.food_info')
        if not table:
            return {}
        return {row.get('datauuid'): row.get('name')
                for row in table.rows if row.get('name')}

    # -- step daily trend (the all-devices row per day) ------------------
    def step_daily_trend(self, dt: Datatype) -> Result:
        table = self.table(dt.id, dt.prefix)
        res = Result(payload=[])
        if not table:
            return res
        best: dict[str, tuple] = {}
        for row in table.rows:
            res.rows_total += 1
            t = self._times(dt, row, res)
            res.note(t.start_date)
            if not self._in_window(dt, t):
                continue
            res.source_rows_in_window += 1
            rec = self._record(dt, row, t)
            # prefer Samsung's all-devices row (-2), then the most steps
            key = (row.get('source_type') == '-2', rec.get('steps') or 0,
                   row.get('update_time'))
            if t.start_iso not in best or key > best[t.start_iso][0]:
                best[t.start_iso] = (key, rec)
        res.payload = [best[k][1] for k in sorted(best)]
        res.rows_in_window = len(res.payload)
        return res

    # -- user profile (patient header) ----------------------------------
    def user_profile(self, dt: Datatype) -> Result:
        table = self.table(dt.id)
        res = Result(payload={})
        if not table:
            return res
        kv: dict[str, str] = {}
        for row in table.rows:
            key = row.get('key')
            if not key:
                continue
            val = (row.get('text_value') or row.get('float_value')
                   or row.get('long_value') or row.get('int_value')
                   or row.get('double_value'))
            if val:
                kv[key] = val
        res.rows_total = len(kv)

        profile: dict = {}
        if kv.get('gender'):
            profile['sex'] = kv['gender']
        birth = kv.get('birth_date')
        if birth and len(birth) >= 4 and birth[:4].isdigit():
            profile['birth_year'] = int(birth[:4])
            profile['age_years'] = self._age(birth)
        height = (self._latest('com.samsung.health.height', 'height')[0]
                  or _to_float(kv.get('height')))
        if height:
            profile['height_cm'] = round(height, 1)
        weight, weight_date = self._latest('com.samsung.health.weight',
                                           'weight')
        if weight:
            profile['latest_weight_kg'] = round(weight, 1)
            profile['latest_weight_date'] = weight_date
            if height:
                profile['bmi'] = round(weight / ((height / 100.0) ** 2), 1)
        profile['unit_preferences'] = {
            'weight': kv.get('weight_unit'),
            'height': kv.get('height_unit'),
            'distance': kv.get('distance_unit'),
            'temperature': kv.get('temperature_unit'),
            'blood_glucose': kv.get('blood_glucose_unit'),
            'blood_pressure': kv.get('blood_pressure_unit'),
            'hba1c': kv.get('hba1c_unit'),
            'water': kv.get('water_unit'),
        }
        if kv.get('country'):
            profile['country'] = kv['country']
        profile['_note'] = (
            'Direct identifiers (name, social id, profile image, device '
            'ids) were intentionally excluded. Height/weight/BMI are the '
            'latest known values regardless of the day window.')
        res.payload = profile
        return res

    def _age(self, birth: str) -> int | None:
        try:
            by, bm, bd = int(birth[:4]), int(birth[4:6]), int(birth[6:8])
        except (ValueError, IndexError):
            return None
        a = self.ctx.anchor_date
        return a.year - by - ((a.month, a.day) < (bm, bd))

    def _latest(self, datatype: str, col: str):
        """(newest value, its local ISO date) of ``col`` in ``datatype``."""
        table = self.table(datatype)
        if not table:
            return None, None
        best_v, best_t, best_off = None, None, None
        for row in table.rows:
            t = timeutil.parse_utc_string(row.get('start_time'))
            v = _to_float(row.get(col))
            if v is not None and (best_t is None or (t and t > best_t)):
                best_v, best_t, best_off = v, t, row.get('time_offset')
        if best_t is None:
            return best_v, None
        tz = timeutil.parse_offset(best_off) or timeutil.parse_offset(
            self.ctx.primary_offset) or timezone.utc
        return best_v, best_t.astimezone(tz).date().isoformat()


def _bin_timezone(data: list, midnight: datetime, unit_ms: int):
    """The day's UTC offset, derived from the first bin with an epoch start.

    Bin ``i`` starts at local midnight + ``i`` units; when Samsung also
    stored the bin's absolute start, the difference is the day's offset.
    Returns None when no bin carries an epoch start.
    """
    for i, item in enumerate(data):
        ms = item.get('mStartTime') if isinstance(item, dict) else None
        if isinstance(ms, (int, float)) and ms > 0:
            utc = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
            local = midnight + timedelta(milliseconds=unit_ms * i)
            delta = local - utc.replace(tzinfo=None)
            minutes = round(delta.total_seconds() / 900) * 15
            if abs(minutes) <= 14 * 60:
                return timezone(timedelta(minutes=minutes))
            return None
    return None


def _running_dynamics(data) -> dict | None:
    """Per-metric summary of a Myotest ``additional_internal`` blob."""
    if not isinstance(data, dict):
        return None
    out = {}
    for block in data.get('data') or []:
        if not isinstance(block, dict):
            continue
        for metric in block.get('advanced_metrics') or []:
            if not isinstance(metric, dict) or not metric.get('data_type'):
                continue
            # the duration-0 point is a zero seed and score 3 marks
            # "no data" (value 0); neither is a measurement
            values = [p.get('value') for p in metric.get('chart_data') or []
                      if isinstance(p, dict) and p.get('duration')
                      and p.get('score') in (0, 1, 2)
                      and isinstance(p.get('value'), (int, float))]
            entry = {'overall_score': metric.get('overall_score'),
                     'score_ratio_pct': metric.get('score_ratio')}
            if values:
                entry['mean_value'] = round(sum(values) / len(values), 4)
                entry['samples'] = len(values)
            out[metric['data_type']] = entry
    return out or None
