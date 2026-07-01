"""Coach Decision service: build, persist and fetch today's decision.

Glue between the pure :func:`app.processing.decide_today` engine and the DB.
Resolves today's planned session from the active multi-week plan, runs the
engine and upserts the resulting :class:`CoachDecision` (one row per date).
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CoachDecisionRow
from app.logging_config import get_logger
from app.processing import compute_metrics, decide_today
from app.schemas import CoachDecision, PlanSessionOut, TrainingPlanOut
from app.services.checkin import latest_checkin
from app.services.ingest import _all_summaries
from app.services.plan_service import get_current_plan
from app.services.profile import get_profile

logger = get_logger("app.services.decision")


def session_on_date(plan: TrainingPlanOut | None, target: date) -> PlanSessionOut | None:
    """Return the plan session scheduled on ``target`` from the active plan.

    Sessions carry ``day_of_week`` (0=Mon) within a week; the plan's
    ``start_date`` anchors week 1, so we map the target date to the right week
    and weekday. Returns ``None`` when there's no plan or nothing that day.
    """
    if plan is None:
        return None
    try:
        start = date.fromisoformat(plan.start_date)
    except (ValueError, TypeError):
        return None
    days_elapsed = (target - start).days
    if days_elapsed < 0:
        return None
    week_number = days_elapsed // 7 + 1
    weekday = target.weekday()  # 0=Mon
    week = next((w for w in plan.weeks if w.week_number == week_number), None)
    if week is None:
        return None
    return next((s for s in week.sessions if s.day_of_week == weekday), None)


def build_today_decision(
    db: Session, ref: date | None = None, persist: bool = True
) -> CoachDecision:
    """Compute today's coaching decision from live state and (optionally) store it."""
    ref = ref or date.today()
    summaries = _all_summaries(db)
    profile = get_profile(db)
    checkin = latest_checkin(db)
    metrics = compute_metrics(summaries, ref=ref, profile=profile, checkin=checkin)
    plan = get_current_plan(db)
    today_session = session_on_date(plan, ref)

    decision = decide_today(metrics, profile, today_session, checkin, ref=ref)
    if persist:
        _upsert(db, decision)
    return decision


def get_today_decision(db: Session, ref: date | None = None) -> CoachDecision:
    """Return today's decision, always freshly recomputed so it tracks state."""
    return build_today_decision(db, ref=ref, persist=True)


def recent_decisions(db: Session, days: int = 14) -> list[CoachDecision]:
    """Return persisted decisions from the last ``days`` days, newest first."""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    rows = db.scalars(
        select(CoachDecisionRow)
        .where(CoachDecisionRow.date >= cutoff)
        .order_by(CoachDecisionRow.date.desc())
    ).all()
    return [_row_to_schema(r) for r in rows]


def _upsert(db: Session, decision: CoachDecision) -> CoachDecisionRow:
    row = db.scalar(
        select(CoachDecisionRow).where(CoachDecisionRow.date == decision.date)
    )
    if row is None:
        row = CoachDecisionRow(date=decision.date)
        db.add(row)
    row.decision = decision.decision
    row.headline = decision.headline
    row.prescription = decision.prescription
    row.rationale = decision.rationale
    row.confidence = decision.confidence
    row.signals = decision.signals
    row.missing_data = decision.missing_data
    row.alternatives = decision.alternatives
    row.safety_flags = decision.safety_flags
    row.plan_session_id = decision.plan_session_id
    row.session_type = decision.session_type
    row.target_distance_km = decision.target_distance_km
    row.target_pace = decision.target_pace
    row.target_duration_min = decision.target_duration_min
    row.source = decision.source
    db.flush()
    return row


def _row_to_schema(row: CoachDecisionRow) -> CoachDecision:
    return CoachDecision(
        date=row.date,
        decision=row.decision,
        headline=row.headline,
        prescription=row.prescription,
        rationale=row.rationale,
        confidence=row.confidence,
        signals=list(row.signals or []),
        missing_data=list(row.missing_data or []),
        alternatives=list(row.alternatives or []),
        safety_flags=list(row.safety_flags or []),
        plan_session_id=row.plan_session_id,
        session_type=row.session_type,
        target_distance_km=row.target_distance_km,
        target_pace=row.target_pace,
        target_duration_min=row.target_duration_min,
        source=row.source,
    )
