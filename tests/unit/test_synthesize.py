"""Unit tests for the collection/synthesize layer."""

from __future__ import annotations

from app.collection.synthesize import (
    _classify_by_training_effect,
    _format_pace,
    _has_walking_pauses,
    _infer_type,
    _stamina_drop,
    extract_details_enrichment,
    extract_rpe_from_details,
    synthesize,
)


def test_format_pace_basic():
    # 5 km in 1500 s -> 5:00/km
    assert _format_pace(5000, 1500) == "5:00/km"


def test_format_pace_rounding_carry():
    # pace that rounds up to a full minute should carry correctly
    assert _format_pace(1000, 359.6) == "6:00/km"


def test_format_pace_zero_returns_none():
    assert _format_pace(0, 100) is None
    assert _format_pace(100, 0) is None


def test_infer_type_from_name():
    assert _infer_type({"activityName": "Tempo run"}) == "tempo"
    assert _infer_type({"activityName": "Long run"}) == "lungo"
    assert _infer_type({"activityName": "6x800 intervals"}) == "intervalli"
    assert _infer_type({"activityName": "Morning jog"}) == "easy"


# ---- name hints -----------------------------------------------------------

def test_infer_type_name_hint_ripetute_italian():
    # Italian name keyword should win even with an aerobic-base TE label.
    activity = {
        "activityName": "Ripetute 6x800",
        "trainingEffectLabel": "LACTATE_THRESHOLD",
        "distance": 8000,
    }
    assert _infer_type(activity) == "intervalli"


# ---- lungo by distance ----------------------------------------------------

def test_infer_type_long_trail_run_is_trail_when_elevation_high():
    # The 15.7 km hot trail run with significant elevation → trail
    # (terrain trumps both distance and the misleading VO2MAX label).
    activity = {
        "activityName": "Lozzo Atestino Trail Running",
        "activityType": {"typeKey": "trail_running"},
        "distance": 15734.0,
        "elevationGain": 420.0,
        "trainingEffectLabel": "VO2MAX",
        "anaerobicTrainingEffect": 3.5,
        "aerobicTrainingEffect": 5.0,
    }
    assert _infer_type(activity) == "trail"


def test_infer_type_long_run_without_elevation_stays_lungo():
    # A 16 km flat road run → lungo, not trail.
    activity = {
        "activityName": "Corsa",
        "activityType": {"typeKey": "running"},
        "distance": 16000.0,
        "elevationGain": 30.0,
    }
    assert _infer_type(activity) == "lungo"


def test_infer_type_below_lungo_threshold_does_not_promote():
    activity = {"activityName": "Corsa", "distance": 13_500.0}
    assert _infer_type(activity) == "easy"


# ---- trail by elevation / typeKey -----------------------------------------

def test_infer_type_trail_by_elevation_gain():
    # Short run but with significant climbing → trail.
    activity = {
        "activityName": "Corsa pomeridiana",
        "distance": 7000.0,
        "elevationGain": 200.0,
    }
    assert _infer_type(activity) == "trail"


def test_infer_type_trail_below_elevation_threshold_is_not_trail():
    activity = {
        "activityName": "Corsa pomeridiana",
        "distance": 7000.0,
        "elevationGain": 100.0,
    }
    assert _infer_type(activity) == "easy"


def test_infer_type_garmin_trail_running_type_wins():
    # Garmin explicitly tagged the sport as trail_running → trail even
    # without much elevation reported.
    activity = {
        "activityName": "Corsa pomeridiana",
        "activityType": {"typeKey": "trail_running"},
        "distance": 6000.0,
        "elevationGain": 40.0,
    }
    assert _infer_type(activity) == "trail"


# ---- walking pauses -------------------------------------------------------

def test_has_walking_pauses_detects_walk_splittype():
    activity = {
        "splitSummaries": [
            {"splitType": "RWD_RUN", "duration": 1500.0},
            {"splitType": "RWD_WALK", "duration": 180.0},
        ]
    }
    assert _has_walking_pauses(activity) is True


