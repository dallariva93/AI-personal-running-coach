"""Tests for the pure Garmin daily-wellness extractors (phase 0c)."""

from __future__ import annotations

from app.collection.wellness_snapshot import (
    _extract_body_battery,
    _extract_hrv,
    _extract_resting_hr,
    _extract_sleep,
    _extract_stress,
    _extract_training_readiness,
    build_wellness_snapshot,
)


def test_build_snapshot_fromFullPayloads_keepsNativeValues():
    snap = build_wellness_snapshot(
        "2026-07-08",
        sleep={"dailySleepDTO": {"sleepTimeSeconds": 27000,
                                 "sleepScores": {"overall": {"value": 82}}}},
        hrv={"hrvSummary": {"lastNightAvg": 65, "status": "BALANCED"}},
        stress={"avgStressLevel": 35},
        body_battery=[{"charged": 45, "drained": 60}],
        resting_hr={"allMetrics": {"metricsMap": {
            "WELLNESS_RESTING_HEART_RATE": [{"value": 48}]}}},
        training_readiness=[{"score": 72, "level": "READY"}],
    )

    assert snap.date == "2026-07-08"
    assert snap.sleep_seconds == 27000
    assert snap.sleep_score == 82
    assert snap.hrv_last_night_avg == 65.0
    assert snap.hrv_status == "BALANCED"
    assert snap.stress_avg == 35
    assert snap.body_battery_charged == 45
    assert snap.body_battery_drained == 60
    assert snap.resting_hr == 48
    assert snap.training_readiness_score == 72
    assert snap.training_readiness_level == "READY"
    assert snap.source == "garmin"
    assert not snap.is_empty()


def test_build_snapshot_allMissing_isEmpty():
    snap = build_wellness_snapshot("2026-07-08")
    assert snap.is_empty()
    assert snap.date == "2026-07-08"


def test_extract_sleep_missingOrGarbage_returnsNone():
    assert _extract_sleep(None) == (None, None)
    assert _extract_sleep({"dailySleepDTO": {}}) == (None, None)
    # Non-positive sleep time is rejected.
    assert _extract_sleep({"dailySleepDTO": {"sleepTimeSeconds": 0}}) == (None, None)


def test_extract_hrv_fallsBackToLastNightAverage_whenNoSummary():
    avg, status = _extract_hrv({"hrv": {"lastNight": [{"rmssd": 60}, {"rmssd": 70}]}})
    assert avg == 65.0
    assert status is None


def test_extract_stress_negativeSentinel_isNone():
    assert _extract_stress({"avgStressLevel": -1}) is None
    assert _extract_stress({"avgStressLevel": 42}) == 42


def test_extract_resting_hr_flatShape():
    assert _extract_resting_hr({"restingHeartRate": 50}) == 50
    # Zero/None are rejected as "no reading".
    assert _extract_resting_hr({"restingHeartRate": 0}) is None


def test_extract_body_battery_readsFirstDay():
    assert _extract_body_battery([{"charged": 30, "drained": 40}]) == (30, 40)
    assert _extract_body_battery([]) == (None, None)


def test_extract_training_readiness_bareDict():
    assert _extract_training_readiness({"score": 55, "level": "MODERATE"}) == (
        55,
        "MODERATE",
    )


def test_extractors_tolerateUnexpectedTypes_withoutRaising():
    # Booleans, strings, ints in place of dicts/lists must yield None, not crash.
    for bad in (True, "x", 5, [], {}, [123], {"hrvSummary": "nope"}):
        build_wellness_snapshot(
            "2026-07-08",
            sleep=bad,
            hrv=bad,
            stress=bad,
            body_battery=bad,
            resting_hr=bad,
            training_readiness=bad,
        )
