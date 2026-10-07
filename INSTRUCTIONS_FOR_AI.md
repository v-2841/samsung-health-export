# How to read this Samsung Health export (instructions for an AI assistant)

You have been given a single JSON file named like
`health_export_2026-07-09_to_2026-07-22.json`. It was produced from a **Samsung
Health** export (Galaxy Watch + phone) and is meant to help a **doctor** review a
patient's recent health data, with you assisting the analysis.

Read this document first, then the file's own embedded `legend`. Everything you
need to interpret the data is inside the file — this note explains the shape and
the pitfalls.

---

## 1. Top-level structure

```
{
  "metadata":          { tool version, the day window, offsets, data cutoff }
  "patient_profile":   { sex, birth year, age, height, latest weight, BMI, country, unit prefs }
  "legend":            { notes, enums (code tables), sections (per-field units & caveats) }
  "coverage_manifest": { EVERY datatype and file kind in the source and what happened to it }
  "data":              { the actual measurements, grouped by clinical category }
}
```

`data` categories: `cardiovascular`, `respiratory`, `body`, `sleep`, `activity`,
`stress`, `readiness`, `mental`, `exercise`, `nutrition`.

`legend.sections["<category>.<section>"]` describes one array under `data`:
its description, caveat, time convention, and for every field the `unit`, the
code table (`codes`) and an interpretation `note`. Nested arrays (per-minute
detail etc.) are described under `nested`.

## 2. The most important rule: absence ≠ normal

The file contains only data whose **local calendar date** falls inside the
window in `metadata.window` (except `patient_profile`, which reports the latest
known height/weight regardless of date).

Before concluding anything about a metric, **check `coverage_manifest`**:

- `status: "included"` with `rows_in_window > 0` → data is present for the window.
- `status: "included"` with `rows_in_window: 0` → the metric exists in the
  source, **but not in this window**. `first_record` / `last_record` show when it
  was recorded. Treat these as *"not measured in this period"*, **never** as
  *"normal"* — e.g. the watch may simply not have been worn.
- `status: "included_header"` → the profile, emitted as `patient_profile`.
- `status: "consumed"` → merged into another section (named in `note`).
- `status: "excluded"` → intentionally left out (privacy or non-medical config),
  with a `reason`. Not a data gap.
- `status: "UNKNOWN"` → a datatype the exporter didn't recognise; mention it.
- `status: "missing_from_export"` → expected by the tool but absent in the source.
- `companion_files` → every high-resolution file kind next to a table, with
  `consumed` / `excluded` (+ reason) / `UNKNOWN`.

`rows_in_window` is the number of records in `data`. Where the source had more
rows than were emitted (one row per day was kept), `source_rows_in_window`
shows the raw count.

## 3. Time

- All timestamps are **ISO-8601 with the local UTC offset**, e.g.
  `2026-07-13T01:20:00+04:00` — the local wall-clock time the patient
  experienced. The offset can change when the patient travels;
  `metadata.window.offsets_in_window` lists the offsets and their dates.
- Daily aggregates use `"day": "YYYY-MM-DD"` (a local calendar date).
- **The export day is usually incomplete.** If `metadata.window.end_day_partial`
  is `true`, the last day's totals stop at `metadata.window.data_cutoff`; those
  rows carry `partial_day: true`. Never read a partial day as a low-activity day.
- High-resolution series live in nested arrays — `detail`, `live_data`,
  `recovery_samples`, `detail_10min` — where each point has `"t"` (local time).
  `hypnogram` items have `start` / `end`. `detail_10min` points carry the day's
  offset when Samsung stored one, otherwise a local time without offset.

## 4. Units and codes

Units are in `legend.sections[...].fields[...].unit` and usually in the field
name. Do not guess — consult the legend. A few to remember:

- Durations are in **milliseconds** unless the name says otherwise:
  `_s` = seconds (`time_below_90pct_s`, `duration_s`), `_min` = minutes.
- Blood glucose is in **mmol/L** (regardless of the display preference in
  `patient_profile.unit_preferences`).
- Nutrition `calcium_pct_dv`, `iron_pct_dv`, `vitamin_*_pct_dv` are **% of the
  daily value**, not milligrams.
- Coded values are decoded to labels; the code tables are in `legend.enums`.
  An unknown code is passed through as `"<table>_<code>"`.

## 5. Missing values and placeholders

- Missing fields are omitted.
- Samsung's `-1` / `-1.0` means "not available" and is always removed.
- Fields where Samsung writes `0` as a placeholder have it converted to null;
  they are marked `zero_is_null: true` in `legend.sections`, e.g. blood-pressure
  `mean_arterial_pressure`, sleep efficiency of unstaged sessions.
  **Every other 0 is a real value.**