def test_has_walking_pauses_ignores_short_walks():
    activity = {
        "splitSummaries": [
            {"splitType": "RWD_WALK", "duration": 25.0},  # < 60 s, traffic light
        ]
    }
    assert _has_walking_pauses(activity) is False


def test_has_walking_pauses_handles_missing_field():
    assert _has_walking_pauses({}) is False
    assert _has_walking_pauses({"splitSummaries": None}) is False


def test_infer_type_walking_pauses_force_intervalli():
    # 8x400 with walking recovery: Garmin averages to LACTATE_THRESHOLD,
    # but the walks reveal the interval structure.
    activity = {
        "activityName": "Corsa pomeridiana",
        "distance": 7400.0,
        "trainingEffectLabel": "LACTATE_THRESHOLD",
        "anaerobicTrainingEffect": 1.8,
        "splitSummaries": [
            {"splitType": "RWD_RUN", "duration": 1800.0},
            {"splitType": "RWD_WALK", "duration": 400.0},
        ],
    }
    assert _infer_type(activity) == "intervalli"


# ---- training-effect signals ----------------------------------------------

def test_classify_by_training_effect_anaerobic_high():
    assert (
        _classify_by_training_effect(
            {"anaerobicTrainingEffect": 3.0, "trainingEffectLabel": "TEMPO"}
        )
        == "intervalli"
    )


def test_classify_by_training_effect_label_maps():
    assert _classify_by_training_effect({"trainingEffectLabel": "AEROBIC_BASE"}) == "easy"
    # Garmin's TEMPO label is a Z3 steady-state → Italian ``medio``.
    assert _classify_by_training_effect({"trainingEffectLabel": "TEMPO"}) == "medio"
    # The threshold-based tempo run in our terminology.
    assert (
        _classify_by_training_effect({"trainingEffectLabel": "LACTATE_THRESHOLD"}) == "tempo"
    )
    # VO2MAX without anaerobic push → sustained supra-threshold = tempo.
    assert _classify_by_training_effect({"trainingEffectLabel": "VO2MAX"}) == "tempo"
    assert (
        _classify_by_training_effect({"trainingEffectLabel": "ANAEROBIC_CAPACITY"})
        == "intervalli"
    )
    assert _classify_by_training_effect({"trainingEffectLabel": "RECOVERY"}) == "recupero"


def test_classify_by_training_effect_aerobic_fallback():
    # No label, no anaerobic push, but a strong aerobic effect → medio
    # (conservative: we can't confirm it sat at threshold without the label).
    assert (
        _classify_by_training_effect(
            {"aerobicTrainingEffect": 4.0, "anaerobicTrainingEffect": 0.5}
        )
        == "medio"
    )


def test_classify_by_training_effect_returns_none_when_silent():
    assert _classify_by_training_effect({}) is None
    assert (
        _classify_by_training_effect(
            {"aerobicTrainingEffect": 2.0, "anaerobicTrainingEffect": 0.1}
        )
        is None
    )


# ---- end-to-end realistic payloads ---------------------------------------

def test_infer_type_real_garmin_tempo_label_is_medio():
    # Garmin TEMPO label on a 5 km Z3-dominant effort → medio, not tempo.
    activity = {
        "activityName": "Padova Corsa",
        "distance": 5155.0,
        "trainingEffectLabel": "TEMPO",
        "anaerobicTrainingEffect": 0.5,
        "aerobicTrainingEffect": 3.6,
    }
    assert _infer_type(activity) == "medio"


def test_infer_type_feel_based_z3_z4_8km_is_medio():
    # The user's scenario: "corsa a sentimento" ~8 km with HR varying
    # between Z3 and Z4. Garmin typically labels it TEMPO with moderate
    # aerobic effect and low anaerobic → medio.
    activity = {
        "activityName": "Corsa pomeridiana",
        "distance": 8000.0,
        "elevationGain": 40.0,
        "trainingEffectLabel": "TEMPO",
        "anaerobicTrainingEffect": 1.5,
        "aerobicTrainingEffect": 4.0,
    }
    assert _infer_type(activity) == "medio"


