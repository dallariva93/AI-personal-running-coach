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


#: Actions the athlete can take on the Today card (Roadmap #2, actionable).
COACH_ACTIONS = {"done", "reduce", "defer", "problem"}


def apply_coach_action(
    db: Session, action: str, detail: str | None = None, ref: date | None = None
) -> CoachDecision:
    """Apply a Today-card action and return the freshly recomputed decision.

    * ``done``    — mark today's planned session completed.
    * ``reduce``  — cut today's session volume by 30% (from its base).
    * ``defer``   — swap today's session with tomorrow's (same week).
    * ``problem`` — record a wellness signal (``detail`` = ``tired`` | ``pain``)
      so readiness drops, the plan adapts and the decision softens.
    """
    from datetime import UTC, datetime

    from app.db.models import TrainingPlan, TrainingPlanSession

    ref = ref or date.today()
    if action not in COACH_ACTIONS:
        raise ValueError(f"Azione non valida: {action}")

    plan = db.scalar(select(TrainingPlan).where(TrainingPlan.status == "active"))
    start = None
    if plan is not None:
        try:
            start = date.fromisoformat(plan.start_date)
        except (ValueError, TypeError):
            start = None

    def _session_on(target: date) -> TrainingPlanSession | None:
        if plan is None or start is None:
            return None
        elapsed = (target - start).days
        if elapsed < 0:
            return None
        wk = elapsed // 7 + 1
        week = next((w for w in plan.weeks if w.week_number == wk), None)
        if week is None:
            return None
        return next((s for s in week.sessions if s.day_of_week == target.weekday()), None)

    today_sess = _session_on(ref)

    if action == "done" and today_sess is not None:
        today_sess.completed = True
        today_sess.completed_at = datetime.now(UTC)

    elif action == "reduce" and today_sess is not None:
        if today_sess.base_target_distance_km is None and today_sess.target_distance_km:
            today_sess.base_target_distance_km = today_sess.target_distance_km
        if today_sess.base_target_distance_km:
            today_sess.target_distance_km = round(today_sess.base_target_distance_km * 0.7, 1)
        today_sess.adjustment_note = "ridotta su richiesta dell'atleta"

    elif action == "defer" and today_sess is not None and today_sess.day_of_week < 6:
        next_sess = _session_on(ref + timedelta(days=1))
        if next_sess is not None:
            # Swap the two days so nothing is lost.
            today_sess.day_of_week, next_sess.day_of_week = (
                next_sess.day_of_week,
                today_sess.day_of_week,
            )

    elif action == "problem":
        _record_problem(db, detail, ref)

    db.flush()

    # A wellness problem should ripple into the upcoming plan; structural edits
    # (done/reduce/defer) should not be immediately re-adapted away.
    if action == "problem":
        try:
            from app.services.adaptive_plan import adapt_plan_after_sync

            adapt_plan_after_sync(db, ref=ref)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Adaptive pass after action skipped: %s", exc)

    return build_today_decision(db, ref=ref, persist=True)


def _record_problem(db: Session, detail: str | None, ref: date) -> None:
    """Fold a 'sono stanco / ho dolore' signal into today's check-in."""
    from app.schemas import DailyCheckin
    from app.services.checkin import save_checkin

    existing = latest_checkin(db)
    base = existing if (existing and existing.date == ref.isoformat()) else None
    fatigue = base.fatigue if base else None
    soreness = base.soreness if base else None
    sleep = base.sleep_h if base else None
    if detail == "pain":
        # Pain is a strong safety signal: push readiness clearly into the red.
        soreness = max(soreness or 0, 10)
        fatigue = max(fatigue or 0, 9)
    else:  # tired / default
        fatigue = max(fatigue or 0, 9)
        sleep = min(sleep if sleep is not None else 6.0, 5.0)
    save_checkin(
        db,
        DailyCheckin(
            date=ref.isoformat(),
            sleep_h=sleep,
            fatigue=fatigue,
            soreness=soreness,
            motivation=base.motivation if base else None,
            hrv_rmssd=base.hrv_rmssd if base else None,
        ),
    )


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
    row.daily_note = decision.daily_note
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
        daily_note=row.daily_note or "",
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
