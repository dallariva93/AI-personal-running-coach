"""Integration: Coach Decision Engine persistence + adaptive plan after sync."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from app.collection.sources import DemoSource
from app.db.models import (
    DailyCheckinRow,
    TrainingPlan,
    TrainingPlanSession,
    TrainingPlanWeek,
)
from app.services.adaptive_plan import adapt_plan_after_sync
from app.services.decision_service import (
    build_today_decision,
    recent_decisions,
    session_on_date,
)
from app.services.ingest import ingest_runs

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _this_monday(today: date | None = None) -> date:
    """Monday of the current week — a stable weekday anchor inside any
    lookback window, so tests don't expire as the calendar moves on."""
    today = today or date.today()
    return today - timedelta(days=today.weekday())


def _seed_runs(session) -> None:
    """Populate real activities so compute_metrics yields live signals."""
    ingest_runs(session, source=DemoSource(FIXTURES / "garmin_activities.json"))
    session.flush()


def _make_plan(session, start: date) -> TrainingPlan:
    plan = TrainingPlan(
        goal_type="10k",
        goal_date=(start + timedelta(days=56)).isoformat(),
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
    # A hard session and an easy session, both in the coming days.
    for dow, st, km in [(0, "intervals", 10.0), (2, "easy", 8.0), (4, "tempo", 12.0)]:
        session.add(
            TrainingPlanSession(
                week_id=week.id,
                day_of_week=dow,
                session_type=st,
                title=f"{st} session",
                target_distance_km=km,
            )
        )
    session.flush()
    return plan


def test_build_today_decision_persists(session):
    # Anchor to the current week's Monday: `recent_decisions` only looks back
    # 30 days, so a hardcoded date silently stops being covered by the window
    # once enough time has passed.
    ref = _this_monday()
    d = build_today_decision(session, ref=ref)
    assert d.decision
    # Persisted and retrievable.
    hist = recent_decisions(session, days=30)
    assert any(x.date == ref.isoformat() for x in hist)


def test_session_on_date_maps_weekday(session):
    start = date(2026, 6, 22)  # a Monday
    _make_plan(session, start)
    from app.services.plan_service import get_current_plan

    plan = get_current_plan(session)
    # Wednesday of week 1 → the easy session (day_of_week 2).
    s = session_on_date(plan, start + timedelta(days=2))
    assert s is not None
    assert s.session_type == "easy"


def test_adaptive_plan_eases_hard_sessions_when_unwell(session):
    start = date(2026, 6, 22)
    _seed_runs(session)
    _make_plan(session, start)
    # Red readiness check-in today → adapter should ease imminent quality work.
    session.add(
        DailyCheckinRow(
            date=start.isoformat(), sleep_h=4.0, fatigue=9, soreness=8, motivation=2
        )
    )
    session.flush()

    summary = adapt_plan_after_sync(session, ref=start)
    assert summary["adjusted"] >= 1

    # The Monday intervals session should now be an easy session, with a note,
    # and its original type preserved in base_session_type.
    hard = session.query(TrainingPlanSession).filter_by(day_of_week=0).one()
    assert hard.session_type == "easy"
    assert hard.base_session_type == "intervals"
    assert hard.adjustment_note


def test_adaptive_plan_is_idempotent(session):
    start = date(2026, 6, 22)
    _seed_runs(session)
    _make_plan(session, start)
    session.add(DailyCheckinRow(date=start.isoformat(), sleep_h=4.0, fatigue=9))
    session.flush()

    adapt_plan_after_sync(session, ref=start)
    tempo = session.query(TrainingPlanSession).filter_by(day_of_week=4).one()
    km_after_first = tempo.target_distance_km

    # Running again must not compound the reduction.
    adapt_plan_after_sync(session, ref=start)
    tempo2 = session.query(TrainingPlanSession).filter_by(day_of_week=4).one()
    assert tempo2.target_distance_km == km_after_first


def test_adaptive_plan_restores_intensity_when_recovered(session):
    start = date(2026, 6, 22)
    _seed_runs(session)
    _make_plan(session, start)
    # First: unwell → eases.
    row = DailyCheckinRow(
        date=start.isoformat(), sleep_h=4.0, fatigue=9, soreness=8, motivation=2
    )
    session.add(row)
    session.flush()
    adapt_plan_after_sync(session, ref=start)
    assert session.query(TrainingPlanSession).filter_by(day_of_week=0).one().session_type == "easy"

    # Then: recovered → restores original intensity from base.
    row.fatigue = 2
    row.sleep_h = 8.0
    row.soreness = 1
    row.motivation = 8
    session.flush()
    adapt_plan_after_sync(session, ref=start)
    restored = session.query(TrainingPlanSession).filter_by(day_of_week=0).one()
    assert restored.session_type == "intervals"


def test_adaptive_no_plan_is_noop(session):
    assert adapt_plan_after_sync(session, ref=date(2026, 6, 22)) == {
        "adjusted": 0,
        "factor": 1.0,
        "notes": [],
    }


def test_coach_today_endpoint(client):
    client.post("/api/ingest")
    resp = client.get("/api/coach/today")
    assert resp.status_code == 200
    body = resp.json()
    assert body["decision"]
    assert "signals" in body and "confidence" in body


def test_overview_includes_today_decision(client):
    client.post("/api/ingest")
    ov = client.get("/api/mobile/overview").json()
    assert "today_decision" in ov
    assert ov["today_decision"]["headline"]
