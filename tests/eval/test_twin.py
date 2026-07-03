"""Digital Twin v0 — 5 end-to-end scenarios (Roadmap A5 / Passo 13).

Each scenario seeds a synthetic history in the DB, runs the orchestrator
:func:`estimate_athlete_model`, and asserts the learned constant (and, for the
recovery case, that the decision engine actually consumes it). Deterministic:
part of the ``not eval_llm`` eval job.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.db.models import (
    Activity,
    DailyCheckinRow,
    TrainingPlan,
    TrainingPlanSession,
    TrainingPlanWeek,
)
from app.processing.digital_twin import build_athlete_model
from app.services.athlete_model_service import (
    estimate_athlete_model,
    save_athlete_model,
)
from app.services.decision_service import build_today_decision

START = date(2026, 1, 5)  # a Monday


def _run(db, d: date, km: float, atype: str = "easy", **kw) -> None:
    db.add(Activity(
        date=d.isoformat(), sport="run", activity_type=atype,
        distance_km=km, duration_min=km * 6, **kw,
    ))


def _green(db, d: date) -> None:
    db.add(DailyCheckinRow(date=d.isoformat(), sleep_h=8.0, fatigue=1,
                           soreness=1, motivation=8, hrv_rmssd=70.0))


def _red(db, d: date) -> None:
    db.add(DailyCheckinRow(date=d.isoformat(), sleep_h=3.0, fatigue=10,
                           soreness=10, motivation=2, hrv_rmssd=20.0))


# ── Scenario 1: ramp collapse at 12% → learned tolerance < 12% ───────────────


def test_scenario_ramp_collapse_below_12(session):
    loads = [40, 42, 45.4, 49.9, 55.9, 63.7, 60, 63, 66]  # +5/+8/+10/+12/+14/…
    for i, load in enumerate(loads):
        _run(session, START + timedelta(days=7 * i), load)
    # The two biggest jumps (+12%, +14%) are followed by a red-readiness week.
    _red(session, START + timedelta(days=7 * 5 + 1))
    _red(session, START + timedelta(days=7 * 6 + 1))
    session.flush()

    model = estimate_athlete_model(session, ref=START + timedelta(days=70))
    assert model.ramp_tolerance_pct.value < 12.0
    assert model.ramp_tolerance_pct.learning is False


# ── Scenario 2: recovers in 3 days → learned half-life 3 ─────────────────────


def _plan_with_too_hard(db, too_hard_weeks: list[int]) -> TrainingPlan:
    plan = TrainingPlan(
        goal_type="10k", goal_date=(START + timedelta(days=56)).isoformat(),
        level="intermediate", weeks_total=8, start_date=START.isoformat(),
        status="active",
    )
    db.add(plan)
    db.flush()
    for wk in range(1, 9):
        week = TrainingPlanWeek(plan_id=plan.id, week_number=wk, phase="Build", target_km=40.0)
        db.add(week)
        db.flush()
        sess = TrainingPlanSession(
            week_id=week.id, day_of_week=0, session_type="intervals",
            title=f"intervals w{wk}", target_distance_km=8.0, target_pace="4:30",
        )
        if wk in too_hard_weeks:
            sess.execution_status = "too_hard"
            sess.execution_score = 45.0
        db.add(sess)
    db.flush()
    return plan


def test_scenario_recovery_halflife_three(session):
    _plan_with_too_hard(session, [1, 2, 3])
    # Each too-hard Monday is followed by a green readiness day exactly 3 days later.
    for wk in (1, 2, 3):
        effort = START + timedelta(days=(wk - 1) * 7)
        _green(session, effort + timedelta(days=3))
    session.flush()

    model = estimate_athlete_model(session, ref=START + timedelta(days=40))
    assert model.recovery_halflife_days.value == 3.0
    assert model.recovery_halflife_days.learning is False


# ── Scenario 3: heat sensitivity learned from hot easy runs ──────────────────


def test_scenario_heat_sensitivity_learned(session):
    # 12 easy runs, GAP = 300 + 3*(temp-15): true slope 3 s/km per °C.
    temps = [16, 18, 20, 22, 24, 26, 17, 19, 21, 23, 25, 27]
    for i, t in enumerate(temps):
        gap = 300 + 3 * (t - 15)
        m, s = divmod(int(gap), 60)
        _run(session, START + timedelta(days=i), 10.0, "easy",
             temperature_c=float(t), avg_grade_adjusted_pace=f"{m}:{s:02d}/km")
    session.flush()

    model = estimate_athlete_model(session, ref=START + timedelta(days=20))
    assert model.heat_sensitivity_s_per_c.learning is False
    assert 2.5 < model.heat_sensitivity_s_per_c.value < 3.5


# ── Scenario 4: thin history → safe population defaults ──────────────────────


def test_scenario_thin_history_uses_defaults(session):
    _run(session, START, 40.0)
    _run(session, START + timedelta(days=7), 42.0)
    session.flush()

    model = estimate_athlete_model(session, ref=START + timedelta(days=14))
    assert model.ramp_tolerance_pct.learning is True
    assert model.recovery_halflife_days.learning is True
    assert model.heat_sensitivity_s_per_c.learning is True
    assert model.ramp_tolerance_pct.value == 10.0  # never a reckless number


# ── Scenario 5: the learned recovery drives the decision engine ──────────────


def test_scenario_learned_recovery_gates_quality(session):
    # Learn half-life 3 and persist it.
    model = build_athlete_model([], [3, 3, 3], [], computed_at=START.isoformat())
    save_athlete_model(session, model)

    # An active plan whose today's session is quality, one day after a hard run.
    plan = TrainingPlan(
        goal_type="10k", goal_date=(START + timedelta(days=56)).isoformat(),
        level="intermediate", weeks_total=8, start_date=START.isoformat(),
        status="active",
    )
    session.add(plan)
    session.flush()
    week = TrainingPlanWeek(plan_id=plan.id, week_number=1, phase="Build", target_km=40.0)
    session.add(week)
    session.flush()
    # Tuesday (day_of_week=1) is an intervals day → that is "today".
    session.add(TrainingPlanSession(
        week_id=week.id, day_of_week=1, session_type="intervals",
        title="8x400", target_distance_km=8.0, target_pace="4:30",
    ))
    # A hard effort yesterday (Monday) so recovery is 1 day in (< half-life 3).
    _run(session, START, 8.0, "tempo")
    _green(session, START + timedelta(days=1))
    session.flush()

    decision = build_today_decision(session, ref=START + timedelta(days=1), persist=False)
    assert decision.decision != "quality"  # gated by the learned recovery window
