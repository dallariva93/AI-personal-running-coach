"""Calendar plan editor (Roadmap #12): moving sessions with safety recalc."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.db.models import TrainingPlan, TrainingPlanSession, TrainingPlanWeek
from app.services.event_service import recent_events
from app.services.plan_service import move_session

# Default weekly skeleton used by the test plans (dow → type).
_WEEK = {0: "rest", 1: "intervals", 2: "easy", 3: "tempo", 4: "rest", 5: "easy", 6: "long"}


def _next_monday() -> date:
    today = date.today()
    return today + timedelta(days=(7 - today.weekday()) % 7 or 7)


def _mk_plan(db, start: date, weeks: int = 2, race_last_sunday: bool = False):
    plan = TrainingPlan(
        goal_type="10k",
        goal_date=(start + timedelta(days=weeks * 7 - 1)).isoformat(),
        level="intermediate",
        weeks_total=weeks,
        start_date=start.isoformat(),
        status="active",
    )
    db.add(plan)
    db.flush()
    for w in range(1, weeks + 1):
        week = TrainingPlanWeek(plan_id=plan.id, week_number=w, phase="Base", target_km=40.0)
        db.add(week)
        db.flush()
        for dow, stype in _WEEK.items():
            if race_last_sunday and w == weeks and dow == 6:
                stype = "race"
            db.add(
                TrainingPlanSession(
                    week_id=week.id,
                    day_of_week=dow,
                    session_type=stype,
                    title=stype.capitalize(),
                    target_distance_km=None if stype == "rest" else 8.0,
                )
            )
    db.flush()
    db.expire(plan)
    return plan


def _find(db, plan, week_no: int, dow: int) -> TrainingPlanSession:
    week = next(w for w in plan.weeks if w.week_number == week_no)
    return next(s for s in week.sessions if s.day_of_week == dow)


def test_move_swaps_with_rest_day_no_warnings(session):
    start = _next_monday()
    plan = _mk_plan(session, start)
    tempo = _find(session, plan, 1, 3)
    target = start + timedelta(days=4)  # week 1, dow 4 (rest)

    result = move_session(session, tempo.id, target.isoformat(), ref=start)

    assert result.warnings == []
    week1 = next(w for w in result.plan.weeks if w.week_number == 1)
    by_dow = {s.day_of_week: s for s in week1.sessions}
    assert by_dow[4].session_type == "tempo"
    assert by_dow[3].session_type == "rest"
    # Still exactly 7 sessions in the week.
    assert len(week1.sessions) == 7


def test_move_next_to_quality_returns_warning(session):
    start = _next_monday()
    plan = _mk_plan(session, start)
    intervals = _find(session, plan, 1, 1)
    target = start + timedelta(days=2)  # dow 2, adjacent to tempo on dow 3

    result = move_session(session, intervals.id, target.isoformat(), ref=start)

    assert any("qualità" in w for w in result.warnings)


def test_cross_week_move_swaps_weeks(session):
    start = _next_monday()
    plan = _mk_plan(session, start)
    intervals = _find(session, plan, 1, 1)
    target = start + timedelta(days=7)  # week 2, dow 0 (rest)

    result = move_session(session, intervals.id, target.isoformat(), ref=start)

    week1 = next(w for w in result.plan.weeks if w.week_number == 1)
    week2 = next(w for w in result.plan.weeks if w.week_number == 2)
    assert {s.day_of_week: s.session_type for s in week2.sessions}[0] == "intervals"
    assert {s.day_of_week: s.session_type for s in week1.sessions}[1] == "rest"
    assert len(week1.sessions) == 7 and len(week2.sessions) == 7
    # Quality right after week 1's Sunday long run → warned.
    assert any("lungo" in w for w in result.warnings)


def test_completed_and_race_sessions_do_not_move(session):
    start = _next_monday()
    plan = _mk_plan(session, start, race_last_sunday=True)

    done = _find(session, plan, 1, 1)
    done.completed = True
    session.flush()
    with pytest.raises(ValueError, match="completata"):
        move_session(session, done.id, (start + timedelta(days=4)).isoformat(), ref=start)

    race = _find(session, plan, 2, 6)
    with pytest.raises(ValueError, match="gara"):
        move_session(session, race.id, (start + timedelta(days=4)).isoformat(), ref=start)

    # Nor can anything land on the race day.
    tempo = _find(session, plan, 1, 3)
    with pytest.raises(ValueError, match="gara"):
        move_session(session, tempo.id, (start + timedelta(days=13)).isoformat(), ref=start)


def test_target_outside_plan_or_in_past_rejected(session):
    start = _next_monday()
    plan = _mk_plan(session, start)
    tempo = _find(session, plan, 1, 3)

    with pytest.raises(ValueError, match="fuori dal piano"):
        move_session(session, tempo.id, (start + timedelta(days=60)).isoformat(), ref=start)
    with pytest.raises(ValueError, match="passato"):
        move_session(
            session,
            tempo.id,
            (start + timedelta(days=1)).isoformat(),
            ref=start + timedelta(days=3),
        )
    with pytest.raises(ValueError, match="non valida"):
        move_session(session, tempo.id, "not-a-date", ref=start)


def test_move_to_same_day_is_noop(session):
    start = _next_monday()
    plan = _mk_plan(session, start)
    tempo = _find(session, plan, 1, 3)
    result = move_session(session, tempo.id, (start + timedelta(days=3)).isoformat(), ref=start)
    assert result.warnings == []
    week1 = next(w for w in result.plan.weeks if w.week_number == 1)
    assert {s.day_of_week: s.session_type for s in week1.sessions}[3] == "tempo"


def test_move_writes_audit_event(session):
    start = _next_monday()
    plan = _mk_plan(session, start)
    tempo = _find(session, plan, 1, 3)
    move_session(session, tempo.id, (start + timedelta(days=4)).isoformat(), ref=start)

    events = recent_events(session, days=60)
    moved = [e for e in events if e.event_type == "action" and "spostata" in e.title.lower()]
    assert moved
    assert moved[0].before is not None and moved[0].after is not None


def test_move_then_undo_restores_identical_week(session):
    """Q8: undo is just moving back to the source date — a swap is its own
    inverse, so week1 must end up byte-identical to how it started."""
    start = _next_monday()
    plan = _mk_plan(session, start)
    tempo = _find(session, plan, 1, 3)
    before = {s.day_of_week: s.session_type for s in _find(session, plan, 1, 3).week.sessions}

    move_session(session, tempo.id, (start + timedelta(days=4)).isoformat(), ref=start)
    result = move_session(session, tempo.id, (start + timedelta(days=3)).isoformat(), ref=start)

    week1 = next(w for w in result.plan.weeks if w.week_number == 1)
    after = {s.day_of_week: s.session_type for s in week1.sessions}
    assert after == before

    # Both the move and its undo are audited (two events, by design).
    events = recent_events(session, days=60)
    moved = [e for e in events if e.event_type == "action" and "spostata" in e.title.lower()]
    assert len(moved) == 2


def test_unknown_session_raises_lookup(session):
    with pytest.raises(LookupError):
        move_session(session, 999_999, date.today().isoformat())


# ── API surface ──────────────────────────────────────────────────────────────


def test_move_endpoint_roundtrip(client):
    resp = client.post(
        "/api/plan/generate",
        json={
            "goal_type": "10k",
            "goal_date": (date.today() + timedelta(days=120)).isoformat(),
            "level": "intermediate",
            "days_per_week": 4,
            "long_run_day": 6,
        },
    )
    assert resp.status_code == 201, resp.text
    plan = resp.json()
    start = date.fromisoformat(plan["start_date"])

    # Pick a movable session and a target slot in a future week.
    week = next(w for w in plan["weeks"] if w["week_number"] == 3)
    movable = next(
        s for s in week["sessions"] if s["session_type"] not in ("rest", "race")
    )
    target_slot = next(s for s in week["sessions"] if s["session_type"] == "rest")
    target_date = start + timedelta(
        days=(week["week_number"] - 1) * 7 + target_slot["day_of_week"]
    )

    resp = client.patch(
        f"/api/plan/sessions/{movable['id']}/move",
        json={"target_date": target_date.isoformat()},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "warnings" in body and "plan" in body
    week_after = next(
        w for w in body["plan"]["weeks"] if w["week_number"] == week["week_number"]
    )
    moved_after = next(s for s in week_after["sessions"] if s["id"] == movable["id"])
    assert moved_after["day_of_week"] == target_slot["day_of_week"]


def test_move_endpoint_errors(client):
    assert (
        client.patch(
            "/api/plan/sessions/999999/move", json={"target_date": "2030-01-01"}
        ).status_code
        == 404
    )
