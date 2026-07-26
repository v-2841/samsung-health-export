"""Declarative spec of what to export and how to map it.

Adding or changing a data type is a *data* edit here, not a code change: the
generic extractor in :mod:`extract` reads this registry and does the rest.
Privacy is enforced by construction — only the columns listed in ``fields``
are ever read, so device ids, Bluetooth addresses, GPS tracks, uuids and app
config simply never leave the CSV.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Field:
    raw: str                 # source column (short name; prefix is applied by the reader)
    name: str = ""           # output key (defaults to raw)
    unit: str = ""           # documented in the legend
    cast: str = "float"      # str | int | float | ms | raw | enum:<table>

    def out_name(self) -> str:
        return self.name or self.raw


@dataclass(frozen=True)
class Binning:
    ref: str                 # column holding "<uuid>.<...>.json"
    dir_suffix: str          # jsons/<dir_suffix>/...
    fields: tuple[Field, ...] = ()
    time_key: str = "start_time"   # epoch-ms key inside each json item
    passthrough: bool = False      # attach parsed json as-is (unknown/curve shapes)
    out: str = "detail"            # key the detail array is attached under


@dataclass(frozen=True)
class Datatype:
    id: str
    category: str
    subkey: str
    friendly: str
    time_col: str = "start_time"
    time_kind: str = "utc_string"   # utc_string | day_time
    offset_col: str = "time_offset"
    end_col: str = ""
    prefix: str = ""
    fields: tuple[Field, ...] = ()
    binning: Binning | None = None
    handler: str = "generic"        # generic | sleep | food_intake | step_daily_trend | user_profile


def F(raw, name="", unit="", cast="float") -> Field:
    return Field(raw, name, unit, cast)


# Column namespaces used by some tables.
_HR = "com.samsung.health.heart_rate."
_BP = "com.samsung.health.blood_pressure."
_SPO2 = "com.samsung.health.oxygen_saturation."
_BG = "com.samsung.health.blood_glucose."
_SLEEP = "com.samsung.health.sleep."
_EX = "com.samsung.health.exercise."
_STEP = "com.samsung.health.step_count."
_CAL = "com.samsung.shealth.calories_burned."


INCLUDED: tuple[Datatype, ...] = (
    # ------------------------------------------------------------------ cardio
    Datatype(
        id="com.samsung.shealth.tracker.heart_rate",
        category="cardiovascular", subkey="heart_rate",
        friendly="Heart rate (hourly summary + per-minute detail)",
        prefix=_HR, end_col="end_time",
        fields=(
            F("heart_rate", "heart_rate", "bpm"),
            F("min", "heart_rate_min", "bpm"),
            F("max", "heart_rate_max", "bpm"),
            F("heart_beat_count", "heart_beat_count", "count", "int"),
        ),
        binning=Binning(
            ref="binning_data", dir_suffix="com.samsung.shealth.tracker.heart_rate",
            fields=(F("heart_rate", "heart_rate", "bpm"),
                    F("heart_rate_min", "heart_rate_min", "bpm"),
                    F("heart_rate_max", "heart_rate_max", "bpm")),
        ),
    ),
    Datatype(
        id="com.samsung.health.hrv",
        category="cardiovascular", subkey="hrv",
        friendly="Heart-rate variability (values live only in the detail JSON)",
        end_col="end_time",
        fields=(),
        binning=Binning(
            ref="binning_data", dir_suffix="com.samsung.health.hrv",
            fields=(F("sdnn", "sdnn", "ms"), F("rmssd", "rmssd", "ms")),
        ),
    ),
    Datatype(
        id="com.samsung.shealth.blood_pressure",
        category="cardiovascular", subkey="blood_pressure",
        friendly="Blood pressure (cuff readings)",
        prefix=_BP,
        fields=(
            F("systolic", "systolic", "mmHg", "int"),
            F("diastolic", "diastolic", "mmHg", "int"),
            F("mean", "mean_arterial_pressure", "mmHg"),
            F("pulse", "pulse", "bpm", "int"),
            F("medication", "medication", "", "str"),
        ),
    ),
    # -------------------------------------------------------------- respiratory
    Datatype(
        id="com.samsung.shealth.tracker.oxygen_saturation",
        category="respiratory", subkey="oxygen_saturation",
        friendly="Blood oxygen (SpO2) spot & session readings",
        prefix=_SPO2, end_col="end_time",
        fields=(
            F("spo2", "spo2", "%"),
            F("min", "spo2_min", "%"),
            F("max", "spo2_max", "%"),
            F("heart_rate", "heart_rate", "bpm"),
            F("coverage_rate", "coverage_rate", "%"),
            F("low_duration", "low_duration_ms", "ms", "ms"),
        ),
        binning=Binning(
            ref="binning", dir_suffix="com.samsung.shealth.tracker.oxygen_saturation",
            fields=(F("spo2", "spo2", "%"), F("spo2_min", "spo2_min", "%"),
                    F("spo2_max", "spo2_max", "%")),
        ),
    ),
    Datatype(
        id="com.samsung.health.respiratory_rate",
        category="respiratory", subkey="respiratory_rate",
        friendly="Respiratory rate (breaths per minute)",
        end_col="end_time",
        fields=(
            F("average", "respiratory_rate_avg", "breaths/min", "posfloat"),
            F("lower_limit", "respiratory_rate_min", "breaths/min", "posfloat"),
            F("upper_limit", "respiratory_rate_max", "breaths/min", "posfloat"),
            F("is_outlier", "is_outlier", "", "int"),
        ),
        binning=Binning(
            ref="binning_data", dir_suffix="com.samsung.health.respiratory_rate",
            fields=(F("respiratory_rate", "respiratory_rate", "breaths/min", "posfloat"),),
        ),
    ),
    # ---------------------------------------------------------- body measurement
    Datatype(
        id="com.samsung.health.weight",
        category="body", subkey="weight",
        friendly="Weight & body composition",
        fields=(
            F("weight", "weight", "kg"),
            F("body_fat", "body_fat_pct", "%"),
            F("body_fat_mass", "body_fat_mass", "kg"),
            F("muscle_mass", "muscle_mass", "kg"),
            F("skeletal_muscle_mass", "skeletal_muscle_mass", "kg"),
            F("skeletal_muscle", "skeletal_muscle_pct", "%"),
            F("basal_metabolic_rate", "bmr", "kcal"),
            F("total_body_water", "total_body_water", "kg"),
            F("fat_free_mass", "fat_free_mass", "kg"),
            F("fat_free", "fat_free_pct", "%"),
            F("vfa_level", "visceral_fat_level", "level"),
            F("height", "height_at_measurement", "cm"),
        ),
    ),
    Datatype(
        id="com.samsung.shealth.blood_glucose",
        category="body", subkey="blood_glucose",
        friendly="Blood glucose",
        prefix=_BG,
        fields=(
            F("glucose", "glucose", "mmol/L"),
            F("meal_type", "meal_context", "", "enum:glucose_meal_context"),
            F("measurement_type", "measurement_type", "", "int"),
            F("sample_source_type", "sample_source_type", "", "int"),
            F("insulin_injected", "insulin_injected", "", "str"),
            F("medication", "medication", "", "str"),
        ),
    ),
    Datatype(
        id="com.samsung.health.skin_temperature",
        category="body", subkey="skin_temperature",
        friendly="Wrist skin temperature (session mean/min/max)",
        end_col="end_time",
        fields=(
            F("temperature", "skin_temp", "C"),
            F("max", "skin_temp_max", "C"),
            F("min", "skin_temp_min", "C"),
            F("baseline", "skin_temp_baseline", "C"),
            F("lower_bound", "skin_temp_lower_bound", "C"),
            F("upper_bound", "skin_temp_upper_bound", "C"),
        ),
        binning=Binning(
            ref="binning_data", dir_suffix="com.samsung.health.skin_temperature",
            fields=(F("mean", "skin_temp_mean", "C"), F("min", "skin_temp_min", "C"),
                    F("max", "skin_temp_max", "C")),
        ),
    ),
    Datatype(
        id="com.samsung.health.height",
        category="body", subkey="height",
        friendly="Height",
        fields=(F("height", "height", "cm"),),
    ),
    # --------------------------------------------------------------------- sleep
    Datatype(
        id="com.samsung.shealth.sleep",
        category="sleep", subkey="sessions",
        friendly="Sleep sessions (scoring + hypnogram)",
        prefix=_SLEEP, end_col="end_time",
        handler="sleep",
        fields=(
            F("sleep_score", "sleep_score", "0-100", "int"),
            F("efficiency", "sleep_efficiency_pct", "%"),
            F("sleep_duration", "sleep_duration_min", "min", "int"),
            F("total_rem_duration", "rem_min", "min", "int"),
            F("total_light_duration", "light_min", "min", "int"),
            F("mental_recovery", "mental_recovery", "0-100"),
            F("physical_recovery", "physical_recovery", "0-100"),
            F("sleep_cycle", "sleep_cycle", "count", "int"),
            F("sleep_latency", "sleep_latency_ms", "ms", "ms"),
            F("movement_awakening", "movement_awakening", "count", "int"),
            F("quality", "quality", "", "int"),
        ),
    ),
    Datatype(
        id="com.samsung.shealth.sleep_combined",
        category="sleep", subkey="combined",
        friendly="Merged multi-device nightly summary (overlaps sessions)",
        end_col="end_time",
        fields=(
            F("sleep_score", "sleep_score", "0-100", "int"),
            F("efficiency", "sleep_efficiency_pct", "%"),
            F("sleep_duration", "sleep_duration_min", "min", "int"),
            F("total_rem_duration", "rem_min", "min", "int"),
            F("total_light_duration", "light_min", "min", "int"),
            F("mental_recovery", "mental_recovery", "0-100"),
            F("physical_recovery", "physical_recovery", "0-100"),
            F("sleep_cycle", "sleep_cycle", "count", "int"),
        ),
    ),
    # ------------------------------------------------------------------ activity
    Datatype(
        id="com.samsung.shealth.tracker.pedometer_day_summary",
        category="activity", subkey="daily_steps",
        friendly="Steps per day (walk/run split, distance, calories)",
        time_col="day_time", time_kind="day_time", offset_col="",
        fields=(
            F("step_count", "steps_total", "count", "int"),
            F("walk_step_count", "steps_walking", "count", "int"),
            F("run_step_count", "steps_running", "count", "int"),
            F("distance", "distance_m", "m"),
            F("calorie", "calories_kcal", "kcal"),
            F("active_time", "active_time_ms", "ms", "ms"),
            F("healthy_step", "healthy_steps", "count", "int"),
        ),
    ),
    Datatype(
        id="com.samsung.shealth.activity.day_summary",
        category="activity", subkey="activity_daily",
        friendly="Daily activity roll-up (active/exercise time, score)",
        time_col="day_time", time_kind="day_time", offset_col="",
        fields=(
            F("step_count", "steps", "count", "int"),
            F("exercise_time", "exercise_time_ms", "ms", "ms"),
            F("active_time", "active_time_ms", "ms", "ms"),
            F("others_time", "others_time_ms", "ms", "ms"),
            F("run_time", "run_time_ms", "ms", "ms"),
            F("walk_time", "walk_time_ms", "ms", "ms"),
            F("calorie", "calories_kcal", "kcal"),
            F("distance", "distance_m", "m"),
            F("score", "activity_score", ""),
            F("floor_count", "floors", "count"),
            F("longest_active_time", "longest_active_time_ms", "ms", "ms"),
            F("longest_idle_time", "longest_idle_time_ms", "ms", "ms"),
        ),
    ),
    Datatype(
        id="com.samsung.shealth.calories_burned.details",
        category="activity", subkey="calories_daily",
        friendly="Daily energy expenditure (active/rest/TEF)",
        prefix=_CAL, time_col="day_time", time_kind="day_time", offset_col="",
        fields=(
            F("active_calorie", "active_kcal", "kcal"),
            F("rest_calorie", "rest_kcal", "kcal"),
            F("tef_calorie", "tef_kcal", "kcal"),
            F("active_time", "active_time_ms", "ms", "ms"),
        ),
    ),
    Datatype(
        id="com.samsung.shealth.tracker.floors_day_summary",
        category="activity", subkey="floors_daily",
        friendly="Floors climbed per day",
        time_col="day_time", time_kind="day_time", offset_col="",
        fields=(F("floor_count", "floors", "count"),),
    ),
    Datatype(
        id="com.samsung.health.floors_climbed",
        category="activity", subkey="floors_intervals",
        friendly="Floors climbed per interval",
        end_col="end_time",
        fields=(F("floor", "floors", "count"),),
    ),
    Datatype(
        id="com.samsung.shealth.tracker.pedometer_step_count",
        category="activity", subkey="steps_intraday",
        friendly="Per-minute step log",
        prefix=_STEP, end_col="end_time",
        fields=(
            F("count", "steps", "count", "int"),
            F("distance", "distance_m", "m"),
            F("calorie", "calories_kcal", "kcal"),
            F("duration", "duration_ms", "ms", "ms"),
            F("run_step", "run_steps", "count", "int"),
            F("walk_step", "walk_steps", "count", "int"),
        ),
    ),
    Datatype(
        id="com.samsung.health.movement",
        category="activity", subkey="movement_intraday",
        friendly="Per-minute movement intensity",
        end_col="end_time",
        fields=(),
        binning=Binning(
            ref="binning_data", dir_suffix="com.samsung.health.movement",
            fields=(F("activity_level", "activity_level", "index"),),
        ),
    ),
    Datatype(
        id="com.samsung.shealth.activity_level",
        category="activity", subkey="activity_levels",
        friendly="Activity level markers",
        fields=(F("activity_level", "level", "", "int"),),
    ),
    Datatype(
        id="com.samsung.shealth.step_daily_trend",
        category="activity", subkey="steps_daily_trend",
        friendly="Steps per day per source (deduped)",
        time_col="day_time", time_kind="day_time", offset_col="",
        handler="step_daily_trend",
        fields=(
            F("count", "steps", "count", "int"),
            F("distance", "distance_m", "m"),
            F("calorie", "calories_kcal", "kcal"),
            F("source_type", "source_type", "", "int"),
        ),
    ),
    # ---------------------------------------------------------------- stress
    Datatype(
        id="com.samsung.shealth.stress",
        category="stress", subkey="hourly",
        friendly="Stress score (0-100) hourly + per-minute detail",
        end_col="end_time",
        fields=(
            F("score", "stress_score", "0-100"),
            F("min", "stress_min", "0-100"),
            F("max", "stress_max", "0-100"),
            F("algorithm", "algorithm", "", "int"),
        ),
        binning=Binning(
            ref="binning_data", dir_suffix="com.samsung.shealth.stress",
            fields=(F("score", "stress_score", "0-100"),
                    F("score_min", "stress_min", "0-100"),
                    F("score_max", "stress_max", "0-100"),
                    F("level", "level", "", )),
        ),
    ),
    Datatype(
        id="com.samsung.shealth.alerted_stress",
        category="stress", subkey="alerts",
        friendly="High-stress alert markers",
        end_col="end_time",
        fields=(),
    ),
    # -------------------------------------------------------------- readiness
    Datatype(
        id="com.samsung.shealth.vitality_score",
        category="readiness", subkey="vitality",
        friendly="Daily readiness / vitality score",
        time_col="day_time", time_kind="day_time", offset_col="",
        fields=(
            F("total_score", "vitality_total_score", "0-100"),
            F("activity_score", "activity_score", "0-100"),
            F("sleep_score", "sleep_score", "0-100"),
            F("shr_score", "sleeping_hr_score", "0-100"),
            F("shr_value", "sleeping_hr", "bpm"),
            F("shrv_score", "sleeping_hrv_score", "0-100"),
            F("shrv_value", "sleeping_hrv", "ms"),
            F("mvpa_time", "mvpa_time_ms", "ms", "ms"),
            F("active_time", "active_time_ms", "ms", "ms"),
            F("sleep_regularity", "sleep_regularity", ""),
            F("activity_balance", "activity_balance", ""),
            F("sleep_balance", "sleep_balance", ""),
            F("sleep_duration", "sleep_duration_ms", "ms", "ms"),
        ),
    ),
    # ----------------------------------------------------------------- mental
    Datatype(
        id="com.samsung.shealth.mood",
        category="mental", subkey="mood",
        friendly="Self-reported mood",
        fields=(
            F("mood_type", "mood", "", "enum:mood_type"),
            F("factors", "factors", "", "str"),
            F("emotions", "emotions", "", "str"),
            F("notes", "notes", "", "str"),
            F("place", "place", "", "str"),
            F("company", "company", "", "str"),
        ),
    ),
    Datatype(
        id="com.samsung.shealth.breathing",
        category="mental", subkey="breathing_sessions",
        friendly="Guided breathing sessions",
        end_col="end_time",
        fields=(
            F("duration", "duration_ms", "ms", "ms"),
            F("cycle", "cycles", "count", "int"),
            F("type", "type", "", "int"),
            F("inhale_duration", "inhale_ms", "ms", "ms"),
            F("exhale_duration", "exhale_ms", "ms", "ms"),
            F("inhale_hold_duration", "inhale_hold_ms", "ms", "ms"),
            F("exhale_hold_duration", "exhale_hold_ms", "ms", "ms"),
        ),
    ),
    # --------------------------------------------------------------- exercise
    Datatype(
        id="com.samsung.shealth.exercise",
        category="exercise", subkey="sessions",
        friendly="Workout sessions (GPS stripped)",
        prefix=_EX, end_col="end_time",
        fields=(
            F("exercise_type", "exercise_type", "", "enum:exercise_type"),
            F("duration", "duration_ms", "ms", "ms"),
            F("distance", "distance_m", "m"),
            F("calorie", "calories_kcal", "kcal"),
            F("mean_heart_rate", "mean_hr", "bpm"),
            F("max_heart_rate", "max_hr", "bpm"),
            F("min_heart_rate", "min_hr", "bpm"),
            F("mean_speed", "mean_speed_mps", "m/s"),
            F("max_speed", "max_speed_mps", "m/s"),
            F("mean_cadence", "mean_cadence", "rpm"),
            F("max_cadence", "max_cadence", "rpm"),
            F("vo2_max", "vo2_max", "mL/kg/min"),
            F("altitude_gain", "altitude_gain_m", "m"),
            F("altitude_loss", "altitude_loss_m", "m"),
            F("count", "count", "count", "int"),
            F("sweat_loss", "sweat_loss", "mL"),
        ),
        binning=Binning(
            ref="live_data", dir_suffix="com.samsung.shealth.exercise",
            fields=(F("heart_rate", "hr", "bpm"), F("cadence", "cadence", "rpm"),
                    F("speed", "speed_mps", "m/s"), F("distance", "distance_m", "m"),
                    F("calorie", "calories_kcal", "kcal"),
                    F("percent_of_vo2max", "percent_of_vo2max", "%")),
            out="live_data",
        ),
    ),
    Datatype(
        id="com.samsung.shealth.exercise.max_heart_rate",
        category="exercise", subkey="max_heart_rate",
        friendly="Per-session max HR + aerobic/anaerobic thresholds",
        fields=(
            F("max_heart_rate", "max_hr", "bpm", "int"),
            F("at_heart_rate", "aerobic_threshold_hr", "bpm", "int"),
            F("ant_heart_rate", "anaerobic_threshold_hr", "bpm", "int"),
        ),
    ),
    Datatype(
        id="com.samsung.shealth.exercise.recovery_heart_rate",
        category="exercise", subkey="recovery_heart_rate",
        friendly="Post-exercise heart-rate recovery",
        end_col="end_time", handler="recovery_hr",
        fields=(),
        binning=Binning(
            ref="heart_rate",
            dir_suffix="com.samsung.shealth.exercise.recovery_heart_rate",
            out="recovery_samples",
        ),
    ),
    Datatype(
        id="com.samsung.shealth.exercise.hr_zone",
        category="exercise", subkey="hr_zone",
        friendly="Heart-rate zone thresholds per session",
        fields=(
            F("at", "aerobic_threshold_hr", "bpm"),
            F("ant", "anaerobic_threshold_hr", "bpm"),
            F("max_hr_auto", "max_hr_auto", "bpm"),
            F("max_hr_custom", "max_hr_custom", "bpm"),
        ),
    ),
    # --------------------------------------------------------------- nutrition
    Datatype(
        id="com.samsung.health.nutrition",
        category="nutrition", subkey="macros",
        friendly="Per-meal macronutrients",
        fields=(
            F("title", "food_name", "", "str"),
            F("meal_type", "meal", "", "enum:meal_type"),
            F("calorie", "calorie", "kcal"),
            F("protein", "protein", "g"),
            F("total_fat", "total_fat", "g"),
            F("saturated_fat", "saturated_fat", "g"),
            F("trans_fat", "trans_fat", "g"),
            F("carbohydrate", "carbohydrate", "g"),
            F("sugar", "sugar", "g"),
            F("added_sugar", "added_sugar", "g"),
            F("dietary_fiber", "dietary_fiber", "g"),
            F("cholesterol", "cholesterol", "mg"),
            F("sodium", "sodium", "mg"),
            F("potassium", "potassium", "mg"),
            F("calcium", "calcium", "mg"),
            F("iron", "iron", "mg"),
        ),
    ),
    Datatype(
        id="com.samsung.health.food_intake",
        category="nutrition", subkey="meals",
        friendly="Meal log (names resolved from the food dictionary)",
        handler="food_intake",
        fields=(
            F("name", "food_name", "", "str"),
            F("meal_type", "meal", "", "enum:meal_type"),
            F("calorie", "calorie", "kcal"),
            F("amount", "amount", ""),
            F("unit", "unit_code", "", "str"),
            F("food_info_id", "food_info_id", "", "str"),
        ),
    ),
    Datatype(
        id="com.samsung.health.water_intake",
        category="nutrition", subkey="water",
        friendly="Hydration",
        fields=(
            F("amount", "amount_ml", "ml"),
            F("unit_amount", "unit_amount", ""),
        ),
    ),
    # ------------------------------------------------------------------ profile
    Datatype(
        id="com.samsung.health.user_profile",
        category="profile", subkey="",
        friendly="User profile (-> patient_profile header)",
        handler="user_profile", time_col="", offset_col="",
    ),
)


# Datatypes deliberately not exported, each with a reason. They still appear in
# the coverage manifest so nothing is dropped silently.
EXCLUDED: dict[str, tuple[str, str]] = {
    "com.samsung.shealth.exercise.weather": ("privacy", "contains exact GPS coordinates"),
    "com.samsung.health.device_profile": ("privacy", "device registry incl. Bluetooth address & device ids"),
    "com.samsung.shealth.goal": ("config", "user step/activity goals"),
    "com.samsung.shealth.service_preferences": ("config", "app service preferences"),
    "com.samsung.shealth.preferences": ("config", "app UI preferences"),
    "com.samsung.shealth.hsp.references": ("internal", "internal id reference map"),
    "com.samsung.shealth.report": ("derived", "weekly report roll-ups (raw data is exported instead)"),
    "com.samsung.shealth.badge": ("gamification", "achievement badges"),
    "com.samsung.shealth.sleep_goal": ("config", "target bedtime/wake"),
    "com.samsung.shealth.food_goal": ("config", "nutrition targets"),
    "com.samsung.shealth.exercise.hr_zone.settings": ("config", "which HR-zone model per sport"),
    "com.samsung.shealth.food_favorite": ("preferences", "favourite foods"),
    "com.samsung.shealth.food_frequent": ("preferences", "frequently logged foods"),
    "com.samsung.shealth.best_records": ("gamification", "personal-best records"),
    "com.samsung.shealth.stress.histogram": ("internal", "stress-algorithm calibration state, not a patient measurement"),
    "com.samsung.shealth.exercise.extension": ("internal", "empty linkage table"),
    "com.samsung.shealth.exercise.periodization_training_program": ("template", "workout plan template"),
    "com.samsung.shealth.exercise.periodization_training_schedule": ("template", "coaching schedule template"),
}

# Consumed by another handler rather than emitted on its own.
CONSUMED: dict[str, str] = {
    "com.samsung.health.sleep_stage": "merged into sleep.sessions[].hypnogram",
    "com.samsung.health.food_info": "used to resolve food names in nutrition.meals",
}


def by_id() -> dict[str, Datatype]:
    return {d.id: d for d in INCLUDED}
