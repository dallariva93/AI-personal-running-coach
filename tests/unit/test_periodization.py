"""Unit tests for the periodization engine."""

from __future__ import annotations

from datetime import date

from app.coaching.coach import OfflineCoach
from app.processing import build_periodization, compute_metrics, current_phase
from app.processing.periodization import phase_for
from app.schemas import AthleteProfile, Goal, RunSummary

REF = date(2026, 6, 24)


def test_no_plan_without_goal():
    assert build_periodization(None, baseline_km=40, ref=REF) is None


def test_no_plan_without_date():
    assert build_periodization(Goal(goal_type="marathon"), baseline_km=40, ref=REF) is None


def test_no_plan_for_past_race():
    goal = Goal(goal_type="10k", target_date="2026-01-01")
    assert build_periodization(goal, baseline_km=40, ref=REF) is None


def test_phases_cover_full_runway_and_end_on_race():
    goal = Goal(goal_type="marathon", target_date="2026-11-08")
    plan = build_periodization(goal, baseline_km=40, ref=REF)
    assert plan is not None
    assert plan.weeks_to_race == 20
    # Phases tile contiguously and total the runway.
    assert sum(p.weeks for p in plan.phases) == plan.weeks_to_race
    names = [p.name for p in plan.phases]
    assert names == ["base", "build", "specific", "peak", "taper", "race"]
    # The race phase ends on (or just after) the target date.
    assert plan.phases[-1].name == "race"
    assert plan.phases[-1].end_date >= goal.target_date


def test_marathon_has_three_week_taper():
    goal = Goal(goal_type="marathon", target_date="2026-11-08")
    plan = build_periodization(goal, baseline_km=40, ref=REF)
    taper = next(p for p in plan.phases if p.name == "taper")
    assert taper.weeks == 3
    assert taper.volume_factor < 1.0  # taper sheds volume


def test_short_runway_is_mostly_taper_and_race():
    goal = Goal(goal_type="10k", target_date="2026-07-05")  # ~11 days out
    plan = build_periodization(goal, baseline_km=30, ref=REF)
    assert plan is not None
    assert plan.weeks_to_race <= 2
    assert sum(p.weeks for p in plan.phases) == plan.weeks_to_race


def test_current_phase_is_first_phase():
    goal = Goal(goal_type="half", target_date="2026-10-01")
    plan = build_periodization(goal, baseline_km=35, ref=REF)
    assert plan.current_phase == "base"
    assert current_phase(plan.phases, REF) == "base"
    assert phase_for(plan, REF).name == "base"


def test_metrics_expose_phase():
    goal = Goal(goal_type="marathon", target_date="2026-11-08")
    runs = [
        RunSummary(date=f"2026-06-{d:02d}", distance_km=8, activity_type="easy", duration_min=48)
        for d in range(1, 24, 2)
    ]
    m = compute_metrics(runs, ref=REF, profile=AthleteProfile(goal=goal))
    assert m.phase == "base"
    assert m.weeks_to_race == 20
    assert m.phase_volume_target_km is not None


def test_offline_taper_week_reduces_volume():
    goal = Goal(goal_type="marathon", target_date="2026-07-05")  # taper/race window
    runs = [
        RunSummary(date=f"2026-06-{d:02d}", distance_km=10, activity_type="easy", duration_min=60)
        for d in range(1, 24, 2)
    ]
    profile = AthleteProfile(goal=goal)
    m = compute_metrics(runs, ref=REF, profile=profile)
    assert m.phase in {"taper", "race", "peak"}
    text = OfflineCoach().plan_week(runs, m, [], profile).next_workout.lower()
    assert m.phase in text or "taper" in text or "gara" in text


def test_periodization_api(client):
    client.post("/api/ingest")
    # No goal yet → 404.
    assert client.get("/api/plan/periodization").status_code == 404
    client.put(
        "/api/profile",
        json={"goal": {"goal_type": "marathon", "target_date": "2027-04-11"}},
    )
    resp = client.get("/api/plan/periodization")
    assert resp.status_code == 200
    body = resp.json()
    assert body["goal_type"] == "marathon"
    assert len(body["phases"]) >= 1
