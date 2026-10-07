"""Code -> human label dictionaries used across the export.

Codes that are not in a table are passed through as ``"<enum>_<code>"`` so the
raw value is never lost; every mapping below is also emitted into the JSON
legend so a reader can audit our decoding.

Sources: the Samsung Health SDK constant reference
(developer.samsung.com/health/android/data/api-reference/constant-values.html
and EXERCISE_TYPE.html). Tables marked *inferred* have no public
documentation; their labels were derived from the data itself.
"""

from __future__ import annotations

SLEEP_STAGE = {
    '40001': 'awake',
    '40002': 'light',
    '40003': 'deep',
    '40004': 'rem',
}

MEAL_TYPE = {
    '100001': 'breakfast',
    '100002': 'lunch',
    '100003': 'dinner',
    '100004': 'morning_snack',
    '100005': 'afternoon_snack',
    '100006': 'evening_snack',
}

# Samsung predefined exercise types (official table).
EXERCISE_TYPE = {
    '1001': 'walking',
    '1002': 'running',
    '11007': 'cycling',
    '13001': 'hiking',
    '15001': 'step_machine',
    '15002': 'weight_machine',
    '15003': 'exercise_bike',
    '15004': 'rowing_machine',
    '15005': 'treadmill',
    '15006': 'elliptical_trainer',
}

# *inferred*: 1 = workouts with HR started on the watch; 4 = 10-64 min walks
# without HR logged by the phone; 8 = 10-52 min watch walks (Jan-Feb 2025).
EXERCISE_SOURCE = {
    '1': 'user_started_workout',
    '4': 'auto_detected',
    '8': 'auto_detected_watch',
}

EXERCISE_COUNT_TYPE = {
    '30001': 'strides',
    '30002': 'strokes',
    '30003': 'swings',
    '30004': 'repetitions',
}

# blood_glucose measurement context (meal_type column on the glucose table)
GLUCOSE_MEAL_TYPE = {
    '80001': 'fasting',
    '80002': 'after_meal',
    '80003': 'before_breakfast',
    '80004': 'after_breakfast',
    '80005': 'before_lunch',
    '80006': 'after_lunch',
    '80007': 'before_dinner',
    '80008': 'after_dinner',
    '80009': 'after_bedtime',
    '80010': 'after_snack',
    '80011': 'before_meal',
    '80012': 'general',
    '80013': 'before_sleep',
}

GLUCOSE_MEASUREMENT_TYPE = {
    '90001': 'whole_blood',
    '90002': 'plasma',
    '90003': 'serum',
}

GLUCOSE_SAMPLE_SOURCE = {
    '90001': 'venous',
    '90002': 'capillary',
}

# food_intake.unit; 120005 is not in the SDK table (amounts 220-400 in this
# export, logged for drinks) — kept as a raw code rather than guessed.
FOOD_UNIT = {
    '120001': 'serving',
    '120002': 'gram',
    '120003': 'ounce',
    '120004': 'kcal',
}

# step_daily_trend.source_type (official).
STEP_SOURCE = {
    '-2': 'all_devices_combined',
    '-1': 'partner_app',
    '0': 'phone_only',
}

# *inferred*: 21313 rows are hourly summaries with per-minute detail;
# 21316 rows are single readings (start == end, no min/max, no detail).
HR_TAG = {
    '21313': 'hourly_summary',
    '21316': 'spot_reading',
}

# *inferred*: 31301 rows are overnight sessions with per-minute detail;
# 30000 / 31000 are single readings (start == end, no detail).
SPO2_TAG = {
    '30000': 'spot_reading',
    '31000': 'spot_reading',
    '31301': 'sleep_session',
}

# Self-reported mood (1..5 scale, Samsung "mood_type"); best-effort labels.
MOOD_TYPE = {
    '1': 'unpleasant',
    '2': 'slightly_unpleasant',
    '3': 'neutral',
    '4': 'slightly_pleasant',
    '5': 'pleasant',
}


def decode(table: dict[str, str], code: str, prefix: str) -> str | None:
    """Label for ``code``, or ``"<prefix>_<code>"`` for unknown codes."""
    if code is None or code == '':
        return None
    code = str(code)
    if code.endswith('.0'):
        code = code[:-2]
    if code == '-1' and code not in table:
        return None                  # Samsung's "not defined" sentinel
    return table.get(code, f'{prefix}_{code}')


# Exposed to the legend builder so the produced file documents its own codes.
ALL = {
    'sleep_stage': SLEEP_STAGE,
    'meal_type': MEAL_TYPE,
    'exercise_type': EXERCISE_TYPE,
    'exercise_source': EXERCISE_SOURCE,
    'exercise_count_type': EXERCISE_COUNT_TYPE,
    'glucose_meal_context': GLUCOSE_MEAL_TYPE,
    'glucose_measurement_type': GLUCOSE_MEASUREMENT_TYPE,
    'glucose_sample_source': GLUCOSE_SAMPLE_SOURCE,
    'food_unit': FOOD_UNIT,
    'step_source': STEP_SOURCE,
    'hr_tag': HR_TAG,
    'spo2_tag': SPO2_TAG,
    'mood_type': MOOD_TYPE,
}