def test_infer_type_real_time_trial_is_tempo_not_intervalli():
    # The user's 2026-06-04 session: 9.3 km all-out time trial. Garmin tags
    # VO2MAX, anaerobic stays low (0.8) because the effort is continuous, no
    # walks. Closest bucket in our taxonomy is ``tempo``, not ``intervalli``.
    activity = {
        "activityName": "Padova Corsa",
        "distance": 9275.0,
        "elevationGain": 25.0,
        "trainingEffectLabel": "VO2MAX",
        "anaerobicTrainingEffect": 0.8,
        "aerobicTrainingEffect": 5.0,
        "splitSummaries": [
            {"splitType": "RWD_RUN", "duration": 2520.0},
            {"splitType": "RWD_WALK", "duration": 2.5},
        ],
    }
    assert _infer_type(activity) == "tempo"


def test_infer_type_defaults_to_easy_when_nothing_screams():
    activity = {
        "activityName": "Corsa pomeridiana",
        "distance": 5500.0,
        "trainingEffectLabel": "AEROBIC_BASE",
        "aerobicTrainingEffect": 2.5,
        "anaerobicTrainingEffect": 0.0,
    }
    assert _infer_type(activity) == "easy"


# ---- RPE extraction -------------------------------------------------------

def test_extract_rpe_divides_garmin_scale_by_10():
    # Garmin stores 10-100 on the watch; we map to 1-10.
    assert extract_rpe_from_details({"summaryDTO": {"directWorkoutRpe": 70}}) == 7
    assert extract_rpe_from_details({"summaryDTO": {"directWorkoutRpe": 90}}) == 9
    assert extract_rpe_from_details({"summaryDTO": {"directWorkoutRpe": 20}}) == 2


def test_extract_rpe_rounds_intermediate_values():
    assert extract_rpe_from_details({"summaryDTO": {"directWorkoutRpe": 55}}) == 6


def test_extract_rpe_clamps_to_valid_range():
    assert extract_rpe_from_details({"summaryDTO": {"directWorkoutRpe": 5}}) == 1
    assert extract_rpe_from_details({"summaryDTO": {"directWorkoutRpe": 150}}) == 10


def test_extract_rpe_returns_none_when_missing_or_zero():
    assert extract_rpe_from_details({}) is None
    assert extract_rpe_from_details({"summaryDTO": {}}) is None
    assert extract_rpe_from_details({"summaryDTO": {"directWorkoutRpe": 0}}) is None
    assert extract_rpe_from_details({"summaryDTO": {"directWorkoutRpe": None}}) is None


def test_extract_rpe_handles_malformed_payload():
    assert extract_rpe_from_details({"summaryDTO": "not a dict"}) is None
    assert extract_rpe_from_details({"summaryDTO": {"directWorkoutRpe": "abc"}}) is None


def test_synthesize_maps_core_fields(raw_activities):
    activity = next(a for a in raw_activities if a["activityId"] == 9003)
    run = synthesize(activity)
    assert run.garmin_activity_id == "9003"
    assert run.date == "2026-06-03"
    assert run.activity_type == "tempo"
    assert run.distance_km == 10.0
    assert run.duration_min == 48.0
    assert run.avg_pace == "4:48/km"
    assert run.avg_hr == 162
    assert run.max_hr == 178


def test_synthesize_hr_zones_converted_to_minutes(raw_activities):
    activity = next(a for a in raw_activities if a["activityId"] == 9001)
    run = synthesize(activity)
    assert run.hr_zones is not None
    # zone2 was 1700 seconds -> ~28.3 minutes
    assert run.hr_zones["z2"] == 28.3
