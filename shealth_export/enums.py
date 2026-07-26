"""Code -> human label dictionaries used across the export.

Codes that are not in a table are passed through as ``"<enum>_<code>"`` so the
raw value is never lost; every mapping below is also emitted into the JSON
legend so a reader can audit our decoding.
"""

from __future__ import annotations

SLEEP_STAGE = {
    "40001": "awake",
    "40002": "light",
    "40003": "deep",
    "40004": "rem",
}

MEAL_TYPE = {
    "100001": "breakfast",
    "100002": "lunch",
    "100003": "dinner",
    "100004": "morning_snack",
    "100005": "afternoon_snack",
    "100006": "evening_snack",
}

# Samsung exercise type codes (only the ones present in this export are certain;
# others are best-effort and still carry the raw code).
EXERCISE_TYPE = {
    "1001": "walking",
    "1002": "running",
    "11007": "cycling",
    "13001": "hiking",
    "15002": "strength_training",
    "15005": "elliptical_or_other_gym",
}

# blood_glucose measurement context (meal_type column on the glucose table)
GLUCOSE_MEAL_TYPE = {
    "80001": "before_meal",
    "80002": "after_meal",
    "80011": "fasting",
    "10001": "general",
}

# Self-reported mood (1..5 scale, Samsung "mood_type"); best-effort labels.
MOOD_TYPE = {
    "1": "unpleasant",
    "2": "slightly_unpleasant",
    "3": "neutral",
    "4": "slightly_pleasant",
    "5": "pleasant",
}


def decode(table: dict[str, str], code: str, prefix: str) -> str | None:
    """Return the label for ``code`` or ``"<prefix>_<code>"`` for unknown non-empty codes."""
    if code is None or code == "":
        return None
    return table.get(code, f"{prefix}_{code}")


# Exposed to the legend builder so the produced file documents its own codes.
ALL = {
    "sleep_stage": SLEEP_STAGE,
    "meal_type": MEAL_TYPE,
    "exercise_type": EXERCISE_TYPE,
    "glucose_meal_context": GLUCOSE_MEAL_TYPE,
    "mood_type": MOOD_TYPE,
}
