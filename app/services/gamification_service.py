"""Streak + badges, adherence-aware (Roadmap Q4).

Wraps the pure functions in ``app.processing.gamification`` with the DB
queries needed to build the 60-day adherence history, so ``/api/gamification``
and ``/api/mobile/overview`` agree on the same numbers instead of each
inlining their own (slightly different) streak logic.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Activity, TrainingPlan
from app.processing.gamification import (
    AdherenceDay,
    compute_adherence_streak,
    compute_badges,
    compute_streak,
)
from app.processing.metrics import EASY_TYPES
from app.schemas import Badge, GamificationData

_ADHERENCE_WINDOW_DAYS = 60


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value[:10])
    except (ValueError, TypeError):
        return None


def _build_adherence_days(db: Session, ref: date) -> list[AdherenceDay]:
    start = ref - timedelta(days=_ADHERENCE_WINDOW_DAYS - 1)
    by_date: dict[date, AdherenceDay] = {
        start + timedelta(days=i): AdherenceDay(day=start + timedelta(days=i))
        for i in range(_ADHERENCE_WINDOW_DAYS)
    }

    # Every plan that ever touched this window, oldest first, so a later plan
    # (e.g. regenerated mid-window) wins on any date they both cover.
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

    activities = db.scalars(
        select(Activity).where(Activity.sport == "run", Activity.date >= start.isoformat())
    ).all()
    for a in activities:
        d = _parse_date(a.date)
        entry = by_date.get(d) if d else None
        if entry is not None and a.activity_type not in EASY_TYPES:
            entry.ran_hard = True

    return list(by_date.values())


def compute_gamification(
    db: Session, activities: list[Activity], ref: date | None = None
) -> GamificationData:
    """Streak + badges: plan-adherence based when a plan is active, legacy otherwise."""
    ref = ref or date.today()
    has_active_plan = (
        db.scalar(select(TrainingPlan.id).where(TrainingPlan.status == "active")) is not None
    )

    if has_active_plan:
        days = _build_adherence_days(db, ref)
        current, best = compute_adherence_streak(days)
        streak_kind = "adherence"
    else:
        current, best = compute_streak(activities)
        streak_kind = "runs"

    badges = [Badge(**b) for b in compute_badges(activities, current, best)]
    return GamificationData(
        streak_days=current,
        streak_days_best=best,
        streak_kind=streak_kind,
        total_badges_earned=sum(1 for b in badges if b.earned),
        badges=badges,
    )
