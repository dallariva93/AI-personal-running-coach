"""Behavioural-trigger gate scenarios (Roadmap A1 / Passo 11).

Each trigger must fire on its synthetic pattern and NEVER more than once per
weekly dedupe window. These run in the deterministic eval job (no LLM).
"""

from __future__ import annotations

from datetime import date, timedelta

from app.db.models import (
    Activity,
    CoachEvent,
    DailyCheckinRow,
    TrainingPlan,
    TrainingPlanSession,
    TrainingPlanWeek,
)
from app.services.decision_service import apply_coach_action
from app.services.execution_service import evaluate_plan_executions
from app.services.triggers import evaluate_triggers

# A Monday so weekday-based day_of_week maps onto the calendar cleanly.
START = date(2026, 1, 5)


def _plan(db, weeks: int = 2, pattern=None) -> TrainingPlan:
    pattern = pattern or [(0, "easy"), (1, "tempo"), (2, "easy"), (3, "intervals"),
                          (4, "rest"), (5, "long"), (6, "easy")]
    plan = TrainingPlan(
        goal_type="10k", goal_date=(START + timedelta(days=weeks * 7)).isoformat(),
        level="intermediate", weeks_total=weeks, start_date=START.isoformat(), status="active",
    )
    db.add(plan)
    db.flush()
    for wk in range(1, weeks + 1):
        week = TrainingPlanWeek(plan_id=plan.id, week_number=wk, phase="Build", target_km=40.0)
        db.add(week)
        db.flush()
        for dow, stype in pattern:
            db.add(TrainingPlanSession(
                week_id=week.id, day_of_week=dow, session_type=stype,
                title=f"{stype} w{wk}", target_distance_km=None if stype == "rest" else 8.0,
                target_pace=None if stype == "rest" else "5:00",
            ))
    db.flush()
    return plan


def _events(db, trigger: str) -> list[CoachEvent]:
    return [
        e for e in db.query(CoachEvent).filter_by(event_type="trigger").all()
        if (e.after or {}).get("trigger") == trigger
    ]


# ── Trigger 1: re-engage after a skipped session ─────────────────────────────


def test_reengage_fires_once_when_yesterday_skipped(session):
    _plan(session)
    # Tue (START+1) is a prescribed tempo; leave it with no activity, then score
    # from Wed so it is marked "skipped". Wed itself has no run either.
    ref = START + timedelta(days=2)  # Wed
    evaluate_plan_executions(session, ref=ref)

    created = evaluate_triggers(session, ref=ref)
    triggers = [e for e in created if (e.after or {}).get("trigger") == "reengage"]
    assert len(triggers) == 1
    assert triggers[0].notifiable and triggers[0].priority == "medium"

    # Skipping a second day the same week must NOT re-fire (weekly dedupe).
    ref2 = START + timedelta(days=3)  # Thu, intervals prescribed, also skipped
    evaluate_plan_executions(session, ref=ref2)
    evaluate_triggers(session, ref=ref2)
    assert len(_events(session, "reengage")) == 1


def test_reengage_silent_when_today_has_a_run(session):
    _plan(session)
    ref = START + timedelta(days=2)
    evaluate_plan_executions(session, ref=ref)
    session.add(Activity(date=ref.isoformat(), sport="run", activity_type="easy",
                         distance_km=6.0, duration_min=36.0))
    session.flush()
    created = evaluate_triggers(session, ref=ref)
    assert not [e for e in created if (e.after or {}).get("trigger") == "reengage"]


# ── Trigger 2: recalibrate after repeated too-hard executions ────────────────


def test_recalibrate_fires_on_three_too_hard(session):
    _plan(session)
    ref = START + timedelta(days=6)
    # Mark three past sessions as executed too hard (within the 10-day window).
    hard = session.query(TrainingPlanSession).filter(
        TrainingPlanSession.day_of_week.in_([0, 1, 3]), TrainingPlanSession.week_id == 1
    ).all()
    for s in hard:
        s.execution_status = "too_hard"
    session.flush()

    created = evaluate_triggers(session, ref=ref)
    recal = [e for e in created if (e.after or {}).get("trigger") == "recalibrate"]
    assert len(recal) == 1 and recal[0].after["actions"] == ["recalibrate"]

    # Re-running the same window must not re-fire (weekly dedupe). ref is a
    # Sunday, so ref-1 stays inside the same ISO week.
    evaluate_triggers(session, ref=ref - timedelta(days=1))
    assert len(_events(session, "recalibrate")) == 1


def test_recalibrate_silent_under_threshold(session):
    _plan(session)
    ref = START + timedelta(days=6)
    two = session.query(TrainingPlanSession).filter(
        TrainingPlanSession.day_of_week.in_([0, 1]), TrainingPlanSession.week_id == 1
    ).all()
    for s in two:
        s.execution_status = "too_hard"
    session.flush()
    created = evaluate_triggers(session, ref=ref)
    assert not [e for e in created if (e.after or {}).get("trigger") == "recalibrate"]


def test_recalibrate_action_loosens_future_paces(session):
    _plan(session)
    ref = START + timedelta(days=6)
    before = {
        s.id: s.target_pace
        for s in session.query(TrainingPlanSession).filter(
            TrainingPlanSession.target_pace.is_not(None)
        ).all()
    }
    apply_coach_action(session, "recalibrate", ref=ref)
    for s in session.query(TrainingPlanSession).all():
        d = START + timedelta(days=(_week_of(s, session) - 1) * 7 + s.day_of_week)
        if s.target_pace and d >= ref and before.get(s.id) == "5:00":
            assert s.target_pace == "5:05"  # +5 s/km on future sessions


def _week_of(sess, db) -> int:
    week = db.get(TrainingPlanWeek, sess.week_id)
    return week.week_number


# ── Trigger 3: HRV below baseline for >=5 consecutive days ───────────────────


def test_hrv_watch_fires_on_five_low_days(session):
    ref = START + timedelta(days=30)
    # 24 days of healthy HRV establish the personal baseline, then 5 low days.
    for offset in range(30, 5, -1):
        d = ref - timedelta(days=offset)
        session.add(DailyCheckinRow(date=d.isoformat(), hrv_rmssd=62.0 + (offset % 3)))
    for offset in range(4, -1, -1):  # last 5 days (incl. ref): clearly low
        d = ref - timedelta(days=offset)
        session.add(DailyCheckinRow(date=d.isoformat(), hrv_rmssd=24.0))
    session.flush()

    created = evaluate_triggers(session, ref=ref)
    hrv = [e for e in created if (e.after or {}).get("trigger") == "hrv_watch"]
    assert len(hrv) == 1 and hrv[0].priority == "medium"

    evaluate_triggers(session, ref=ref + timedelta(days=1))
    assert len(_events(session, "hrv_watch")) == 1


def test_hrv_watch_silent_when_recovered(session):
    ref = START + timedelta(days=30)
    for offset in range(30, -1, -1):
        d = ref - timedelta(days=offset)
        session.add(DailyCheckinRow(date=d.isoformat(), hrv_rmssd=62.0 + (offset % 3)))
    session.flush()
    created = evaluate_triggers(session, ref=ref)
    assert not [e for e in created if (e.after or {}).get("trigger") == "hrv_watch"]
