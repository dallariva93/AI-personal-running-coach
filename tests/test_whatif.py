"""What-if counterfactuals on the plan (Roadmap A7 / Passo 16).

Pure-function tests for the projection engine and the three scenarios, plus
service/endpoint tests proving zero DB writes. The forward EWMA is asserted
against the existing ``fitness_fatigue`` on known history (acceptance).
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import func, select

from app.db.models import (
    Activity,
    TrainingPlan,
    TrainingPlanSession,
    TrainingPlanWeek,
)
from app.processing.metrics import _daily_internal_loads, fitness_fatigue, project_form
from app.processing.whatif import (
    PlannedSession,
    WhatIfResult,
    simulate_scenario,
)
from app.schemas import RunSummary
from app.services.whatif_service import run_whatif

START = date(2026, 1, 5)  # a Monday
# ``ref`` sits in the final stretch: "mi ammalo una settimana" is the realistic,
# roadmap-intended framing — the upcoming week close to race day. There, removing
# the load drops recent fatigue (ATL, 7d) more than fitness (CTL, 42d), so the
# athlete arrives fresher (higher TSB) but underprepared (worse prediction).
REF = date(2026, 3, 22)
RACE = date(2026, 3, 30)   # 12-week plan end (goal day)


# ── Projection parity with the live metric (acceptance) ──────────────────────


def test_project_form_matches_fitness_fatigue_on_known_history():
    runs = [
        RunSummary(date=(START + timedelta(days=i)).isoformat(), activity_type="easy",
                   distance_km=10.0, duration_min=60.0)
        for i in range(0, 50, 2)
    ]
    ref = START + timedelta(days=55)
    assert project_form(_daily_internal_loads(runs, None, None), ref) == \
        fitness_fatigue(runs, ref=ref)


def test_project_form_empty_is_zero():
    assert project_form({}, REF) == (0.0, 0.0, 0.0)


# ── Pure scenarios ────────────────────────────────────────────────────────────


def _steady_history() -> dict[date, float]:
    # ~8 weeks of steady load up to REF.
    return {REF - timedelta(days=i): 250.0 for i in range(0, 56, 2)}


def _final_week_plan() -> list[PlannedSession]:
    """The remaining sessions between REF and RACE (the final ~week)."""
    return [
        PlannedSession(REF + timedelta(days=2), "tempo", 500.0),
        PlannedSession(REF + timedelta(days=4), "easy", 200.0),
        PlannedSession(REF + timedelta(days=6), "lungo", 600.0),
    ]


def test_skip_next_long_drops_one_long():
    planned = _final_week_plan()
    res = simulate_scenario("skip_next_long", _steady_history(), planned, REF, RACE, 2520.0)
    # Fitness a touch lower (dropped a big session) → prediction not faster.
    assert res.scenario_ctl_at_race <= res.baseline_ctl_at_race
    assert res.race_time_delta_seconds is not None and res.race_time_delta_seconds >= 0
    assert any("lungo" in n.lower() for n in res.risk_notes)


def test_sick_one_week_worse_prediction_and_higher_tsb():
    """Acceptance: a sick week → worse (slower) prediction AND higher TSB."""
    planned = _final_week_plan()
    res = simulate_scenario("sick_one_week", _steady_history(), planned, REF, RACE, 2520.0)
    assert res.scenario_ctl_at_race < res.baseline_ctl_at_race  # detrained
    assert res.race_time_delta_seconds > 0  # slower than baseline
    assert res.scenario_tsb_at_race > res.baseline_tsb_at_race  # less fatigue → higher TSB
    assert res.scenario_race_seconds > res.baseline_race_seconds


def test_add_training_day_raises_load():
    planned = _final_week_plan()
    res = simulate_scenario("add_training_day", _steady_history(), planned, REF, RACE, 2520.0)
    assert res.scenario_ctl_at_race >= res.baseline_ctl_at_race  # extra work → more fitness
    # A faster (or equal) projected time, never slower.
    assert res.race_time_delta_seconds is not None and res.race_time_delta_seconds <= 0


def test_add_training_day_full_week_is_noop():
    # Every day in the next week already has a session → nothing to add.
    full = [
        PlannedSession(REF + timedelta(days=i), "easy", 150.0) for i in range(1, 8)
    ]
    res = simulate_scenario("add_training_day", _steady_history(), full, REF, RACE, 2520.0)
    assert res.scenario_ctl_at_race == res.baseline_ctl_at_race
    assert any("piena" in n.lower() for n in res.risk_notes)


def test_no_prediction_still_projects_tsb():
    res = simulate_scenario("sick_one_week", _steady_history(), _final_week_plan(), REF, RACE, None)
    assert res.race_time_delta_seconds is None
    assert res.scenario_race_seconds is None
    assert isinstance(res.scenario_tsb_at_race, float)


def test_unknown_scenario_raises():
    with pytest.raises(ValueError):
        simulate_scenario("teleport", {}, [], REF, RACE, None)


def test_result_dataclass_shape():
    res = simulate_scenario(
        "skip_next_long", _steady_history(), _final_week_plan(), REF, RACE, 2520.0
    )
    assert isinstance(res, WhatIfResult) and res.scenario == "skip_next_long"


# ── Service + endpoint (zero persistence) ────────────────────────────────────


def _persist_plan(db) -> TrainingPlan:
    plan = TrainingPlan(
        goal_type="10k", goal_date=RACE.isoformat(), level="intermediate",
        weeks_total=12, start_date=START.isoformat(), status="active",
    )
    db.add(plan)
    db.flush()
    pattern = [(1, "tempo"), (3, "intervalli"), (5, "lungo"), (6, "rest")]
    for wk in range(1, 13):
        week = TrainingPlanWeek(plan_id=plan.id, week_number=wk, phase="Build", target_km=40.0)
        db.add(week)
        db.flush()
        for dow, stype in pattern:
            db.add(TrainingPlanSession(
                week_id=week.id, day_of_week=dow, session_type=stype,
                title=f"{stype} w{wk}", target_distance_km=None if stype == "rest" else 12.0,
                target_pace=None if stype == "rest" else "5:00",
            ))
    db.flush()
    return plan


def _seed_history(db) -> None:
    for i in range(0, 56, 2):
        db.add(Activity(date=(REF - timedelta(days=i)).isoformat(), sport="run",
                        activity_type="easy", distance_km=10.0, duration_min=60.0))
    db.flush()


def test_run_whatif_no_active_plan_returns_none(session):
    assert run_whatif(session, "sick_one_week", ref=REF) is None


def test_run_whatif_sick_week_no_db_writes(session):
    _persist_plan(session)
    _seed_history(session)
    before_sessions = session.scalar(select(func.count()).select_from(TrainingPlanSession))
    before_activities = session.scalar(select(func.count()).select_from(Activity))

    result = run_whatif(session, "sick_one_week", ref=REF)
    assert result is not None
    assert result.scenario == "sick_one_week"
    assert result.scenario_tsb_at_race > result.baseline_tsb_at_race
    assert result.risk_notes

    # Zero persistence (acceptance): counts unchanged, no dirty plan rows.
    assert session.scalar(select(func.count()).select_from(TrainingPlanSession)) == before_sessions
    assert session.scalar(select(func.count()).select_from(Activity)) == before_activities


def test_whatif_endpoint(client, session):
    _persist_plan(session)
    _seed_history(session)
    session.commit()

    resp = client.post("/api/plan/whatif", json={"scenario": "skip_next_long"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["scenario"] == "skip_next_long"
    assert "risk_notes" in body and "baseline_tsb_at_race" in body


def test_whatif_endpoint_rejects_unknown_scenario(client):
    resp = client.post("/api/plan/whatif", json={"scenario": "nope"})
    assert resp.status_code == 400


def test_whatif_endpoint_404_without_plan(client):
    resp = client.post("/api/plan/whatif", json={"scenario": "sick_one_week"})
    assert resp.status_code == 404
