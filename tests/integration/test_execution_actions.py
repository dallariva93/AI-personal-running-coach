"""Integration: execution scoring on the plan + actionable Today decision."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from app.collection.sources import DemoSource
from app.db.models import TrainingPlan, TrainingPlanSession, TrainingPlanWeek
from app.schemas import RunSummary
from app.services.decision_service import apply_coach_action, build_today_decision
from app.services.execution_service import evaluate_plan_executions, recent_executions
from app.services.ingest import ingest_runs, upsert_activity

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _seed_runs(session) -> None:
    ingest_runs(session, source=DemoSource(FIXTURES / "garmin_activities.json"))
    session.flush()


def _plan_with_session(session, start: date, dow: int, st: str, km: float) -> TrainingPlan:
    plan = TrainingPlan(
        goal_type="10k",
        goal_date=(start + timedelta(days=40)).isoformat(),
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
    session.add(
        TrainingPlanSession(
            week_id=week.id, day_of_week=dow, session_type=st, title=st, target_distance_km=km
        )
    )
    session.flush()
    return plan


def test_execution_scored_and_autocompletes(session):
    start = date(2026, 6, 22)  # Monday
    _plan_with_session(session, start, dow=0, st="easy", km=8.0)
    # An activity on the session's date that matches the prescription.
    upsert_activity(
        session,
        RunSummary(
            date=start.isoformat(),
            activity_type="easy",
            distance_km=8.0,
            duration_min=48.0,
        ),
    )
    session.flush()

    results = evaluate_plan_executions(session, ref=start)
    assert results
    sess = session.query(TrainingPlanSession).filter_by(day_of_week=0).one()
    assert sess.execution_status == "completed_well"
    assert sess.completed is True  # reality marks it done
    assert sess.executed_activity_id is not None

    # And it surfaces via the recent-executions listing.
    listed = recent_executions(session, days=30)
    assert any(x.plan_session_id == sess.id for x in listed)


def test_missing_activity_marks_skipped(session):
    start = date(2026, 6, 22)
    _plan_with_session(session, start, dow=0, st="tempo", km=10.0)
    # No activity on that date, and it's in the past.
    results = evaluate_plan_executions(session, ref=start + timedelta(days=1))
    sess = session.query(TrainingPlanSession).filter_by(day_of_week=0).one()
    assert sess.execution_status == "skipped"
    assert results


def test_action_done_completes_session(session):
    start = date(2026, 6, 22)
    _seed_runs(session)
    _plan_with_session(session, start, dow=0, st="easy", km=8.0)
    # P0-3: "done" needs evidence — an explicit RPE (or a matching activity).
    apply_coach_action(session, "done", rpe=5, ref=start)
    sess = session.query(TrainingPlanSession).filter_by(day_of_week=0).one()
    assert sess.completed is True


def test_action_done_without_evidence_is_rejected(session):
    """P0-3: a bare 'done' with no activity and no RPE must be refused."""
    import pytest

    start = date(2026, 6, 22)
    _seed_runs(session)
    _plan_with_session(session, start, dow=0, st="easy", km=8.0)
    with pytest.raises(ValueError, match="attivita|RPE"):
        apply_coach_action(session, "done", ref=start)


def test_action_reduce_cuts_volume(session):
    start = date(2026, 6, 22)
    _seed_runs(session)
    _plan_with_session(session, start, dow=0, st="tempo", km=10.0)
    apply_coach_action(session, "reduce", ref=start)
    sess = session.query(TrainingPlanSession).filter_by(day_of_week=0).one()
    assert sess.base_target_distance_km == 10.0
    assert sess.target_distance_km == 7.0


def test_action_problem_softens_decision(session):
    start = date(2026, 6, 22)
    _seed_runs(session)
    _plan_with_session(session, start, dow=0, st="intervals", km=10.0)
    decision = apply_coach_action(session, "problem", detail="pain", ref=start)
    # A pain signal on a hard day should not leave a hard prescription standing.
    assert decision.decision in {"modify", "rest", "easy"}
    assert decision.safety_flags


def test_action_endpoint(client):
    client.post("/api/ingest")
    r = client.post("/api/coach/today/action", json={"action": "problem", "detail": "tired"})
    assert r.status_code == 200
    assert r.json()["daily_note"]


def test_invalid_action_rejected(client):
    client.post("/api/ingest")
    r = client.post("/api/coach/today/action", json={"action": "explode"})
    assert r.status_code == 422


def test_daily_note_present_in_decision(session):
    _seed_runs(session)
    d = build_today_decision(session, ref=date(2026, 6, 22))
    assert d.daily_note
