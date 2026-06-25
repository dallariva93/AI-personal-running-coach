"""Unit tests for the race predictor and threshold evolution (Fase 4)."""

from __future__ import annotations

from datetime import date

from app.processing import compute_metrics, estimate_thresholds, predict_race_time
from app.processing.performance import seconds_to_time, time_to_seconds
from app.schemas import AthleteProfile, AthleteSnapshot, Goal, RunSummary

REF = date(2026, 6, 24)


def test_time_parsing_roundtrip():
    assert time_to_seconds("1:30:00") == 5400
    assert time_to_seconds("45:00") == 2700
    assert time_to_seconds(None) is None
    assert seconds_to_time(5400) == "1:30:00"
    assert seconds_to_time(2700) == "45:00"


def test_no_prediction_without_goal():
    assert predict_race_time(None, AthleteSnapshot()) is None


def test_prediction_low_confidence_without_efforts():
    goal = Goal(goal_type="marathon", target_date="2026-11-08", target_time="03:30:00")
    pred = predict_race_time(goal, AthleteSnapshot())
    assert pred is not None
    assert pred.confidence == "low"
    assert pred.predicted_time is None


def test_riegel_extrapolates_half_to_marathon():
    snap = AthleteSnapshot(best_half="1:35:00")
    goal = Goal(goal_type="marathon", target_date="2026-11-08", target_time="03:30:00")
    pred = predict_race_time(goal, snap)
    # Riegel: 95min * 2^1.06 ≈ 198min ≈ 3:18, comfortably under 3:30.
    assert pred.predicted_seconds < pred.target_seconds
    assert pred.probability > 0.5
    assert pred.confidence == "medium"


def test_probability_low_when_target_too_fast():
    snap = AthleteSnapshot(best_10k="50:00")
    goal = Goal(goal_type="10k", target_date="2026-08-01", target_time="00:40:00")
    pred = predict_race_time(goal, snap)
    assert pred.probability < 0.5  # 40' is well beyond a 50' runner


def test_efficiency_trend_shifts_prediction():
    snap = AthleteSnapshot(best_10k="45:00")
    goal = Goal(goal_type="10k", target_date="2026-08-01")
    faster = predict_race_time(goal, snap, "improving")
    slower = predict_race_time(goal, snap, "declining")
    assert faster.predicted_seconds < slower.predicted_seconds


def test_estimate_thresholds_from_hard_efforts():
    runs = [
        RunSummary(date="2026-06-10", distance_km=10, duration_min=42, activity_type="tempo"),
        RunSummary(date="2026-06-15", distance_km=8, duration_min=40, activity_type="gara"),
        RunSummary(date="2026-06-18", distance_km=12, duration_min=80, activity_type="easy"),
    ]
    phys = estimate_thresholds(runs, ref=REF)
    assert phys is not None
    # Fastest sustained hard pace = 42min/10km = 4:12/km.
    assert phys.lt2_pace == "4:12"


def test_estimate_thresholds_none_without_hard_efforts():
    runs = [RunSummary(date="2026-06-10", distance_km=8, duration_min=50, activity_type="easy")]
    assert estimate_thresholds(runs, ref=REF) is None


def test_metrics_expose_prediction():
    runs = [RunSummary(date="2026-06-01", distance_km=21.1, duration_min=95, activity_type="gara")]
    goal = Goal(goal_type="marathon", target_date="2026-11-08", target_time="03:30:00")
    m = compute_metrics(runs, ref=REF, profile=AthleteProfile(goal=goal))
    assert m.predicted_race_time is not None
    assert m.race_confidence in {"low", "medium", "high"}


def test_prediction_api(client):
    client.post("/api/ingest")
    assert client.get("/api/predict").status_code == 404  # no goal yet
    client.put(
        "/api/profile",
        json={"goal": {"goal_type": "marathon", "target_date": "2027-04-11",
                       "target_time": "03:30:00"}},
    )
    resp = client.get("/api/predict")
    assert resp.status_code == 200
    assert resp.json()["distance_km"] > 42


def test_ingest_autofills_thresholds(client):
    client.post("/api/ingest")  # demo data includes tempo/race efforts
    prof = client.get("/api/profile").json()
    # Physiology may be filled from the demo hard efforts (or stay empty if none).
    assert "physiology" in prof