- Day rows with `no_movement_recorded: true` (activity/calories) have every
  movement field at 0 — usually no device was tracking (e.g. before tracking
  started); they are not truly immobile days.
- Exact duplicate detail points are dropped; the manifest reports
  `duplicate_detail_points_dropped`. Sub-second samples can share the same `t`.
- **Stress 0 is a real, very low reading** — Samsung itself averages zero
  minutes into the hourly score. Do not discard zeros.

## 6. Per-category notes

- **cardiovascular.heart_rate** — `kind: hourly_summary` rows (`heart_rate`,
  `heart_rate_min`, `heart_rate_max`) with per-minute `detail`, plus
  `kind: spot_reading` one-off measurements. Good for resting/nocturnal HR.
- **cardiovascular.hrv** — HRV values (`sdnn`, `rmssd`, ms) live **only** in the
  `detail` array; the parent row is just a time span.
- **respiratory.oxygen_saturation** — `kind: sleep_session` rows with per-minute
  `detail` (`irregular: 1` = minute flagged by Samsung) and
  `time_below_90pct_s` (seconds below 90 %); `kind: spot_reading` single values.
- **sleep.sessions** — one object per session: `wake_date`, `sleep_start` /
  `sleep_end`, scores (with sub-scores on newer app versions), stage minutes
  `deep_min` / `light_min` / `rem_min` / `awake_min`, and a `hypnogram`.
  `sleep_duration_min` **includes awake minutes**. `staged: false` = no stage
  analysis. `is_nap` marks naps. Sessions with `merged_into_combined: true` are
  segments of one night that also appears in **sleep.combined** — never add
  both. **sleep.naps** gives the vitality score before/after a nap.
- **stress.hourly** — Samsung's proprietary 0–100 stress score (hourly + minute
  `detail`); `stress.alerts` are high-stress event markers.
- **readiness.vitality** — Samsung's daily readiness score (`day` = date of
  waking) fusing sleeping HR/HRV, sleep and activity. It also carries the
  patient's own **baseline ranges** (`sleeping_hr_baseline_min/max`,
  `sleeping_hrv_baseline_min/max`) — compare values against them.
- **mental.mood** — self-reported mood (free-text notes are not exported);
  `mental.breathing_sessions` are guided-breathing exercises.
- **exercise.sessions** — workouts and walks with type, `source`, `device`,
  duration, distance, HR, VO₂max, cadence, `resting_hr`, `running_dynamics`
  (Myotest) and `live_data` (mostly HR samples). `source: auto_detected` are
  walks the phone/watch logged by itself — **not deliberate training**.
  **GPS routes were removed for privacy.** `recovery_heart_rate` rows link to
  their workout via `exercise_start_time`.
- **activity** — `daily_steps` is the **canonical daily total** (one row per
  day, Samsung's merge of all devices) with `detail_10min` bins over the whole
  history; `steps_daily_trend` is a cross-check of the same totals.
  `steps_intraday` is the per-minute log **per device** (`device: phone/watch`
  overlap — never sum across devices) and exists only for recent weeks.
  `activity_daily`, `calories_daily`, `floors_daily` are one row per day;
  `movement_intraday` is per-minute movement intensity.

## 7. Clinical caveats

- This is **consumer wearable data**, not medical-grade instrumentation. HR,
  SpO₂, skin temperature, respiratory rate and sleep staging are
  wrist-optical/estimated.
- `stress`, `vitality`, `heart_health_score`, sleep scores and
  `mental_recovery`/`physical_recovery` are **proprietary Samsung scores**, not
  validated clinical indices — describe them as trends, not diagnoses.
- Blood pressure, blood glucose and nutrition are manual/occasional entries and
  may be old (see `coverage_manifest`).
- Flag anything clinically notable, but recommend confirmation with standard
  clinical measurements. Do not provide a diagnosis; support the doctor's review.

## 8. Suggested approach

1. Read `metadata` (window, partial last day, offsets), `patient_profile`, and
   the `coverage_manifest` summary.
2. State plainly what **is** and **is not** covered in this window.
3. Summarise each present category with ranges/trends and units, excluding the
   partial last day from daily averages.
4. Call out anomalies (e.g. nocturnal SpO₂ dips and `time_below_90pct_s`,
   sleeping HR/HRV outside the personal baseline, poor sleep efficiency, high
   stress load) as observations for the doctor to verify.
