"""Rolling-horizon re-plan (Fase D): future weeks refresh, history is immutable."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select

from app.db.models import TrainingPlan
from app.services.replan_service import replan_future_weeks

_PAYLOAD = {
    "goal_type": "marathon",
    "goal_date": "2027-04-18",  # far → a full 24-week block
    "goal_time": "3:45:00",
    "level": "intermediate",
    "days_per_week": 4,
    "long_run_day": 6,
}


def _active(session) -> TrainingPlan:
    return session.scalar(select(TrainingPlan).where(TrainingPlan.status == "active"))


def _session_ids(plan) -> dict[int, set[int]]:
    return {w.week_number: {s.id for s in w.sessions} for w in plan.weeks}


def test_generate_persists_replan_inputs(client, session):
    client.post("/api/plan/generate", json=_PAYLOAD)
    plan = _active(session)
    assert plan.days_per_week == 4
    assert plan.long_run_day == 6
    assert plan.baseline_km is not None


def test_replan_preserves_past_and_replaces_future(client, session):
    client.post("/api/plan/generate", json=_PAYLOAD)
    plan = _active(session)
    start = date.fromisoformat(plan.start_date)
    before = _session_ids(plan)

    ref = start + timedelta(weeks=3)  # current week = 4
    result = replan_future_weeks(session, ref=ref)
    session.commit()

    assert result["replanned"] > 0
    plan = _active(session)
    after = _session_ids(plan)

    # Past + current weeks (1..4) keep their exact sessions.
    for wn in range(1, 5):
        assert after[wn] == before[wn], f"week {wn} should be immutable"
    # At least one future week was rebuilt (new session ids), goal-race week aside.
    changed = [wn for wn in after if wn > 4 and after[wn] != before[wn]]
    assert changed, "future weeks should be re-derived"


def test_replan_skips_weeks_with_a_completed_session(client, session):
    client.post("/api/plan/generate", json=_PAYLOAD)
    plan = _active(session)
    start = date.fromisoformat(plan.start_date)

    # Mark a session in a far-future week (week 10) completed.
    week10 = next(w for w in plan.weeks if w.week_number == 10)
    target = next(s for s in week10.sessions if s.session_type != "rest")
    target.completed = True
    session.flush()
    keep_ids = {s.id for s in week10.sessions}

    replan_future_weeks(session, ref=start + timedelta(weeks=3))
    session.commit()

    plan = _active(session)
    week10 = next(w for w in plan.weeks if w.week_number == 10)
    assert {s.id for s in week10.sessions} == keep_ids  # untouched


def test_replan_no_future_weeks_is_noop(client, session):
    client.post("/api/plan/generate", json=_PAYLOAD)
    plan = _active(session)
    start = date.fromisoformat(plan.start_date)
    # ref past the end → current week clamps to the last one, no future left.
    result = replan_future_weeks(session, ref=start + timedelta(weeks=40))
    assert result["replanned"] == 0


def test_reconstruct_request_infers_from_sessions_for_legacy_plans(session):
    """Plans created before the inputs were persisted still re-plan (inference)."""
    from app.db.models import TrainingPlanSession, TrainingPlanWeek
    from app.services.replan_service import _reconstruct_request

    plan = TrainingPlan(
        goal_type="10k", goal_date="2027-01-10", level="intermediate",
        weeks_total=1, start_date="2026-06-22", status="active",
    )  # days_per_week / long_run_day / runner_context all None (legacy)
    session.add(plan)
    session.flush()
    wk = TrainingPlanWeek(plan_id=plan.id, week_number=1, phase="Base", target_km=40.0)
    session.add(wk)
    session.flush()
    for dow, t in {0: "rest", 1: "intervals", 2: "easy", 3: "tempo",
                   4: "rest", 5: "easy", 6: "long"}.items():
        session.add(
            TrainingPlanSession(week_id=wk.id, day_of_week=dow, session_type=t, title=t)
        )
    session.flush()
    session.refresh(plan)

    req = _reconstruct_request(plan)
    assert req.days_per_week == 5  # 5 non-rest days inferred (dow 1,2,3,5,6)
    assert req.long_run_day == 6  # long run on Sunday
    assert req.goal_type == "10k"


def test_maybe_replan_weekly_guards_against_repeats(client, session):
    """The auto-trigger re-plans at most once per weekly window."""
    from app.services.replan_service import maybe_replan_weekly

    client.post("/api/plan/generate", json=_PAYLOAD)
    plan = _active(session)
    start = date.fromisoformat(plan.start_date)
    ref = start + timedelta(weeks=3)

    first = maybe_replan_weekly(session, ref=ref)
    session.commit()
    assert first["replanned"] > 0  # first pass re-plans and logs the event

    second = maybe_replan_weekly(session, ref=ref + timedelta(days=2))
    assert second["replanned"] == 0  # within the window → skipped
    assert second.get("skipped") == "recent"


def test_replan_endpoint_refreshes_and_404_without_plan(client):
    # No plan yet.
    assert client.post("/api/plan/replan").status_code == 404
    # With a plan, it returns the refreshed plan.
    client.post("/api/plan/generate", json=_PAYLOAD)
    resp = client.post("/api/plan/replan")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "active"
    assert len(body["weeks"]) == body["weeks_total"]
