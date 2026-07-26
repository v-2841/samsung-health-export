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
  "metadata":          { export info, the day window, units, language }
  "patient_profile":   { sex, age, height, latest weight, BMI, unit prefs }
  "legend":            { human notes, enum decodings, units per section }
  "coverage_manifest": { EVERY datatype in the source and what happened to it }
  "data":              { the actual measurements, grouped by clinical category }
}
```

`data` categories: `cardiovascular`, `respiratory`, `body`, `sleep`, `activity`,
`stress`, `readiness`, `mental`, `exercise`, `nutrition`.

## 2. The most important rule: absence ≠ normal

The file contains only data whose **local calendar date** falls inside the
window in `metadata.window` (except `patient_profile`, which reports the latest
known height/weight regardless of date).

Before concluding anything about a metric, **check `coverage_manifest`**:

- `status: "included"` with `rows_in_window > 0` → data is present for the window.
- `status: "included"` with `rows_in_window: 0` and a `last_record` date → the
  patient has this metric historically, **but not in this window**. For example
  blood pressure and blood glucose in this dataset were last recorded in
  January 2025. Treat these as *"not measured in this period"*, **never** as
  *"normal"*.
- `status: "excluded"` → intentionally left out (privacy or non-medical config),
  with a `reason`. Not a data gap.
- `status: "UNKNOWN"` → a datatype the exporter didn't recognise; mention it.

## 3. Timestamps

- All timestamps are **ISO-8601 with the local UTC offset**, e.g.
  `2026-07-13T01:20:00+04:00`. They already represent the **local wall-clock
  time the patient experienced** (the source stores UTC; the exporter shifted it
  using each record's offset).
- Daily aggregates use `"day": "YYYY-MM-DD"` (a local calendar date) instead of
  start/end times.
- High-resolution series live in nested arrays — `detail`, `live_data`,
  `recovery_samples`, `hypnogram` — where each point has `"t"` (local ISO time).

## 4. Units and codes

Units are documented in `legend.units_by_section` and inline in field names
(e.g. `distance_m`, `duration_ms`, `active_time_ms`, `calories_kcal`,
`sleeping_hrv` in ms). Do not guess — consult the legend. A few to remember:

- Durations are in **milliseconds** unless the field name says otherwise
  (`sleep_duration_min` is minutes; `active_time_ms` is milliseconds).
- Blood glucose is in **mmol/L** (regardless of the display preference in
  `patient_profile.unit_preferences`).
- Coded values are decoded to labels; the raw code tables are in `legend.enums`
  (sleep stages, meal types, exercise types, glucose meal context, mood).

## 5. Missing values and sentinels

- Missing fields are omitted or `null`.
- Source sentinels are cleaned: `-1` / `-1.0` mean "not available"; a stress
  `stress_score` of `0` means "no valid reading"; an `longest_idle_time_ms` of
  `86400000` (a full day) means "no data that day".

## 6. Per-category notes

- **cardiovascular.heart_rate** — hourly rows (`heart_rate`, `min`, `max`) each
  with per-minute `detail`. Good for resting/nocturnal HR and daytime range.
- **cardiovascular.hrv** — HRV values (`sdnn`, `rmssd`, ms) live **only** in the
  `detail` array; the parent row is just a time span.
- **respiratory.oxygen_saturation** — SpO₂ sessions with per-reading `detail`;
  nocturnal dips can matter clinically.
- **sleep.sessions** — one object per sleep session with `night_of`, scores,
  stage durations, and a full `hypnogram` (stage timeline). Sessions crossing
  midnight are included if either bedtime or wake time is in the window.
- **stress.hourly** — Samsung's proprietary 0–100 stress score (hourly + minute
  `detail`); `stress.alerts` are high-stress event markers.
- **readiness.vitality** — Samsung's daily "vitality/energy" score fusing
  sleeping HR (`sleeping_hr`), sleeping HRV (`sleeping_hrv`), sleep and activity.
- **mental.mood** — self-reported mood (sparse); `mental.breathing_sessions` are
  guided-breathing exercises.
- **exercise.sessions** — workouts (type, duration, distance, HR, VO₂max, cadence)
  with `live_data` (cadence/speed samples). **GPS routes were removed for privacy.**
- **activity** — `daily_steps` is the canonical per-day step count;
  `steps_intraday` is the per-minute step log; `movement_intraday` is per-minute
  movement intensity.

## 7. Clinical caveats

- This is **consumer wearable data**, not medical-grade instrumentation. HR, SpO₂,
  skin temperature, respiratory rate and sleep staging are wrist-optical/estimated.
- `stress`, `vitality`, sleep `mental_recovery`/`physical_recovery` are
  **proprietary Samsung scores**, not validated clinical indices — describe them
  as trends, not diagnoses.
- Blood pressure and blood glucose are manual/occasional entries and may be old
  (see `coverage_manifest`).
- Flag anything clinically notable, but recommend confirmation with standard
  clinical measurements. Do not provide a diagnosis; support the doctor's review.

## 8. Suggested approach

1. Read `metadata`, `patient_profile`, and the `coverage_manifest` summary.
2. State plainly what **is** and **is not** covered in this window.
3. Summarise each present category with ranges/trends and units.
4. Call out anomalies (e.g. nocturnal SpO₂ dips, elevated resting HR, poor sleep
   efficiency, high stress load) as observations for the doctor to verify.
