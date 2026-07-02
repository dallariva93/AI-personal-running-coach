"""Tests for readiness check-ins, day scheduling, multi-race and weather/trail."""

from __future__ import annotations

from datetime import date

from app.coaching.coach import OfflineCoach
from app.coaching.prompts import goal_context
from app.collection.synthesize import synthesize
from app.processing import compute_metrics
from app.processing.recovery import readiness
from app.schemas import AthleteProfile, DailyCheckin, Goal, Race, RunSummary

REF = date(2026, 6, 24)


def _run(d: str, km: float, t: str = "easy") -> RunSummary:
    return RunSummary(date=d, distance_km=km, activity_type=t, duration_min=km * 6)


# -- Readiness (GAP 9) ------------------------------------------------------
def test_readiness_unknown_without_checkin():
    assert readiness(None) == (None, "unknown")


def test_readiness_green_when_rested():
    c = DailyCheckin(date="2026-06-24", sleep_h=8, fatigue=2, soreness=1, motivation=9)
    score, state = readiness(c)
    assert state == "green" and score >= 70


def test_readiness_red_when_wrecked():
    c = DailyCheckin(date="2026-06-24", sleep_h=4, fatigue=9, soreness=8, motivation=2)
    score, state = readiness(c)
    assert state == "red" and score < 40


def test_metrics_expose_readiness():
    c = DailyCheckin(date="2026-06-24", sleep_h=5, fatigue=8, soreness=7, motivation=3)
    m = compute_metrics([_run("2026-06-23", 10)], ref=REF, checkin=c)
    assert m.readiness_state in {"red", "amber"}


def test_red_readiness_forces_deload():
    goal = Goal(goal_type="marathon", target_date="2026-12-06")
    runs = [_run(f"2026-06-{d:02d}", 6) for d in range(1, 24, 3)]
    profile = AthleteProfile(goal=goal)
    c = DailyCheckin(date="2026-06-24", sleep_h=4, fatigue=10, soreness=9, motivation=1)
    m = compute_metrics(runs, ref=REF, profile=profile, checkin=c)
    text = OfflineCoach().plan_week(runs, m, [], profile).next_workout.lower()
    assert "scarico" in text


# -- Available-days scheduling (GAP 15) -------------------------------------
def test_offline_plan_uses_available_days():
    runs = [_run(f"2026-06-{d:02d}", 6) for d in range(1, 24, 3)]
    profile = AthleteProfile(available_days=["Monday", "Wednesday", "Friday", "Sunday"])
    m = compute_metrics(runs, ref=REF, profile=profile)
    text = OfflineCoach().plan_week(runs, m, [], profile).next_workout
    assert "Lun:" in text and "Mer:" in text and "Ven:" in text


# -- Multi-race A/B/C (GAP 16) ----------------------------------------------
def test_goal_context_lists_secondary_races():
    profile = AthleteProfile(
        goal=Goal(goal_type="marathon", target_date="2099-04-11"),
        races=[
            Race(race_type="half", date="2099-02-01", priority="B"),
            Race(race_type="10k", date="2099-01-10", priority="C"),
        ],
    )
    ctx = goal_context(profile)
    assert "secondarie" in ctx.lower()
    assert "half" in ctx and "10k" in ctx


def test_profile_races_round_trip(session):
    from app.services import get_profile, save_profile

    save_profile(
        session,
        AthleteProfile(races=[Race(race_type="half", date="2027-03-01", priority="B")]),
    )
    session.commit()
    loaded = get_profile(session)
    assert loaded is not None and len(loaded.races) == 1
    assert loaded.races[0].priority == "B"


# -- Weather & trail capture (GAP 18/20) ------------------------------------
def test_synthesize_captures_weather_and_descent():
    raw = {
        "activityId": 1, "startTimeLocal": "2026-06-24 07:00:00",
        "distance": 10000, "duration": 3000,
        "temperature": 28.0, "humidity": 75, "elevationLoss": 220,
    }
    run = synthesize(raw)
    assert run.temperature_c == 28.0
    assert run.humidity_pct == 75
    assert run.elevation_loss_m == 220
    assert run.start_time == "07:00"  # Q6: local start time captured


def test_offline_run_analysis_flags_heat():
    run = _run("2026-06-24", 10)
    run.temperature_c = 30
    run.humidity_pct = 80
    m = compute_metrics([run], ref=REF)
    analysis = OfflineCoach().analyze_run(run, [], m).analysis.lower()
    assert "caldo" in analysis


# -- Check-in persistence API ----------------------------------------------
def test_checkin_api_round_trip(client):
    payload = {"date": "2026-06-24", "sleep_h": 7.5, "fatigue": 3, "motivation": 8}
    resp = client.post("/api/checkin", json=payload)
    assert resp.status_code == 201
    assert client.get("/api/checkin").json()["fatigue"] == 3


def test_ui_checkin_form(client):
    resp = client.post(
        "/ui/checkin",
        data={"sleep_h": "8", "fatigue": "2", "soreness": "1", "motivation": "9"},
    )
    assert resp.status_code == 200
    assert "Check-in salvato" in resp.text
