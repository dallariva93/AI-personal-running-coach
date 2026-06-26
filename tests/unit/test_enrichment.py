"""Tests for the detail-endpoint enrichment parsers.

These cover the gap that left real Garmin activities sparse: the rich metrics
live on the per-activity detail endpoints, nested under ``summaryDTO``.
"""

from __future__ import annotations

from app.collection.synthesize import (
    extract_details_enrichment,
    extract_hr_zones_from_timezones,
    extract_splits,
    extract_weather,
)


def test_extract_details_enrichment_from_summary_dto():
    """A realistic get_activity payload yields the full rich field set."""
    details = {
        "activityId": 99,
        "vO2MaxValue": 54.0,
        "summaryDTO": {
            "activityTrainingLoad": 180.0,
            "averageTemperature": 19.5,
            "elevationLoss": 42.0,
            "vigorousIntensityMinutes": 12.0,
            "moderateIntensityMinutes": 20.0,
            "differenceBodyBattery": -18,
            "avgGradeAdjustedSpeed": 3.4,  # m/s
            "fastestSplit_1000": 270,  # seconds for the fastest km
            "fastestSplit_5000": 1425,
            "aerobicTrainingEffect": 3.6,
            "anaerobicTrainingEffect": 1.4,
            "aerobicTrainingEffectMessage": "IMPROVING_LACTATE_THRESHOLD_31",
            "anaerobicTrainingEffectMessage": "MINOR_ANAEROBIC_BENEFIT_8",
            "beginPotentialStamina": 100.0,
            "endPotentialStamina": 70.0,
            "directWorkoutRpe": 60,
            "hrTimeInZone_1": 120,
            "hrTimeInZone_2": 600,
            "hrTimeInZone_3": 540,
            "hrTimeInZone_4": 480,
            "hrTimeInZone_5": 60,
        },
    }
    out = extract_details_enrichment(details)

    assert out["vo2max"] == 54.0
    assert out["garmin_training_load"] == 180.0
    assert out["temperature_c"] == 19.5
    assert out["elevation_loss_m"] == 42.0
    assert out["vigorous_minutes"] == 12.0
    assert out["moderate_minutes"] == 20.0
    assert out["body_battery_delta"] == -18
    assert out["aerobic_training_effect"] == 3.6
    assert out["anaerobic_training_effect"] == 1.4
    assert out["aerobic_te_message"] == "IMPROVING_LACTATE_THRESHOLD_31"
    assert out["avg_grade_adjusted_pace"].endswith("/km")
    assert out["fastest_split_1k"].endswith("/km")
    assert out["rpe"] == 6
    assert out["stamina_drop"] == 30.0
    assert out["hr_zones"] == {"z1": 2.0, "z2": 10.0, "z3": 9.0, "z4": 8.0, "z5": 1.0}


def test_extract_details_enrichment_ignores_garbage():
    assert extract_details_enrichment({}) == {}
    assert extract_details_enrichment("nope") == {}  # type: ignore[arg-type]


def test_extract_hr_zones_from_timezones():
    payload = [
        {"zoneNumber": 1, "secsInZone": 120.0},
        {"zoneNumber": 2, "secsInZone": 600.0},
        {"zoneNumber": 3, "secsInZone": 0.0},
    ]
    assert extract_hr_zones_from_timezones(payload) == {"z1": 2.0, "z2": 10.0, "z3": 0.0}
    assert extract_hr_zones_from_timezones(None) is None
    assert extract_hr_zones_from_timezones([]) is None


def test_extract_splits():
    payload = {
        "lapDTOs": [
            {"distance": 1000.0, "duration": 300.0},
            {"distance": 1000.0, "duration": 288.0},
            {"distance": 120.0, "duration": 40.0},  # trailing partial, skipped
        ]
    }
    splits = extract_splits(payload)
    assert splits == ["5:00/km", "4:48/km"]
    assert extract_splits({}) is None
    assert extract_splits(None) is None


def test_extract_weather_humidity_only():
    assert extract_weather({"relativeHumidity": 64, "temp": 70}) == {"humidity_pct": 64.0}
    assert extract_weather(None) == {}
