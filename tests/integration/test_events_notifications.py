"""Integration: coach audit event log (#5) + notifications (#6)."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from app.collection.sources import DemoSource
from app.db.models import DailyCheckinRow, TrainingPlan, TrainingPlanSession, TrainingPlanWeek
from app.services.adaptive_plan import adapt_plan_after_sync
from app.services.decision_service import build_today_decision, record_decision_notification
from app.services.event_service import (
    mark_notified,
    pending_notifications,
    recent_events,
)
from app.services.ingest import ingest_runs

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _this_monday(today: date | None = None) -> date:
    """Monday of the current week — a stable weekday anchor inside any
    lookback window, so tests don't expire as the calendar moves on."""
    today = today or date.today()
    return today - timedelta(days=today.weekday())



def _seed_runs(session) -> None:
    ingest_runs(session, source=DemoSource(FIXTURES / "garmin_activities.json"))
    session.flush()


def _plan(session, start: date) -> None:
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
            week_id=week.id, day_of_week=2, session_type="intervals",
            title="Ripetute", target_distance_km=12.0,
        )
    )
    session.flush()


def test_adaptation_writes_audit_event_with_before_after(session):
    start = _this_monday()
    _seed_runs(session)
    _plan(session, start)
    session.add(
        DailyCheckinRow(date=start.isoformat(), fatigue=9, soreness=10, sleep_h=4.0)
    )
    session.flush()

    adapt_plan_after_sync(session, ref=start)

    events = recent_events(session, days=60)
    adapt = [e for e in events if e.event_type == "plan_adapted"]
    assert adapt, "expected a plan_adapted audit event"
    e = adapt[0]
    # It records what/why/before/after.
    assert e.before is not None and e.after is not None
    assert e.before["session_type"] == "intervals"
    assert e.after["session_type"] == "easy"
    assert e.signals  # the 'why' signals
    assert e.notifiable is True


def test_adaptation_event_is_deduped(session):
    start = _this_monday()
    _seed_runs(session)
    _plan(session, start)
    session.add(DailyCheckinRow(date=start.isoformat(), fatigue=9, soreness=10, sleep_h=4.0))
    session.flush()

    adapt_plan_after_sync(session, ref=start)
    n1 = len([e for e in recent_events(session, days=60) if e.event_type == "plan_adapted"])
    # Re-running with the same state must not duplicate the event.
    adapt_plan_after_sync(session, ref=start)
    n2 = len([e for e in recent_events(session, days=60) if e.event_type == "plan_adapted"])
    assert n1 == n2


def test_decision_notification_and_ack(session):
    _seed_runs(session)
    session.add(DailyCheckinRow(date="2026-06-22", fatigue=9, soreness=10, sleep_h=4.0))
    session.flush()
    decision = build_today_decision(session, ref=_this_monday())
    record_decision_notification(session, decision)

    pend = pending_notifications(session)
    assert pend, "a red-readiness decision should be notifiable"
    assert pend[0].body

    # Acking removes it from the pending list.
    mark_notified(session, [pend[0].id])
    assert not pending_notifications(session)


def test_routine_decision_not_notified(session):
    _seed_runs(session)
    # Healthy check-in → routine easy day → no notification.
    session.add(
        DailyCheckinRow(date="2026-06-22", fatigue=2, sleep_h=8.0, motivation=8, hrv_rmssd=60.0)
    )
    session.flush()
    decision = build_today_decision(session, ref=_this_monday())
    record_decision_notification(session, decision)
    assert not pending_notifications(session)


def test_events_and_notifications_endpoints(client):
    client.post("/api/ingest")
    client.post(
        "/api/checkin",
        json={"date": date.today().isoformat(), "fatigue": 9, "soreness": 10, "sleep_h": 4},
    )
    client.post("/api/ingest")

    assert client.get("/api/coach/events").status_code == 200
    notes = client.get("/api/notifications").json()
    assert client.get("/api/mobile/overview").json().get("notifications") is not None
    if notes:
        r = client.post("/api/notifications/ack", json={"ids": [notes[0]["id"]]})
        assert r.json()["acked"] >= 1


def test_action_logs_audit_event(client):
    client.post("/api/ingest")
    client.post("/api/coach/today/action", json={"action": "problem", "detail": "pain"})
    events = client.get("/api/coach/events").json()
    assert any(e["event_type"] == "action" for e in events)
