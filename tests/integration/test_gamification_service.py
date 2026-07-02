"""Integration tests for the adherence-aware gamification service (Roadmap Q4)."""

from __future__ import annotations

from datetime import date, timedelta

from app.db.models import Activity, TrainingPlan, TrainingPlanSession, TrainingPlanWeek
from app.services.execution_service import evaluate_plan_executions
from app.services.gamification_service import compute_gamification

REF = date(2026, 6, 24)  # Wednesday


def _plan(session, start: date, sessions: list[tuple[int, str, float | None]]) -> TrainingPlan:
    plan = TrainingPlan(
        goal_type="10k",
        goal_date="2026-12-31",
        level="intermediate",
        weeks_total=1,
        start_date=start.isoformat(),
        status="active",
    )
    session.add(plan)
    session.flush()
    week = TrainingPlanWeek(plan_id=plan.id, week_number=1, phase="Build", target_km=40.0)
    session.add(week)
    session.flush()
    for dow, st, km in sessions:
        session.add(
            TrainingPlanSession(
                week_id=week.id, day_of_week=dow, session_type=st, title=st, target_distance_km=km
            )
        )
    session.flush()
    return plan


def test_gamification_without_plan_uses_legacy_runs_streak(session):
    # compute_streak's "still alive" check is anchored to date.today() (no ref
    # param), so this one must use a real today's-date activity, not REF.
    today = date.today()
    session.add(
        Activity(date=today.isoformat(), sport="run", activity_type="easy", distance_km=8.0)
    )
    session.flush()
    data = compute_gamification(session, session.query(Activity).all())
    assert data.streak_kind == "runs"
    assert data.streak_days == 1


def test_gamification_with_plan_uses_adherence_streak(session):
    start = REF - timedelta(days=2)  # Monday
    _plan(
        session,
        start,
        [
            (0, "easy", 8.0),   # Mon: prescribed, will be completed
            (1, "rest", None),  # Tue: prescribed rest
            (2, "easy", 6.0),   # Wed (REF): prescribed, will be completed
        ],
    )
    session.add(
        Activity(date=start.isoformat(), sport="run", activity_type="easy", distance_km=8.0)
    )
    session.add(
        Activity(date=REF.isoformat(), sport="run", activity_type="easy", distance_km=6.0)
    )
    session.flush()
    evaluate_plan_executions(session, ref=REF)
    session.flush()

    data = compute_gamification(session, list(session.query(Activity).all()), ref=REF)
    assert data.streak_kind == "adherence"
    assert data.streak_days == 3  # Mon completed, Tue rest honoured, Wed completed


def test_gamification_hard_run_on_rest_day_breaks_adherence_streak(session):
    start = REF - timedelta(days=1)  # Tuesday
    _plan(
        session,
        start,
        [
            (1, "rest", None),   # Tue: prescribed rest
            (2, "easy", 6.0),    # Wed (REF): prescribed, will be completed
        ],
    )
    # A hard run lands on the rest day: breaks adherence.
    session.add(
        Activity(date=start.isoformat(), sport="run", activity_type="intervals", distance_km=10.0)
    )
    session.add(
        Activity(date=REF.isoformat(), sport="run", activity_type="easy", distance_km=6.0)
    )
    session.flush()
    evaluate_plan_executions(session, ref=REF)
    session.flush()

    data = compute_gamification(session, list(session.query(Activity).all()), ref=REF)
    assert data.streak_kind == "adherence"
    assert data.streak_days == 1  # only today (Wed) survives


def test_gamification_endpoint_exposes_streak_kind(client):
    resp = client.post("/api/ingest")
    assert resp.status_code == 200
    body = client.get("/api/gamification").json()
    assert body["streak_kind"] in {"adherence", "runs"}
