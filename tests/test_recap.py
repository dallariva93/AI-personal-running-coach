"""Race recap + weekly recap (Roadmap A6 / Passo 15).

Pure-function tests for the facts (`app/processing/recap.py`), the adherence
percentage helper, and the goal-type mapper; service-level tests for the DB
orchestration (`app/services/recap_service.py`) and the two endpoints.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.db.models import (
    Activity,
    CoachEvent,
    TrainingPlan,
    TrainingPlanSession,
    TrainingPlanWeek,
)
from app.processing.gamification import AdherenceDay, compute_adherence_pct
from app.processing.performance import nearest_goal_type
from app.processing.recap import compute_race_recap_facts, compute_weekly_recap_facts
from app.schemas import PersonalRecord, RunSummary
from app.services.recap_service import (
    build_race_recap,
    build_weekly_recap,
    maybe_emit_race_recap_ready,
    maybe_emit_weekly_recap_trigger,
)

START = date(2026, 1, 5)  # a Monday


# ── Pure: nearest_goal_type ───────────────────────────────────────────────────


def test_nearest_goal_type_exact_and_nearby():
    assert nearest_goal_type(10.0) == "10k"
    assert nearest_goal_type(9.8) == "10k"
    assert nearest_goal_type(21.1) == "half"
    assert nearest_goal_type(42.2) == "marathon"
    assert nearest_goal_type(5.0) == "5k"


# ── Pure: compute_adherence_pct ───────────────────────────────────────────────


def test_adherence_pct_all_honoured():
    days = [
        AdherenceDay(day=START, has_session=True, execution_status="done"),
        AdherenceDay(day=START + timedelta(days=1), prescribed_rest=True, ran_hard=False),
    ]
    assert compute_adherence_pct(days) == 100.0


def test_adherence_pct_one_skipped():
    days = [
        AdherenceDay(day=START, has_session=True, execution_status="skipped"),
        AdherenceDay(day=START + timedelta(days=1), has_session=True, execution_status="done"),
    ]
    assert compute_adherence_pct(days) == 50.0


def test_adherence_pct_none_when_no_plan_coverage():
    days = [AdherenceDay(day=START), AdherenceDay(day=START + timedelta(days=1))]
    assert compute_adherence_pct(days) is None


# ── Pure: compute_weekly_recap_facts / best moment priority ──────────────────


def _run(d: date, km: float) -> RunSummary:
    return RunSummary(date=d.isoformat(), distance_km=km, duration_min=km * 6)


def test_weekly_facts_basic_aggregation():
    runs = [_run(START, 8.0), _run(START + timedelta(days=2), 10.0)]
    facts = compute_weekly_recap_facts(
        runs, [], 80.0, [70.0, 90.0], START.isoformat(),
        (START + timedelta(days=6)).isoformat(),
    )
    assert facts.distance_km == 18.0
    assert facts.runs_count == 2
    assert facts.adherence_pct == 80.0
    assert facts.avg_execution_score == 80.0


def test_best_moment_prefers_pr_over_long_run():
    runs = [_run(START, 20.0)]  # would otherwise be "long run" best moment
    pr = PersonalRecord(distance="10K", pace="4:30/km", date=START.isoformat())
    facts = compute_weekly_recap_facts(
        runs, [pr], None, [], START.isoformat(), (START + timedelta(days=6)).isoformat(),
    )
    assert facts.best_moment == "Nuovo PB 10K: 4:30/km"


def test_best_moment_falls_back_to_great_execution():
    runs = [_run(START, 8.0)]  # not a long run
    facts = compute_weekly_recap_facts(
        runs, [], None, [95.0], START.isoformat(), (START + timedelta(days=6)).isoformat(),
        best_execution=("Intervalli 8x400", 95.0),
    )
    assert facts.best_moment == "Seduta perfetta: Intervalli 8x400 (95/100)"


def test_best_moment_falls_back_to_long_run():
    runs = [_run(START, 18.0)]
    facts = compute_weekly_recap_facts(
        runs, [], None, [], START.isoformat(), (START + timedelta(days=6)).isoformat(),
    )
    assert facts.best_moment == "Il lungo da 18 km"


def test_best_moment_none_when_nothing_stands_out():
    runs = [_run(START, 5.0)]
    facts = compute_weekly_recap_facts(
        runs, [], None, [], START.isoformat(), (START + timedelta(days=6)).isoformat(),
    )
    assert facts.best_moment is None


# ── Pure: compute_race_recap_facts ────────────────────────────────────────────


def test_race_facts_faster_than_predicted():
    facts = compute_race_recap_facts(
        activity_id=1, race_date=START.isoformat(), distance_km=10.0,
        duration_min=42.0, splits_km=["4:10", "4:15"], predicted_seconds=42.5 * 60,
    )
    assert facts.actual_time == "42:00"
    assert facts.delta_seconds == -30.0
    assert "più veloce" in facts.delta_label


def test_race_facts_slower_than_predicted():
    facts = compute_race_recap_facts(
        activity_id=1, race_date=START.isoformat(), distance_km=10.0,
        duration_min=45.0, splits_km=None, predicted_seconds=42.0 * 60,
    )
    assert facts.delta_seconds == 180.0
    assert "più lento" in facts.delta_label


def test_race_facts_no_prediction():
    facts = compute_race_recap_facts(
        activity_id=1, race_date=START.isoformat(), distance_km=10.0,
        duration_min=45.0, splits_km=None, predicted_seconds=None,
    )
    assert facts.predicted_time is None
    assert facts.delta_seconds is None and facts.delta_label is None


# ── Service: build_weekly_recap ──────────────────────────────────────────────


def _plan(db, weeks: int = 1) -> TrainingPlan:
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
        for dow, stype in [(0, "easy"), (1, "tempo"), (6, "rest")]:
            db.add(TrainingPlanSession(
                week_id=week.id, day_of_week=dow, session_type=stype,
                title=f"{stype} w{wk}", target_distance_km=None if stype == "rest" else 8.0,
                target_pace=None if stype == "rest" else "5:00",
                execution_status="done" if stype != "rest" else None,
                execution_score=85.0 if stype == "tempo" else None,
            ))
    db.flush()
    return plan


def test_build_weekly_recap_full(session):
    _plan(session)
    session.add(Activity(date=START.isoformat(), sport="run", activity_type="easy",
                         distance_km=8.0, duration_min=48.0))
    session.add(Activity(date=(START + timedelta(days=1)).isoformat(), sport="run",
                         activity_type="tempo", distance_km=8.0, duration_min=40.0))
    session.flush()

    recap = build_weekly_recap(session, ref=START + timedelta(days=3))
    assert recap.week_start == START.isoformat()
    assert recap.runs_count == 2
    assert recap.distance_km == 16.0
    assert recap.adherence_pct == 100.0  # both prescribed sessions done, rest untouched
    assert recap.avg_execution_score == 85.0
    assert recap.narrative  # template always present


def test_build_weekly_recap_no_plan_no_activity(session):
    recap = build_weekly_recap(session, ref=START)
    assert recap.runs_count == 0
    assert recap.adherence_pct is None
    assert recap.narrative  # still a valid (empty-week) sentence


# ── Service: build_race_recap ────────────────────────────────────────────────


def test_build_race_recap_compares_prediction(session):
    # History before the race: a 10K in ~44:00 → predicts the goal race.
    session.add(Activity(date=(START - timedelta(days=20)).isoformat(), sport="run",
                         activity_type="tempo", distance_km=10.0, duration_min=44.0,
                         avg_pace="4:24/km"))
    race = Activity(date=(START + timedelta(days=30)).isoformat(), sport="run",
                    activity_type="gara", distance_km=10.0, duration_min=42.0,
                    splits_km=["4:10"] * 10)
    session.add(race)
    session.flush()

    recap = build_race_recap(session, race.id)
    assert recap is not None
    assert recap.activity_id == race.id
    assert recap.actual_time == "42:00"
    assert recap.splits_km == ["4:10"] * 10
    assert recap.narrative


def test_build_race_recap_none_for_non_race(session):
    easy = Activity(date=START.isoformat(), sport="run", activity_type="easy", distance_km=8.0)
    session.add(easy)
    session.flush()
    assert build_race_recap(session, easy.id) is None


def test_build_race_recap_none_for_missing_activity(session):
    assert build_race_recap(session, 999999) is None


# ── Service: notifiable triggers ─────────────────────────────────────────────


def test_weekly_recap_trigger_fires_sunday_evening_once(session):
    sunday = START + timedelta(days=6)
    from datetime import datetime

    evening = datetime(sunday.year, sunday.month, sunday.day, 19, 0)
    ev = maybe_emit_weekly_recap_trigger(session, ref=sunday, now=evening)
    assert ev is not None and ev.notifiable and ev.after["deep_link"] == "recap/weekly"

    # Same week, later call → deduped.
    ev2 = maybe_emit_weekly_recap_trigger(session, ref=sunday, now=evening)
    assert ev2 is None
    assert session.query(CoachEvent).filter_by(event_type="recap_weekly_ready").count() == 1


def test_weekly_recap_trigger_silent_before_evening_or_off_sunday(session):
    sunday = START + timedelta(days=6)
    from datetime import datetime

    morning = datetime(sunday.year, sunday.month, sunday.day, 9, 0)
    assert maybe_emit_weekly_recap_trigger(session, ref=sunday, now=morning) is None
    monday_evening = datetime(START.year, START.month, START.day, 19, 0)
    assert maybe_emit_weekly_recap_trigger(session, ref=START, now=monday_evening) is None


def test_race_recap_ready_fires_once_per_activity(session):
    race = Activity(date=START.isoformat(), sport="run", activity_type="gara", distance_km=10.0)
    session.add(race)
    session.flush()
    ev = maybe_emit_race_recap_ready(session, race)
    assert ev is not None and ev.after["activity_id"] == race.id
    assert maybe_emit_race_recap_ready(session, race) is None


def test_race_recap_ready_silent_for_non_race(session):
    easy = Activity(date=START.isoformat(), sport="run", activity_type="easy", distance_km=8.0)
    session.add(easy)
    session.flush()
    assert maybe_emit_race_recap_ready(session, easy) is None
    assert maybe_emit_race_recap_ready(session, None) is None


# ── HTTP endpoints ────────────────────────────────────────────────────────────


def test_weekly_recap_endpoint(client):
    resp = client.get("/api/recap/weekly")
    assert resp.status_code == 200
    body = resp.json()
    assert "narrative" in body and "week_start" in body


def test_race_recap_endpoint_404_for_non_race(client, session):
    easy = Activity(date=START.isoformat(), sport="run", activity_type="easy", distance_km=8.0)
    session.add(easy)
    session.commit()
    resp = client.get(f"/api/recap/race/{easy.id}")
    assert resp.status_code == 404


def test_race_recap_endpoint_200_for_race(client, session):
    race = Activity(date=START.isoformat(), sport="run", activity_type="gara",
                    distance_km=10.0, duration_min=42.0)
    session.add(race)
    session.commit()
    resp = client.get(f"/api/recap/race/{race.id}")
    assert resp.status_code == 200
    assert resp.json()["actual_time"] == "42:00"
