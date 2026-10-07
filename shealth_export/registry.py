"""Declarative spec of what to export and how to map it.

Adding or changing a data type is a *data* edit here, not a code change: the
generic extractor in :mod:`extract` reads this registry and does the rest.
Privacy is enforced by construction — only the columns listed in ``fields``
are ever read, so device ids, Bluetooth addresses, GPS tracks, uuids and app
config simply never leave the CSV.

Field casts (see ``extract.cast_value``): ``str`` | ``int`` | ``posint`` |
``float`` | ``posfloat`` | ``nonneg`` (int >= 0) | ``kmh_to_mps`` |
``enum:<table>``. The ``pos*`` casts turn Samsung's 0-placeholders into null
(flagged ``zero_is_null`` in the legend); ``-1`` is always null.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Field:
    raw: str            # source column (short name; prefix applied by reader)
    name: str = ''      # output key (defaults to raw)
    unit: str = ''      # documented in the legend
    cast: str = 'float'
    note: str = ''      # interpretation caveat, emitted into the legend

    def out_name(self) -> str:
        return self.name or self.raw


@dataclass(frozen=True)
class Binning:
    ref: str            # column holding "<uuid>.<...>.json"
    dir_suffix: str     # jsons/<dir_suffix>/...
    fields: tuple[Field, ...] = ()
    time_key: str = 'start_time'   # epoch-ms key inside each json item
    out: str = 'detail'            # key the detail array is attached under


@dataclass(frozen=True)
class Datatype:
    id: str
    category: str
    subkey: str
    friendly: str
    time_col: str = 'start_time'
    time_kind: str = 'utc_string'   # utc_string | day_time
    offset_col: str = 'time_offset'
    end_col: str = ''
    prefix: str = ''
    fields: tuple[Field, ...] = ()
    binning: Binning | None = None
    handler: str = 'generic'
    # one row per local day: 'max:<output field>' keeps the row with the
    # largest value (ties -> most recently updated row)
    dedup: str = ''
    window_overlap: bool = False    # in window if start OR end day is in it
    device: bool = False            # emit 'device' (phone/watch/combined)
    skip_empty: bool = False        # drop records with no measurement
    note: str = ''                  # section caveat, emitted into the legend
    extra: tuple[Field, ...] = ()   # keys added by the handler (legend only)
    # nested arrays/objects a handler builds: ((key, (Field, ...)), ...)
    nested: tuple[tuple[str, tuple[Field, ...]], ...] = ()
    # day rows where all of these output fields are 0/absent get
    # no_movement_recorded=true (no device was tracking)
    zero_day_fields: tuple[str, ...] = ()


def F(raw, name='', unit='', cast='float', note='') -> Field:
    return Field(raw, name, unit, cast, note)


def X(name, unit='', note='') -> Field:
    """Document a key that a handler adds (not read from a CSV column)."""
    return Field('', name, unit, '', note)


# Column namespaces used by some tables.
_HR = 'com.samsung.health.heart_rate.'
_BP = 'com.samsung.health.blood_pressure.'
_SPO2 = 'com.samsung.health.oxygen_saturation.'
_BG = 'com.samsung.health.blood_glucose.'
_SLEEP = 'com.samsung.health.sleep.'
_EX = 'com.samsung.health.exercise.'
_STEP = 'com.samsung.health.step_count.'
_CAL = 'com.samsung.shealth.calories_burned.'

_DEVICE = X('device', '', 'source device class: phone / watch / combined '
            '(merged by Samsung); device identities are not exported')
_PARTIAL = X('partial_day', '', 'true for the export day itself: the day was '
             'still in progress when the export was taken')
_NO_MOVE = X('no_movement_recorded', '', 'true when every movement field '
             'is 0 - usually no device was tracking that day (e.g. before '
             'tracking started), not a truly immobile day')

_SLEEP_SCORES = (
    F('sleep_score', 'sleep_score', '0-100', 'int'),
    F('efficiency', 'sleep_efficiency_pct', '%', 'posfloat'),
    F('sleep_duration', 'sleep_duration_min', 'min', 'int',
      'whole recorded sleep period INCLUDING awake episodes '
      '(= sum of all hypnogram stages)'),
    F('factor_02', 'deep_min', 'min', 'int',
      'Samsung column factor_02; matches the hypnogram deep total (+-0.5 '
      'min) on every staged session'),
    F('total_light_duration', 'light_min', 'min', 'int'),
    F('total_rem_duration', 'rem_min', 'min', 'int'),
    F('factor_05', 'awake_min', 'min', 'int',
      'Samsung column factor_05; matches the hypnogram awake total (+-0.5 '
      'min) on every staged session'),
    F('mental_recovery', 'mental_recovery', '0-100'),
    F('physical_recovery', 'physical_recovery', '0-100'),
    F('sleep_cycle', 'sleep_cycle', 'count', 'int'),
    F('total_sleep_time_score', 'total_sleep_time_score', 'points',
      'int', 'component of sleep_score (newer app versions only)'),
    F('deep_score', 'deep_score', 'points', 'int',
      'component of sleep_score'),
    F('rem_score', 'rem_score', 'points', 'int',
      'component of sleep_score'),
    F('latency_score', 'latency_score', 'points', 'int',
      'component of sleep_score'),
    F('wake_score', 'wake_score', 'points', 'int',
      'component of sleep_score'),
    F('sleep_efficiency_with_latency', 'sleep_efficiency_with_latency_pct',
      '%', 'posfloat'),
)


INCLUDED: tuple[Datatype, ...] = (
    # ------------------------------------------------------------ cardio
    Datatype(
        id='com.samsung.shealth.tracker.heart_rate',
        category='cardiovascular', subkey='heart_rate',
        friendly='Heart rate (hourly summary + per-minute detail, '
                 'plus single spot readings)',
        prefix=_HR, end_col='end_time',
        fields=(
            F('tag_id', 'kind', '', 'enum:hr_tag',
              'hourly_summary rows carry min/max and per-minute detail; '
              'spot_reading rows are one-off measurements'),
            F('heart_rate', 'heart_rate', 'bpm'),
            F('min', 'heart_rate_min', 'bpm'),
            F('max', 'heart_rate_max', 'bpm'),
        ),
        binning=Binning(
            ref='binning_data',
            dir_suffix='com.samsung.shealth.tracker.heart_rate',
            fields=(F('heart_rate', 'heart_rate', 'bpm'),
                    F('heart_rate_min', 'heart_rate_min', 'bpm'),
                    F('heart_rate_max', 'heart_rate_max', 'bpm')),
        ),
    ),
    Datatype(
        id='com.samsung.health.hrv',
        category='cardiovascular', subkey='hrv',
        friendly='Heart-rate variability (values live only in the detail)',
        end_col='end_time',
        fields=(),
        binning=Binning(
            ref='binning_data', dir_suffix='com.samsung.health.hrv',
            fields=(F('sdnn', 'sdnn', 'ms'), F('rmssd', 'rmssd', 'ms')),
        ),
    ),
    Datatype(
        id='com.samsung.shealth.blood_pressure',
        category='cardiovascular', subkey='blood_pressure',
        friendly='Blood pressure (cuff readings)',
        prefix=_BP,
        fields=(
            F('systolic', 'systolic', 'mmHg', 'int'),
            F('diastolic', 'diastolic', 'mmHg', 'int'),
            F('mean', 'mean_arterial_pressure', 'mmHg', 'posfloat',
              'Samsung stores 0 when not measured -> null'),
            F('pulse', 'pulse', 'bpm', 'int'),
            F('medication', 'medication', '', 'str',
              'medication flag/text as entered with the reading'),
        ),
    ),
    Datatype(
        id='com.samsung.shealth.heart_health_score',
        category='cardiovascular', subkey='heart_health_score',
        friendly='Samsung heart-health score (proprietary)',
        time_col='day_time', time_kind='day_time', offset_col='',
        skip_empty=True,
        fields=(
            F('total_score', 'total_score', '0-100'),
            F('exercise_score', 'exercise_score', '0-100'),
            F('sleep_score', 'sleep_score', '0-100'),
            F('mean_arterial_pressure_score', 'blood_pressure_score',
              '0-100'),
            F('body_mass_index_score', 'bmi_score', '0-100'),
        ),
        note='rows whose scores are all empty are skipped',
    ),
    # ------------------------------------------------------- respiratory
    Datatype(
        id='com.samsung.shealth.tracker.oxygen_saturation',
        category='respiratory', subkey='oxygen_saturation',
        friendly='Blood oxygen (SpO2): overnight sessions & spot readings',
        prefix=_SPO2, end_col='end_time',
        fields=(
            F('tag_id', 'kind', '', 'enum:spo2_tag'),
            F('spo2', 'spo2', '%'),
            F('min', 'spo2_min', '%'),
            F('max', 'spo2_max', '%'),
            F('heart_rate', 'heart_rate', 'bpm'),
            F('coverage_rate', 'coverage_rate', '%'),
            F('low_duration', 'time_below_90pct_s', 's', 'nonneg',
              'seconds with SpO2 below 90% in the session (verified '
              'against the Samsung Health app: 319 = "5 min 19 s")'),
        ),
        binning=Binning(
            ref='binning',
            dir_suffix='com.samsung.shealth.tracker.oxygen_saturation',
            fields=(F('spo2', 'spo2', '%'), F('spo2_min', 'spo2_min', '%'),
                    F('spo2_max', 'spo2_max', '%'),
                    F('isIrregular', 'irregular', '', 'int',
                      '1 = Samsung flagged the minute as irregular')),
        ),
    ),
    Datatype(
        id='com.samsung.health.respiratory_rate',
        category='respiratory', subkey='respiratory_rate',
        friendly='Respiratory rate (breaths per minute)',
        end_col='end_time',
        fields=(
            F('average', 'respiratory_rate_avg', 'breaths/min', 'posfloat'),
            F('lower_limit', 'respiratory_rate_min', 'breaths/min',
              'posfloat'),
            F('upper_limit', 'respiratory_rate_max', 'breaths/min',
              'posfloat'),
            F('is_outlier', 'is_outlier', '', 'int',
              '1 = Samsung marked the session as an outlier vs the '
              "person's baseline"),
        ),
        binning=Binning(
            ref='binning_data',
            dir_suffix='com.samsung.health.respiratory_rate',
            fields=(F('respiratory_rate', 'respiratory_rate', 'breaths/min',
                      'posfloat',
                      '0 readings (sensor warm-up) are dropped'),),
        ),
    ),
    # -------------------------------------------------- body measurement
    Datatype(
        id='com.samsung.health.weight',
        category='body', subkey='weight',
        friendly='Weight & body composition',
        fields=(
            F('weight', 'weight', 'kg'),
            F('body_fat', 'body_fat_pct', '%'),
            F('body_fat_mass', 'body_fat_mass', 'kg'),
            F('muscle_mass', 'muscle_mass', 'kg'),
            F('skeletal_muscle_mass', 'skeletal_muscle_mass', 'kg'),
            F('skeletal_muscle', 'skeletal_muscle_pct', '%'),
            F('basal_metabolic_rate', 'bmr', 'kcal'),
            F('total_body_water', 'total_body_water', 'kg'),
            F('fat_free_mass', 'fat_free_mass', 'kg'),
            F('fat_free', 'fat_free_pct', '%'),
            F('vfa_level', 'visceral_fat_level', 'level'),
            F('height', 'height_at_measurement', 'cm'),
        ),
    ),
    Datatype(
        id='com.samsung.shealth.blood_glucose',
        category='body', subkey='blood_glucose',
        friendly='Blood glucose',
        prefix=_BG,
        fields=(
            F('glucose', 'glucose', 'mmol/L'),
            F('meal_type', 'meal_context', '', 'enum:glucose_meal_context'),
            F('measurement_type', 'measurement_type', '',
              'enum:glucose_measurement_type'),
            F('sample_source_type', 'sample_source', '',
              'enum:glucose_sample_source'),
            F('insulin_injected', 'insulin_injected', 'IU',
              note='0 = no insulin recorded with the reading'),
            F('medication', 'medication', '', 'int',
              '0 = no medication recorded with the reading'),
        ),
    ),
    Datatype(
        id='com.samsung.health.skin_temperature',
        category='body', subkey='skin_temperature',
        friendly='Wrist skin temperature (session mean/min/max)',
        end_col='end_time',
        fields=(
            F('temperature', 'skin_temp', 'C'),
            F('max', 'skin_temp_max', 'C'),
            F('min', 'skin_temp_min', 'C'),
            F('baseline', 'skin_temp_baseline', 'C'),
            F('lower_bound', 'skin_temp_lower_bound', 'C'),
            F('upper_bound', 'skin_temp_upper_bound', 'C'),
        ),
        binning=Binning(
            ref='binning_data',
            dir_suffix='com.samsung.health.skin_temperature',
            fields=(F('mean', 'skin_temp_mean', 'C'),
                    F('min', 'skin_temp_min', 'C'),
                    F('max', 'skin_temp_max', 'C')),
        ),
    ),
    Datatype(
        id='com.samsung.health.height',
        category='body', subkey='height',
        friendly='Height',
        fields=(F('height', 'height', 'cm'),),
    ),
    # ------------------------------------------------------------- sleep
    Datatype(
        id='com.samsung.shealth.sleep',
        category='sleep', subkey='sessions',
        friendly='Sleep sessions (scoring + hypnogram)',
        prefix=_SLEEP, end_col='end_time',
        handler='sleep',
        fields=_SLEEP_SCORES + (
            F('sleep_latency', 'sleep_latency_ms', 'ms', 'nonneg'),
            F('movement_awakening', 'movement_awakening', 'index',
              'int', 'Samsung-proprietary restlessness index (2-100), '
              'not a count of awakenings'),
            F('quality', 'quality', '', 'posint',
              'Samsung quality code; only set on unstaged sessions'),
        ),
        nested=(('hypnogram', (
            F('stage', 'stage', '', 'enum:sleep_stage'),
            X('start', '', 'local ISO start of the stage'),
            X('end', '', 'local ISO end of the stage'))),),
        extra=(
            X('wake_date', 'date', 'local date of sleep_end; the same '
              'convention as readiness.vitality[].day'),
            X('staged', '', 'false = no stage analysis (phone/manual '
              'entry): stage minutes, scores and hypnogram are absent'),
            X('is_nap', '', 'Samsung classified the session as a nap'),
            X('merged_into_combined', '', 'this session is one segment '
              'of a sleep.combined night - do not add both'),
            X('hypnogram', '', 'stage timeline: {stage, start, end}'),
        ),
    ),
    Datatype(
        id='com.samsung.shealth.sleep_combined',
        category='sleep', subkey='combined',
        friendly='Nights merged from several segments of one night',
        end_col='end_time',
        fields=_SLEEP_SCORES,
        note='each row merges sleep.sessions flagged '
             'merged_into_combined; never sum combined with its segments',
    ),
    Datatype(
        id='com.samsung.shealth.vitality.nap_data',
        category='sleep', subkey='naps',
        friendly='Naps with the vitality score before/after',
        end_col='end_time',
        fields=(
            F('score_before', 'vitality_before', '0-100'),
            F('score_after', 'vitality_after', '0-100'),
        ),
        note='the same naps also appear in sleep.sessions (is_nap=true)',
    ),
    # ---------------------------------------------------------- activity
    Datatype(
        id='com.samsung.shealth.tracker.pedometer_day_summary',
        category='activity', subkey='daily_steps',
        friendly='Steps per day, all devices merged (canonical daily total)',
        time_col='day_time', time_kind='day_time', offset_col='',
        handler='daily_steps',
        fields=(
            F('step_count', 'steps_total', 'count', 'int'),
            F('walk_step_count', 'steps_walking', 'count', 'int'),
            F('run_step_count', 'steps_running', 'count', 'int'),
            F('distance', 'distance_m', 'm'),
            F('calorie', 'calories_kcal', 'kcal'),
            F('active_time', 'active_time_ms', 'ms', 'nonneg'),
            F('speed', 'walking_speed_mps', 'm/s', 'posfloat',
              'average speed while moving that day'),
        ),
        binning=Binning(
            ref='binning_data',
            dir_suffix='com.samsung.shealth.tracker.pedometer_day_summary',
            fields=(F('mStepCount', 'steps', 'count', 'int'),
                    F('mWalkStepCount', 'steps_walking', 'count', 'int'),
                    F('mRunStepCount', 'steps_running', 'count', 'int'),
                    F('mDistance', 'distance_m', 'm'),
                    F('mCalorie', 'calories_kcal', 'kcal'),
                    F('mTotalActiveTime', 'active_time_ms', 'ms', 'nonneg'),
                    F('mSpeed', 'speed_mps', 'm/s', 'kmh_to_mps',
                      'the source stores km/h; converted to m/s')),
            out='detail_10min',
        ),
        extra=(_PARTIAL,
               X('detail_10min', '', '10-minute bins of the merged total; '
                 'bins with 0 steps are omitted; t = bin start')),
        note='one row per day: the row Samsung merged across all devices '
             '("Combined"); per-device rows are not exported',
    ),
    Datatype(
        id='com.samsung.shealth.activity.day_summary',
        category='activity', subkey='activity_daily',
        friendly='Daily activity roll-up (active/exercise time, score)',
        time_col='day_time', time_kind='day_time', offset_col='',
        dedup='max:steps',
        fields=(
            F('step_count', 'steps', 'count', 'int'),
            F('exercise_time', 'exercise_time_ms', 'ms', 'nonneg'),
            F('active_time', 'active_time_ms', 'ms', 'nonneg'),
            F('others_time', 'others_time_ms', 'ms', 'nonneg'),
            F('run_time', 'run_time_ms', 'ms', 'nonneg'),
            F('walk_time', 'walk_time_ms', 'ms', 'nonneg'),
            F('calorie', 'calories_kcal', 'kcal'),
            F('distance', 'distance_m', 'm'),
            F('score', 'activity_score', '0-100',
              note='Samsung-proprietary daily activity score'),
            F('longest_active_time', 'longest_active_time_ms', 'ms',
              'nonneg'),
        ),
        extra=(_PARTIAL, _NO_MOVE),
        zero_day_fields=('steps', 'active_time_ms', 'distance_m',
                         'exercise_time_ms'),
        note='one row per day (phones only; when two phones overlap the '
             'row with more steps is kept). Floors: see floors_daily',
    ),
    Datatype(
        id='com.samsung.shealth.calories_burned.details',
        category='activity', subkey='calories_daily',
        friendly='Daily energy expenditure (active/rest/TEF)',
        prefix=_CAL, time_col='day_time', time_kind='day_time',
        offset_col='', dedup='max:active_kcal',
        fields=(
            F('active_calorie', 'active_kcal', 'kcal'),
            F('rest_calorie', 'rest_kcal', 'kcal'),
            F('tef_calorie', 'tef_kcal', 'kcal',
              note='thermic effect of food'),
            F('active_time', 'active_time_ms', 'ms', 'nonneg'),
        ),
        extra=(_PARTIAL, _NO_MOVE),
        zero_day_fields=('active_kcal', 'active_time_ms'),
        note='one row per day (when two phones overlap the row with more '
             'active kcal is kept); rest_kcal is estimated from the profile '
             'even on days without tracking',
    ),
    Datatype(
        id='com.samsung.shealth.tracker.floors_day_summary',
        category='activity', subkey='floors_daily',
        friendly='Floors climbed per day',
        time_col='day_time', time_kind='day_time', offset_col='',
        dedup='max:floors',
        fields=(F('floor_count', 'floors', 'count'),),
        extra=(_PARTIAL,),
    ),
    Datatype(
        id='com.samsung.health.floors_climbed',
        category='activity', subkey='floors_intervals',
        friendly='Floors climbed per interval',
        end_col='end_time',
        fields=(F('floor', 'floors', 'count'),),
    ),
    Datatype(
        id='com.samsung.shealth.tracker.pedometer_step_count',
        category='activity', subkey='steps_intraday',
        friendly='Per-minute step log, per device',
        prefix=_STEP, end_col='end_time', device=True,
        fields=(
            F('count', 'steps', 'count', 'int'),
            F('distance', 'distance_m', 'm'),
            F('calorie', 'calories_kcal', 'kcal'),
            F('duration', 'duration_ms', 'ms', 'nonneg'),
            F('run_step', 'run_steps', 'count', 'int'),
            F('walk_step', 'walk_steps', 'count', 'int'),
        ),
        extra=(_DEVICE,),
        note='phone and watch log the same minutes in parallel: never sum '
             'across devices (use daily_steps for totals). Only recent '
             'weeks exist in the source; for older days use '
             'daily_steps[].detail_10min',
    ),
    Datatype(
        id='com.samsung.health.movement',
        category='activity', subkey='movement_intraday',
        friendly='Per-minute movement intensity',
        end_col='end_time',
        fields=(),
        binning=Binning(
            ref='binning_data', dir_suffix='com.samsung.health.movement',
            fields=(F('activity_level', 'activity_level', 'index'),),
        ),
    ),
    Datatype(
        id='com.samsung.shealth.activity_level',
        category='activity', subkey='activity_levels',
        friendly='Activity level markers',
        fields=(F('activity_level', 'level', 'code', 'int',
                  'undocumented Samsung activity-level code'),),
    ),
    Datatype(
        id='com.samsung.shealth.step_daily_trend',
        category='activity', subkey='steps_daily_trend',
        friendly='Steps per day, all-devices row (one row per day)',
        time_col='day_time', time_kind='day_time', offset_col='',
        handler='step_daily_trend',
        fields=(
            F('count', 'steps', 'count', 'int'),
            F('distance', 'distance_m', 'm'),
            F('calorie', 'calories_kcal', 'kcal'),
            F('source_type', 'source', '', 'enum:step_source'),
        ),
        extra=(_PARTIAL,),
        note='should equal daily_steps.steps_total; kept as a cross-check',
    ),
    # ------------------------------------------------------------ stress
    Datatype(
        id='com.samsung.shealth.stress',
        category='stress', subkey='hourly',
        friendly='Stress score (0-100) hourly + per-minute detail',
        end_col='end_time',
        fields=(
            F('score', 'stress_score', '0-100'),
            F('min', 'stress_min', '0-100'),
            F('max', 'stress_max', '0-100'),
            F('algorithm', 'algorithm', '', 'int',
              'Samsung stress-algorithm version code'),
        ),
        binning=Binning(
            ref='binning_data', dir_suffix='com.samsung.shealth.stress',
            fields=(F('score', 'stress_score', '0-100'),
                    F('score_min', 'stress_min', '0-100'),
                    F('score_max', 'stress_max', '0-100')),
        ),
        note='0 is a real (very low) reading, not "missing": Samsung '
             'averages zero minutes into the hourly score',
    ),
    Datatype(
        id='com.samsung.shealth.alerted_stress',
        category='stress', subkey='alerts',
        friendly='High-stress alert markers',
        end_col='end_time',
        fields=(),
    ),
    # --------------------------------------------------------- readiness
    Datatype(
        id='com.samsung.shealth.vitality_score',
        category='readiness', subkey='vitality',
        friendly='Daily readiness / vitality score',
        time_col='day_time', time_kind='day_time', offset_col='',
        fields=(
            F('total_score', 'vitality_total_score', '0-100'),
            F('activity_score', 'activity_score', '0-100'),
            F('sleep_score', 'sleep_score', '0-100'),
            F('shr_score', 'sleeping_hr_score', '0-100'),
            F('shr_value', 'sleeping_hr', 'bpm'),
            F('shr_baseline_min', 'sleeping_hr_baseline_min', 'bpm',
              note="the person's own normal range for sleeping HR"),
            F('shr_baseline_max', 'sleeping_hr_baseline_max', 'bpm'),
            F('prev_shr_avg', 'sleeping_hr_prev_avg', 'bpm',
              note='recent average used as the comparison point'),
            F('shrv_score', 'sleeping_hrv_score', '0-100'),
            F('shrv_value', 'sleeping_hrv', 'ms'),
            F('shrv_baseline_min', 'sleeping_hrv_baseline_min', 'ms',
              note="the person's own normal range for sleeping HRV"),
            F('shrv_baseline_max', 'sleeping_hrv_baseline_max', 'ms'),
            F('prev_shrv_avg', 'sleeping_hrv_prev_avg', 'ms'),
            F('skin_temperature_scale', 'skin_temp_score', '0-100'),
            F('skin_temperature_optimal_range_min',
              'skin_temp_optimal_min', 'C'),
            F('skin_temperature_optimal_range_max',
              'skin_temp_optimal_max', 'C'),
            F('max_hr', 'max_hr', 'bpm',
              note='max HR the score assumes (age/profile based)'),
            F('mvpa_time', 'mvpa_time_ms', 'ms', 'nonneg',
              note='moderate-to-vigorous physical activity'),
            F('active_time', 'active_time_ms', 'ms', 'nonneg'),
            F('sleep_regularity', 'sleep_regularity', '0-100'),
            F('activity_balance', 'activity_balance', 'ratio',
              note='short-term / long-term activity load; 0.83-1.17 is '
                   "Samsung's optimal band"),
            F('sleep_balance', 'sleep_balance', 'ratio'),
            F('sleep_duration', 'sleep_duration_ms', 'ms', 'nonneg',
              "the sleep input of Samsung's score; it may differ from "
              'sleep.sessions (e.g. naps / split nights)'),
        ),
        note='day = local date of waking up',
    ),
    # ------------------------------------------------------------ mental
    Datatype(
        id='com.samsung.shealth.mood',
        category='mental', subkey='mood',
        friendly='Self-reported mood',
        fields=(
            F('mood_type', 'mood', '', 'enum:mood_type'),
            F('factors', 'factors', '', 'str',
              'mood factors as selected in the app'),
            F('emotions', 'emotions', '', 'str',
              'emotions as selected in the app'),
        ),
        note='free-text notes / place / company are not exported (privacy)',
    ),
    Datatype(
        id='com.samsung.shealth.breathing',
        category='mental', subkey='breathing_sessions',
        friendly='Guided breathing sessions',
        end_col='end_time',
        fields=(
            F('duration', 'duration_s', 's', 'nonneg',
              'seconds (180 s for 18 cycles in this export)'),
            F('cycle', 'cycles', 'count', 'int'),
            F('type', 'type', '', 'int',
              'Samsung breathing-exercise type code (undocumented)'),
            F('inhale_duration', 'inhale_duration', 'unverified'),
            F('exhale_duration', 'exhale_duration', 'unverified'),
            F('inhale_hold_duration', 'inhale_hold_duration', 'unverified'),
            F('exhale_hold_duration', 'exhale_hold_duration', 'unverified'),
        ),
    ),
    # ---------------------------------------------------------- exercise
    Datatype(
        id='com.samsung.shealth.exercise',
        category='exercise', subkey='sessions',
        friendly='Workout sessions incl. auto-detected walks (GPS removed)',
        prefix=_EX, end_col='end_time', handler='exercise',
        window_overlap=True, device=True,
        fields=(
            F('exercise_type', 'exercise_type', '', 'enum:exercise_type'),
            F('source_type', 'source', '', 'enum:exercise_source',
              'auto_detected = the phone/watch logged a walk on its own '
              '(no HR); user_started_workout = a deliberate workout'),
            F('duration', 'duration_ms', 'ms', 'nonneg',
              'active duration; excludes pauses, so it can be shorter '
              'than end_time - start_time'),
            F('distance', 'distance_m', 'm'),
            F('calorie', 'calories_kcal', 'kcal'),
            F('total_calorie', 'total_calories_kcal', 'kcal',
              note='incl. resting energy during the session'),
            F('mean_heart_rate', 'mean_hr', 'bpm'),
            F('max_heart_rate', 'max_hr', 'bpm'),
            F('min_heart_rate', 'min_hr', 'bpm'),
            F('mean_speed', 'mean_speed_mps', 'm/s'),
            F('max_speed', 'max_speed_mps', 'm/s'),
            F('mean_cadence', 'mean_cadence', 'steps/min'),
            F('max_cadence', 'max_cadence', 'steps/min'),
            F('vo2_max', 'vo2_max', 'mL/kg/min'),
            F('altitude_gain', 'altitude_gain_m', 'm'),
            F('altitude_loss', 'altitude_loss_m', 'm'),
            F('count', 'count', 'count', 'int'),
            F('count_type', 'count_type', '', 'enum:exercise_count_type'),
            F('sweat_loss', 'sweat_loss', 'mL'),
        ),
        binning=Binning(
            ref='live_data', dir_suffix='com.samsung.shealth.exercise',
            fields=(F('heart_rate', 'hr', 'bpm'),
                    F('cadence', 'cadence', 'steps/min'),
                    F('speed', 'speed_mps', 'm/s'),
                    F('distance', 'distance_m', 'm'),
                    F('calorie', 'calories_kcal', 'kcal'),
                    F('percent_of_vo2max', 'percent_of_vo2max', '%')),
            out='live_data',
        ),
        extra=(
            _DEVICE,
            X('resting_hr', 'bpm', 'resting HR the watch used for this '
              "session's HR zones"),
            X('running_dynamics', '', 'Myotest running metrics: per '
              'metric overall_score (Myotest 3-band rating 0/1/2; which '
              'end is better is undocumented), score_ratio_pct (% of the '
              'run in bands 0/1/2), mean_value over 10-s samples with data '
              '(Myotest units; contact/flight time appear to be ms)'),
            X('live_data', '', 'in-session samples (mostly HR; cadence/'
              'speed/distance when available); sub-second samples can '
              'share the same t'),
        ),
        nested=(('running_dynamics.<metric>', (
            X('overall_score', 'band 0/1/2', 'Myotest rating of the run'),
            X('score_ratio_pct', '%', '[band 0, band 1, band 2] share of '
              'the run'),
            X('mean_value', 'Myotest units', 'mean over 10-s samples'),
            X('samples', 'count', '10-s samples with data'))),),
    ),
    Datatype(
        id='com.samsung.shealth.exercise.max_heart_rate',
        category='exercise', subkey='max_heart_rate',
        friendly='Max HR + aerobic/anaerobic thresholds (settings snapshot)',
        fields=(
            F('max_heart_rate', 'max_hr', 'bpm', 'int'),
            F('at_heart_rate', 'aerobic_threshold_hr', 'bpm', 'int'),
            F('ant_heart_rate', 'anaerobic_threshold_hr', 'bpm', 'int'),
        ),
    ),
    Datatype(
        id='com.samsung.shealth.exercise.recovery_heart_rate',
        category='exercise', subkey='recovery_heart_rate',
        friendly='Post-exercise heart-rate recovery',
        end_col='end_time', handler='recovery_hr',
        fields=(),
        binning=Binning(
            ref='heart_rate',
            dir_suffix='com.samsung.shealth.exercise.recovery_heart_rate',
            out='recovery_samples',
        ),
        extra=(
            X('exercise_start_time', '', 'start_time of the workout in '
              'exercise.sessions this recovery belongs to'),
        ),
        nested=(('recovery_samples', (
            X('t', '', 'local time of the sample'),
            X('elapsed_ms', 'ms', 'time since the recovery measurement '
              'started'),
            X('hr', 'bpm', 'heart rate'))),),
    ),
    Datatype(
        id='com.samsung.shealth.exercise.hr_zone',
        category='exercise', subkey='hr_zone',
        friendly='Heart-rate zone thresholds (settings snapshot)',
        fields=(
            F('at', 'aerobic_threshold_hr', 'bpm'),
            F('ant', 'anaerobic_threshold_hr', 'bpm'),
            F('max_hr_auto', 'max_hr_auto', 'bpm'),
            F('max_hr_custom', 'max_hr_custom', 'bpm'),
        ),
    ),
    # --------------------------------------------------------- nutrition
    Datatype(
        id='com.samsung.health.nutrition',
        category='nutrition', subkey='macros',
        friendly='Per-meal nutrient totals',
        fields=(
            F('title', 'title', '', 'str', 'meal title as typed in the app'),
            F('meal_type', 'meal', '', 'enum:meal_type'),
            F('calorie', 'calorie', 'kcal'),
            F('protein', 'protein', 'g'),
            F('total_fat', 'total_fat', 'g'),
            F('saturated_fat', 'saturated_fat', 'g'),
            F('monosaturated_fat', 'monounsaturated_fat', 'g'),
            F('polysaturated_fat', 'polyunsaturated_fat', 'g'),
            F('trans_fat', 'trans_fat', 'g'),
            F('carbohydrate', 'carbohydrate', 'g'),
            F('sugar', 'sugar', 'g'),
            F('added_sugar', 'added_sugar', 'g', 'posfloat',
              'always 0 in the source -> treated as not recorded'),
            F('dietary_fiber', 'dietary_fiber', 'g'),
            F('cholesterol', 'cholesterol', 'mg'),
            F('sodium', 'sodium', 'mg'),
            F('potassium', 'potassium', 'mg'),
            F('calcium', 'calcium_pct_dv', '% daily value',
              note='Samsung SDK: "Calcium amount in percent"'),
            F('iron', 'iron_pct_dv', '% daily value'),
            F('vitamin_a', 'vitamin_a_pct_dv', '% daily value'),
            F('vitamin_c', 'vitamin_c_pct_dv', '% daily value'),
            F('vitamin_d', 'vitamin_d_pct_dv', '% daily value',
              note='unit undocumented; assumed % like vitamin A/C'),
        ),
    ),
    Datatype(
        id='com.samsung.health.food_intake',
        category='nutrition', subkey='meals',
        friendly='Meal log (names resolved from the food dictionary)',
        handler='food_intake',
        fields=(
            F('name', 'food_name', '', 'str'),
            F('meal_type', 'meal', '', 'enum:meal_type'),
            F('calorie', 'calorie', 'kcal'),
            F('amount', 'amount', 'see unit'),
            F('unit', 'unit', '', 'enum:food_unit'),
        ),
        extra=(X('food_name', '', '"quick add (calories only)" = a '
                 'calorie-only entry without a food'),),
    ),
    Datatype(
        id='com.samsung.health.water_intake',
        category='nutrition', subkey='water',
        friendly='Hydration',
        fields=(
            F('amount', 'amount_ml', 'ml'),
            F('unit_amount', 'glass_size_ml', 'ml'),
        ),
    ),
    # ----------------------------------------------------------- profile
    Datatype(
        id='com.samsung.health.user_profile',
        category='profile', subkey='',
        friendly='User profile (-> patient_profile header)',
        handler='user_profile', time_col='', offset_col='',
    ),
)


# Datatypes deliberately not exported, each with a reason. They still appear
# in the coverage manifest so nothing is dropped silently.
EXCLUDED: dict[str, tuple[str, str]] = {
    'com.samsung.shealth.exercise.weather':
        ('privacy', 'contains exact GPS coordinates'),
    'com.samsung.health.device_profile':
        ('privacy', 'device registry incl. Bluetooth address & device ids; '
                    'read internally only to label rows phone/watch'),
    'com.samsung.shealth.goal': ('config', 'user step/activity goals'),
    'com.samsung.shealth.service_preferences':
        ('config', 'app service preferences'),
    'com.samsung.shealth.preferences': ('config', 'app UI preferences'),
    'com.samsung.shealth.hsp.references':
        ('internal', 'internal id reference map'),
    'com.samsung.shealth.report':
        ('derived', 'weekly report roll-ups (raw data is exported instead)'),
    'com.samsung.shealth.badge': ('gamification', 'achievement badges'),
    'com.samsung.shealth.sleep_goal': ('config', 'target bedtime/wake'),
    'com.samsung.shealth.food_goal': ('config', 'nutrition targets'),
    'com.samsung.shealth.exercise.hr_zone.settings':
        ('config', 'which HR-zone model per sport'),
    'com.samsung.shealth.food_favorite':
        ('preferences', 'favourite foods'),
    'com.samsung.shealth.food_frequent':
        ('preferences', 'frequently logged foods'),
    'com.samsung.shealth.best_records':
        ('gamification', 'personal-best records'),
    'com.samsung.shealth.stress.histogram':
        ('internal', 'stress-algorithm calibration state, not a patient '
                     'measurement'),
    'com.samsung.shealth.exercise.extension':
        ('internal', 'links rows to workouts; carries no measurements'),
    'com.samsung.shealth.exercise.periodization_training_program':
        ('template', 'workout plan template'),
    'com.samsung.shealth.exercise.periodization_training_schedule':
        ('template', 'coaching schedule template'),
}

# Consumed by another handler rather than emitted on its own.
CONSUMED: dict[str, str] = {
    'com.samsung.health.sleep_stage': 'merged into sleep.sessions[].hypnogram',
    'com.samsung.health.food_info':
        'used to resolve food names in nutrition.meals',
}

# Companion JSON files under jsons/<datatype>/, keyed by datatype then by
# "kind" (the referencing column, namespace stripped). Anything not listed
# here is reported as UNKNOWN in the coverage manifest.
JSON_KINDS: dict[str, dict[str, tuple[str, str]]] = {
    'com.samsung.shealth.tracker.heart_rate': {
        'binning_data': ('consumed', 'heart_rate[].detail')},
    'com.samsung.health.hrv': {'binning_data': ('consumed', 'hrv[].detail')},
    'com.samsung.health.movement': {
        'binning_data': ('consumed', 'movement_intraday[].detail')},
    'com.samsung.health.respiratory_rate': {
        'binning_data': ('consumed', 'respiratory_rate[].detail')},
    'com.samsung.health.skin_temperature': {
        'binning_data': ('consumed', 'skin_temperature[].detail')},
    'com.samsung.shealth.stress': {
        'binning_data': ('consumed', 'stress.hourly[].detail')},
    'com.samsung.shealth.tracker.oxygen_saturation': {
        'binning': ('consumed', 'oxygen_saturation[].detail')},
    'com.samsung.shealth.exercise': {
        'live_data': ('consumed', 'exercise.sessions[].live_data'),
        'sensing_status': ('consumed', 'exercise.sessions[].resting_hr'),
        'additional_internal':
            ('consumed', 'exercise.sessions[].running_dynamics'),
        'live_data_internal':
            ('excluded', 'pause/interval markers for the app UI'),
        'location_data': ('excluded', 'privacy: GPS route'),
        'location_data_internal': ('excluded', 'privacy: GPS route'),
    },
    'com.samsung.shealth.exercise.recovery_heart_rate': {
        'heart_rate': ('consumed', 'recovery_heart_rate[].recovery_samples')},
    'com.samsung.shealth.tracker.pedometer_day_summary': {
        'binning_data': ('consumed', 'daily_steps[].detail_10min'),
        'source_info': ('excluded', 'internal: device ids per source'),
        'achievement': ('excluded', 'gamification: goal achievement'),
    },
    'com.samsung.shealth.step_daily_trend': {
        'binning_data': ('excluded', 'same 10-minute bins as '
                                     'daily_steps[].detail_10min')},
    'com.samsung.shealth.tracker.floors_day_summary': {
        'binning_data': ('excluded', '10-minute floor bins; daily totals '
                                     'and floors_intervals are exported')},
    'com.samsung.health.floors_climbed': {
        'raw_data': ('excluded', 'duplicates the CSV row (one value)')},
    'com.samsung.shealth.activity.day_summary': {
        'extra_data': ('excluded', '10-minute units overlap '
                       'daily_steps[].detail_10min; activity-recognition '
                       'segments use undocumented type codes; goals/streaks '
                       'are gamification')},
    'com.samsung.shealth.calories_burned.details': {
        'extra_data': ('excluded', 'profile snapshot (age/sex/height/'
                       'weight, see patient_profile) + per-activity split')},
    'com.samsung.shealth.heart_health_score': {
        'insight': ('excluded', 'free-text insight; empty (0 bytes) in '
                                'exports seen so far')},
    'com.samsung.health.device_profile': {
        'capability': ('excluded', 'privacy: device capabilities')},
    'com.samsung.health.user_profile': {
        'dashboard_config': ('excluded', 'config: app dashboard'),
        'home_tile_config': ('excluded', 'config: app home tiles'),
        'image': ('excluded', 'privacy: profile photo'),
    },
    'com.samsung.shealth.preferences': {
        'blob_value': ('excluded', 'config: app settings blobs')},
    'com.samsung.shealth.report': {
        'compressed_content': ('excluded', 'derived weekly reports')},
    'com.samsung.shealth.stress.histogram': {
        'histogram': ('excluded', 'internal stress calibration state')},
    'com.samsung.shealth.exercise.periodization_training_program': {
        'program': ('excluded', 'workout plan template')},
    'com.samsung.shealth.exercise.periodization_training_schedule': {
        'schedule': ('excluded', 'coaching schedule template')},
}


def by_id() -> dict[str, Datatype]:
    return {d.id: d for d in INCLUDED}
