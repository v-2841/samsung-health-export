"""Turn CSV tables into clean, window-filtered record lists.

Most datatypes go through :meth:`Extractor.generic`. A few need cross-table
logic and get a dedicated handler (``sleep`` joins the hypnogram, ``food_intake``
resolves names, ``step_daily_trend`` dedupes per day, ``user_profile`` builds
the patient header).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date

from . import binning as binning_mod
from . import enums, timeutil
from .csvio import Row, Table, csv_path, iter_json_shard_path, read_table
from .registry import Datatype


@dataclass
class Context:
    export_dir: str
    timecode: str
    window: timeutil.Window
    primary_offset: str
    anchor_date: date


@dataclass
class Result:
    payload: object                 # list of records, or dict (profile)
    rows_total: int = 0
    rows_in_window: int = 0
    detail_items: int = 0
    last_record: str | None = None  # ISO date of newest record (ignoring the window)


_SENTINEL_NUMERIC = {"", "-1", "-1.0"}


def cast_value(value, kind: str):
    if value is None:
        return None
    if kind.startswith("enum:"):
        return enums.decode(enums.ALL.get(kind[5:], {}), value, kind[5:])
    if kind == "str" or kind == "raw":
        return value if value != "" else None
    if value in _SENTINEL_NUMERIC:
        return None
    try:
        if kind in ("int", "posint"):
            v = int(float(value))
            return v if (kind == "int" or v > 0) else None
        if kind == "ms":
            v = int(float(value))
            return v if v >= 0 else None
        v = float(value)             # float / posfloat / default
        if kind == "posfloat":
            return v if v > 0 else None
        return v
    except (TypeError, ValueError):
        return None                  # a "numeric" field is always numeric-or-null


class Extractor:
    def __init__(self, ctx: Context):
        self.ctx = ctx
        self._cache: dict[str, Table] = {}

    # -- helpers ---------------------------------------------------------
    def table(self, datatype: str, prefix: str = "") -> Table | None:
        if datatype not in self._cache:
            path = csv_path(self.ctx.export_dir, datatype, self.ctx.timecode)
            self._cache[datatype] = read_table(path, prefix) if path else None
        return self._cache[datatype]

    def _offset(self, dt: Datatype, row: Row) -> str:
        """Row's UTC offset, falling back to the export's primary offset if empty/absent."""
        if dt.offset_col:
            return row.get(dt.offset_col) or self.ctx.primary_offset
        return self.ctx.primary_offset

    def _local_date_and_iso(self, dt: Datatype, row: Row):
        """Return (local_date, start_iso, end_iso) for a row, honouring time_kind."""
        if dt.time_kind == "day_time":
            d = timeutil.parse_day_time(row.get(dt.time_col))
            return d, (d.isoformat() if d else None), None
        offset = self._offset(dt, row)
        start = row.get(dt.time_col)
        d = timeutil.utc_string_to_local_date(start, offset)
        start_iso = timeutil.utc_string_to_iso(start, offset)
        end_iso = timeutil.utc_string_to_iso(row.get(dt.end_col), offset) if dt.end_col else None
        return d, start_iso, end_iso

    def _map_fields(self, dt: Datatype, row: Row) -> dict:
        out = {}
        for fld in dt.fields:
            v = cast_value(row.get(fld.raw), fld.cast)
            if v is not None:
                out[fld.out_name()] = v
        return out

    def _base_record(self, dt: Datatype, row: Row, local_date, start_iso, end_iso) -> dict:
        rec: dict = {}
        if dt.time_kind == "day_time":
            rec["day"] = start_iso
        else:
            if start_iso:
                rec["start_time"] = start_iso
            if end_iso:
                rec["end_time"] = end_iso
        rec.update(self._map_fields(dt, row))
        return rec

    def _attach_detail(self, dt: Datatype, row: Row, rec: dict, offset: str | None) -> int:
        if not dt.binning:
            return 0
        detail = binning_mod.extract_detail(
            self.ctx.export_dir, dt.binning, row.get(dt.binning.ref), offset, cast_value)
        if detail:
            rec[dt.binning.out] = detail
            return len(detail)
        return 0

    # -- dispatch --------------------------------------------------------
    def run(self, dt: Datatype) -> Result:
        return getattr(self, dt.handler)(dt)

    # -- generic ---------------------------------------------------------
    def generic(self, dt: Datatype) -> Result:
        table = self.table(dt.id, dt.prefix)
        res = Result(payload=[])
        if not table:
            return res
        newest: date | None = None
        for row in table.rows:
            res.rows_total += 1
            local_date, start_iso, end_iso = self._local_date_and_iso(dt, row)
            if local_date and (newest is None or local_date > newest):
                newest = local_date
            if not self.ctx.window.contains(local_date):
                continue
            res.rows_in_window += 1
            rec = self._base_record(dt, row, local_date, start_iso, end_iso)
            offset = self._offset(dt, row)
            res.detail_items += self._attach_detail(dt, row, rec, offset)
            res.payload.append(rec)
        res.last_record = newest.isoformat() if newest else None
        return res

    # -- sleep (join hypnogram) -----------------------------------------
    def sleep(self, dt: Datatype) -> Result:
        table = self.table(dt.id, dt.prefix)
        res = Result(payload=[])
        if not table:
            return res
        hypno = self._hypnograms()
        newest: date | None = None
        for row in table.rows:
            res.rows_total += 1
            offset = self._offset(dt, row)
            start = row.get(dt.time_col)
            end = row.get(dt.end_col)
            start_date = timeutil.utc_string_to_local_date(start, offset)
            end_date = timeutil.utc_string_to_local_date(end, offset)
            night = start_date or end_date
            if night and (newest is None or night > newest):
                newest = night
            # a night is in scope if either its bedtime or wake time lands in the window
            if not (self.ctx.window.contains(start_date) or self.ctx.window.contains(end_date)):
                continue
            res.rows_in_window += 1
            rec = {"night_of": night.isoformat() if night else None,
                   "sleep_start": timeutil.utc_string_to_iso(start, offset),
                   "sleep_end": timeutil.utc_string_to_iso(end, offset)}
            rec.update(self._map_fields(dt, row))
            sid = row.get("datauuid")
            stages = hypno.get(sid)
            if stages:
                rec["hypnogram"] = stages
                res.detail_items += len(stages)
            res.payload.append(rec)
        res.last_record = newest.isoformat() if newest else None
        return res

    def _hypnograms(self) -> dict[str, list]:
        table = self.table("com.samsung.health.sleep_stage")
        out: dict[str, list] = {}
        if not table:
            return out
        for row in table.rows:
            sid = row.get("sleep_id")
            if not sid:
                continue
            offset = row.get("time_offset")
            start = row.get("start_time")
            ms = timeutil.parse_utc_string(start)
            out.setdefault(sid, []).append({
                "_sort": ms.timestamp() if ms else 0,
                "stage": enums.decode(enums.SLEEP_STAGE, row.get("stage"), "stage"),
                "start": timeutil.utc_string_to_iso(start, offset),
                "end": timeutil.utc_string_to_iso(row.get("end_time"), offset),
            })
        for sid, stages in out.items():
            stages.sort(key=lambda s: s.pop("_sort"))
        return out

    # -- recovery heart rate (flatten chart_data curve) -----------------
    def recovery_hr(self, dt: Datatype) -> Result:
        table = self.table(dt.id, dt.prefix)
        res = Result(payload=[])
        if not table:
            return res
        newest: date | None = None
        for row in table.rows:
            res.rows_total += 1
            offset = self._offset(dt, row)
            start = row.get(dt.time_col)
            local_date = timeutil.utc_string_to_local_date(start, offset)
            if local_date and (newest is None or local_date > newest):
                newest = local_date
            if not self.ctx.window.contains(local_date):
                continue
            res.rows_in_window += 1
            rec = {"start_time": timeutil.utc_string_to_iso(start, offset),
                   "end_time": timeutil.utc_string_to_iso(row.get(dt.end_col), offset)}
            samples = self._recovery_samples(dt, row.get(dt.binning.ref), offset)
            if samples:
                rec["recovery_samples"] = samples
                res.detail_items += len(samples)
            res.payload.append(rec)
        res.last_record = newest.isoformat() if newest else None
        return res

    def _recovery_samples(self, dt: Datatype, ref: str, offset: str | None) -> list:
        path = iter_json_shard_path(self.ctx.export_dir, dt.binning.dir_suffix, ref)
        if not path:
            return []
        try:
            with open(path, encoding="utf-8-sig") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return []
        blocks = data if isinstance(data, list) else [data]
        out = []
        for block in blocks:
            if not isinstance(block, dict):
                continue
            for pt in block.get("chart_data", []):
                if not isinstance(pt, dict):
                    continue
                ms = pt.get("start_time")
                out.append({
                    "t": timeutil.epoch_ms_to_iso(int(ms), offset) if isinstance(ms, (int, float)) and ms > 0 else None,
                    "elapsed_ms": pt.get("elapsed_time"),
                    "hr": cast_value(pt.get("heart_rate"), "float"),
                })
        return out

    # -- food intake (resolve names) ------------------------------------
    def food_intake(self, dt: Datatype) -> Result:
        names = self._food_names()
        table = self.table(dt.id, dt.prefix)
        res = Result(payload=[])
        if not table:
            return res
        newest: date | None = None
        for row in table.rows:
            res.rows_total += 1
            offset = self._offset(dt, row)
            local_date = timeutil.utc_string_to_local_date(row.get(dt.time_col), offset)
            if local_date and (newest is None or local_date > newest):
                newest = local_date
            if not self.ctx.window.contains(local_date):
                continue
            res.rows_in_window += 1
            rec = {"start_time": timeutil.utc_string_to_iso(row.get(dt.time_col), offset)}
            rec.update(self._map_fields(dt, row))
            if not rec.get("food_name"):
                resolved = names.get(row.get("food_info_id"))
                if resolved:
                    rec["food_name"] = resolved
            res.payload.append(rec)
        res.last_record = newest.isoformat() if newest else None
        return res

    def _food_names(self) -> dict[str, str]:
        table = self.table("com.samsung.health.food_info")
        if not table:
            return {}
        return {row.get("datauuid"): row.get("name") for row in table.rows if row.get("name")}

    # -- step daily trend (dedupe per day) ------------------------------
    def step_daily_trend(self, dt: Datatype) -> Result:
        table = self.table(dt.id, dt.prefix)
        res = Result(payload=[])
        if not table:
            return res
        best: dict[str, dict] = {}
        newest: date | None = None
        for row in table.rows:
            res.rows_total += 1
            d = timeutil.parse_day_time(row.get(dt.time_col))
            if d and (newest is None or d > newest):
                newest = d
            if not self.ctx.window.contains(d):
                continue
            res.rows_in_window += 1        # true raw in-window row count (before dedup)
            day = d.isoformat()
            rec = self._base_record(dt, row, d, day, None)
            steps = rec.get("steps") or 0
            # keep the row with the most steps for each calendar day
            if day not in best or steps > (best[day].get("steps") or 0):
                best[day] = rec
        res.payload = [best[k] for k in sorted(best)]
        res.last_record = newest.isoformat() if newest else None
        return res

    # -- user profile (patient header) ----------------------------------
    def user_profile(self, dt: Datatype) -> Result:
        table = self.table(dt.id)
        res = Result(payload={})
        if not table:
            return res
        kv: dict[str, str] = {}
        for row in table.rows:
            key = row.get("key")
            if not key:
                continue
            val = (row.get("text_value") or row.get("float_value") or row.get("long_value")
                   or row.get("int_value") or row.get("double_value"))
            if val:
                kv[key] = val
        res.rows_total = len(kv)

        profile: dict = {}
        if kv.get("gender"):
            profile["sex"] = kv["gender"]
        birth = kv.get("birth_date")
        if birth and len(birth) >= 4 and birth[:4].isdigit():
            by = int(birth[:4])
            profile["birth_year"] = by
            profile["age_years"] = self._age(birth)
        height = self._latest_numeric("com.samsung.health.height", "height") or _to_float(kv.get("height"))
        if height:
            profile["height_cm"] = round(height, 1)
        weight, weight_date = self._latest_weight()
        if weight:
            profile["latest_weight_kg"] = round(weight, 1)
            profile["latest_weight_date"] = weight_date
            if height:
                profile["bmi"] = round(weight / ((height / 100.0) ** 2), 1)
        profile["unit_preferences"] = {
            "weight": kv.get("weight_unit"), "height": kv.get("height_unit"),
            "distance": kv.get("distance_unit"), "temperature": kv.get("temperature_unit"),
            "blood_glucose": kv.get("blood_glucose_unit"), "blood_pressure": kv.get("blood_pressure_unit"),
            "water": kv.get("water_unit"),
        }
        if kv.get("country"):
            profile["country"] = kv["country"]
        profile["_note"] = ("Direct identifiers (name, social id, profile image, device ids) "
                            "were intentionally excluded. Height/weight/BMI are the latest known "
                            "values regardless of the day window.")
        res.payload = profile
        return res

    def _age(self, birth: str) -> int | None:
        try:
            by, bm, bd = int(birth[:4]), int(birth[4:6]), int(birth[6:8])
        except (ValueError, IndexError):
            return None
        a = self.ctx.anchor_date
        return a.year - by - ((a.month, a.day) < (bm, bd))

    def _latest_numeric(self, datatype: str, col: str) -> float | None:
        table = self.table(datatype)
        if not table:
            return None
        best_v, best_t = None, None
        for row in table.rows:
            t = timeutil.parse_utc_string(row.get("start_time"))
            v = _to_float(row.get(col))
            if v is not None and (best_t is None or (t and t > best_t)):
                best_v, best_t = v, t
        return best_v

    def _latest_weight(self):
        table = self.table("com.samsung.health.weight")
        if not table:
            return None, None
        best_v, best_t = None, None
        for row in table.rows:
            t = timeutil.parse_utc_string(row.get("start_time"))
            v = _to_float(row.get("weight"))
            if v is not None and (best_t is None or (t and t > best_t)):
                best_v, best_t = v, t
        return best_v, (best_t.date().isoformat() if best_t else None)


def _to_float(v):
    if v in (None, "", "-1", "-1.0"):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
