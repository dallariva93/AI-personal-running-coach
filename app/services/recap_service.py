"""Recap orchestration (Roadmap A6): gather facts, verbalize, notify.

Two shareable surfaces:

* **Weekly recap** — km, adherence %, average execution score and the week's
  best moment (a PR, a near-perfect session, or the long run), computed from
  the coach's own diary and plan data. A Sunday-evening trigger (once per ISO
  week) tells the athlete it's ready.
* **Race recap** — the just-run race's actual time against a genuine pre-race
  prediction (built from the athlete's history *before* that race, so it is
  never hindsight), plus splits. A notifiable event fires once per race,
  mirroring how A4 nudges for a debrief on a fresh run.

Both reuse the A1 verbalizer discipline (:mod:`app.coaching.recap_narrative`):
the facts are deterministic, the LLM only rewrites the surface and can never
invent a number.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.coaching.recap_narrative import build_race_narrative, build_weekly_narrative
from app.db.models import Activity, CoachEvent, TrainingPlan
from app.processing.gamification import AdherenceDay, compute_adherence_pct
from app.processing.metrics import EASY_TYPES
from app.processing.performance import nearest_goal_type, predict_race_time
from app.processing.recap import compute_race_recap_facts, compute_weekly_recap_facts
from app.processing.records import compute_personal_records
from app.processing.snapshot import build_snapshot
from app.schemas import Goal, PersonalRecord, RaceRecap, WeeklyRecap
from app.services.event_service import log_event
from app.services.ingest import _activity_to_summary

_RACE_TYPES = ("gara", "race")
# Local hour from which "Sunday evening" begins (Roadmap A6 trigger).
_EVENING_HOUR = 18


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value[:10])
    except (ValueError, TypeError):
        return None


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _week_key(ref: date) -> str:
    y, w, _ = ref.isocalendar()
    return f"{y}-W{w:02d}"


def _week_plan_facts(
    db: Session, week_start: date, week_end: date, week_activities: list[Activity]
) -> tuple[float | None, list[float], tuple[str, float] | None]:
    """(adherence_pct, execution_scores, best_execution) for one calendar week."""
    by_date: dict[date, AdherenceDay] = {
        week_start + timedelta(days=i): AdherenceDay(day=week_start + timedelta(days=i))
        for i in range(7)
    }
    execution_scores: list[float] = []
    best_execution: tuple[str, float] | None = None

    plans = db.scalars(select(TrainingPlan).order_by(TrainingPlan.id.asc())).all()
    for plan in plans:
        plan_start = _parse_date(plan.start_date)
        if plan_start is None:
            continue
        for week in plan.weeks:
            for sess in week.sessions:
                d = plan_start + timedelta(days=(week.week_number - 1) * 7 + sess.day_of_week)
                entry = by_date.get(d)
                if entry is None:
                    continue
                if (sess.session_type or "").lower() in ("rest", "riposo"):
                    entry.prescribed_rest = True
                    entry.has_session = False
                else:
                    entry.has_session = True
                    entry.prescribed_rest = False
                    entry.execution_status = sess.execution_status
                if sess.execution_score is not None:
                    execution_scores.append(sess.execution_score)
                    if best_execution is None or sess.execution_score > best_execution[1]:
                        best_execution = (sess.title, sess.execution_score)

    for a in week_activities:
        d = _parse_date(a.date)
        entry = by_date.get(d) if d else None
        if entry is not None and a.activity_type not in EASY_TYPES:
            entry.ran_hard = True

    adherence_pct = compute_adherence_pct(list(by_date.values()))
    return adherence_pct, execution_scores, best_execution


def build_weekly_recap(db: Session, ref: date | None = None) -> WeeklyRecap:
    """Assemble and verbalize the recap for the ISO week containing ``ref``."""
    ref = ref or date.today()
    week_start = _monday(ref)
    week_end = week_start + timedelta(days=6)

    all_activities = list(
        db.scalars(
            select(Activity).where(Activity.sport == "run").order_by(Activity.date.desc())
        ).all()
    )
    week_activities = [
        a for a in all_activities
        if (d := _parse_date(a.date)) and week_start <= d <= week_end
    ]
    week_runs = [_activity_to_summary(a) for a in week_activities]
    prs = [PersonalRecord(**pr) for pr in compute_personal_records(all_activities)]

    adherence_pct, execution_scores, best_execution = _week_plan_facts(
        db, week_start, week_end, week_activities
    )
    facts = compute_weekly_recap_facts(
        week_runs, prs, adherence_pct, execution_scores,
        week_start.isoformat(), week_end.isoformat(), best_execution,
    )
    narrative = build_weekly_narrative(facts)
    return WeeklyRecap(
        week_start=facts.week_start,
        week_end=facts.week_end,
        distance_km=facts.distance_km,
        runs_count=facts.runs_count,
        adherence_pct=facts.adherence_pct,
        avg_execution_score=facts.avg_execution_score,
        best_moment=facts.best_moment,
        narrative=narrative,
    )


def build_race_recap(db: Session, activity_id: int) -> RaceRecap | None:
    """Prediction-vs-reality recap for a race activity, or None if not a race."""
    activity = db.get(Activity, activity_id)
    if (
        activity is None
        or activity.sport != "run"
        or (activity.activity_type or "").lower() not in _RACE_TYPES
    ):
        return None

    race_date = _parse_date(activity.date)
    prior_rows = db.scalars(
        select(Activity)
        .where(Activity.sport == "run", Activity.date < activity.date)
        .order_by(Activity.date.desc())
    ).all()
    prior_runs = [_activity_to_summary(a) for a in prior_rows]
    snapshot = build_snapshot(
        prior_runs, ref=(race_date - timedelta(days=1)) if race_date else None
    )
    goal = Goal(goal_type=nearest_goal_type(activity.distance_km))
    prediction = predict_race_time(goal, snapshot)
    predicted_seconds = prediction.predicted_seconds if prediction else None

    facts = compute_race_recap_facts(
        activity_id=activity.id,
        race_date=activity.date,
        distance_km=activity.distance_km,
        duration_min=activity.duration_min,
        splits_km=activity.splits_km,
        predicted_seconds=predicted_seconds,
    )
    narrative = build_race_narrative(facts)
    return RaceRecap(
        activity_id=facts.activity_id,
        date=facts.date,
        distance_km=facts.distance_km,
        actual_time=facts.actual_time,
        predicted_time=facts.predicted_time,
        delta_seconds=facts.delta_seconds,
        delta_label=facts.delta_label,
        splits_km=facts.splits_km,
        narrative=narrative,
    )


def maybe_emit_weekly_recap_trigger(
    db: Session, ref: date | None = None, now: datetime | None = None
) -> CoachEvent | None:
    """Sunday-evening nudge that the week's recap is ready (A6).

    At most one per ISO week (weekly dedupe, same pattern as the A1 triggers).
    """
    ref = ref or date.today()
    now = now or datetime.now()
    if ref.weekday() != 6 or now.hour < _EVENING_HOUR:
        return None
    return log_event(
        db,
        date_str=ref.isoformat(),
        event_type="recap_weekly_ready",
        title="Il tuo riassunto della settimana è pronto",
        detail="Guarda come è andata questa settimana e condividila.",
        after={"deep_link": "recap/weekly"},
        notifiable=True,
        priority="low",
        dedupe_key=f"recap_weekly:{_week_key(ref)}",
    )


def maybe_emit_race_recap_ready(db: Session, activity: Activity | None) -> CoachEvent | None:
    """Notify once that a just-ingested race's recap card is ready (A6)."""
    if (
        activity is None
        or activity.sport != "run"
        or (activity.activity_type or "").lower() not in _RACE_TYPES
    ):
        return None
    return log_event(
        db,
        date_str=activity.date,
        event_type="recap_race_ready",
        title="La tua card della gara è pronta",
        detail="Confronta previsione e risultato reale, e condividila.",
        after={"deep_link": "recap/race", "activity_id": activity.id},
        notifiable=True,
        priority="low",
        dedupe_key=f"recap_race:{activity.id}",
    )
