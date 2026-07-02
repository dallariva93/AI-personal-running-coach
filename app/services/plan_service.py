"""Service layer for multi-week training plans."""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.coaching.coach import Coach
from app.db.models import TrainingPlan, TrainingPlanSession, TrainingPlanWeek
from app.logging_config import get_logger
from app.schemas import (
    AthleteProfile,
    PlanGenerateRequest,
    PlanSessionOut,
    PlanWeekOut,
    TrainingMetrics,
    TrainingPlanOut,
)

logger = get_logger("app.services.plan_service")


def generate_plan(
    db: Session,
    request: PlanGenerateRequest,
    coach: Coach,
    profile: AthleteProfile | None = None,
    metrics: TrainingMetrics | None = None,
) -> TrainingPlanOut:
    """Archive any active plan, generate a new plan via coach, persist to DB."""
    # Archive any existing active plan
    active = db.scalar(
        select(TrainingPlan).where(TrainingPlan.status == "active")
    )
    if active is not None:
        active.status = "archived"
        db.flush()

    # Generate plan data from coach
    plan_data = coach.plan_multiweek(request, profile, metrics)

    # Guarantee the plan matches what was agreed in the pre-plan chat: the
    # generator is a separate model call (with an offline fallback) and can
    # drift from the agreed week. This deterministic pass reshapes every week
    # to the agreed day → session-type skeleton from the runner context.
    from app.processing import enforce_week_structure

    plan_data, enforcement_notes = enforce_week_structure(
        plan_data, request.runner_context
    )
    if enforcement_notes:
        logger.info(
            "Plan reshaped to honor the chat agreement: %s",
            "; ".join(enforcement_notes),
        )

    weeks_list = plan_data.get("weeks", [])
    weeks_total = len(weeks_list)
    start_date = plan_data.get("start_date", date.today().isoformat())

    # Persist the plan
    plan = TrainingPlan(
        goal_type=request.goal_type,
        goal_date=request.goal_date,
        goal_time=request.goal_time,
        level=request.level,
        weeks_total=weeks_total,
        start_date=start_date,
        status="active",
        created_at=datetime.now(UTC),
    )
    db.add(plan)
    db.flush()

    for week_data in weeks_list:
        week = TrainingPlanWeek(
            plan_id=plan.id,
            week_number=week_data["week_number"],
            phase=week_data.get("phase", "Base"),
            target_km=float(week_data.get("target_km", 0.0)),
            description=week_data.get("description"),
        )
        db.add(week)
        db.flush()

        for sess_data in week_data.get("sessions", []):
            target_dist = (
                float(sess_data["target_distance_km"])
                if sess_data.get("target_distance_km") is not None
                else None
            )
            sess_type = sess_data.get("session_type", "easy")
            sess = TrainingPlanSession(
                week_id=week.id,
                day_of_week=int(sess_data["day_of_week"]),
                session_type=sess_type,
                title=sess_data.get("title", ""),
                description=sess_data.get("description"),
                target_distance_km=target_dist,
                target_pace=sess_data.get("target_pace"),
                target_duration_min=(
                    float(sess_data["target_duration_min"])
                    if sess_data.get("target_duration_min") is not None
                    else None
                ),
                completed=bool(sess_data.get("completed", False)),
                # P0-10: capture base prescription at creation time.
                base_target_distance_km=target_dist,
                base_session_type=sess_type,
            )
            db.add(sess)

    db.flush()
    # Reload with relationships
    db.refresh(plan)
    return _compute_plan_out(plan)


def get_current_plan(db: Session) -> TrainingPlanOut | None:
    """Fetch the active training plan with computed fields."""
    plan = db.scalar(
        select(TrainingPlan).where(TrainingPlan.status == "active")
    )
    if plan is None:
        return None
    return _compute_plan_out(plan)


def get_plan(db: Session, plan_id: int) -> TrainingPlanOut | None:
    """Fetch a specific plan by ID."""
    plan = db.get(TrainingPlan, plan_id)
    if plan is None:
        return None
    return _compute_plan_out(plan)


def toggle_session_complete(db: Session, session_id: int) -> PlanSessionOut:
    """Toggle completion status of a session."""
    sess = db.get(TrainingPlanSession, session_id)
    if sess is None:
        raise ValueError(f"Sessione {session_id} non trovata.")
    sess.completed = not sess.completed
    sess.completed_at = datetime.now(UTC) if sess.completed else None
    db.flush()
    return PlanSessionOut.model_validate(sess)


def archive_plan(db: Session, plan_id: int) -> bool:
    """Set plan status to 'archived'."""
    plan = db.get(TrainingPlan, plan_id)
    if plan is None:
        return False
    plan.status = "archived"
    db.flush()
    return True


def _compute_plan_out(plan: TrainingPlan) -> TrainingPlanOut:
    """Compute derived fields and build the output schema."""
    today = date.today()
    try:
        start = date.fromisoformat(plan.start_date)
    except (ValueError, TypeError):
        start = today

    days_elapsed = (today - start).days
    current_week_number = max(1, min(plan.weeks_total, days_elapsed // 7 + 1))
    weeks_remaining = max(0, plan.weeks_total - current_week_number)

    weeks_out = [_compute_week_out(w) for w in plan.weeks]

    current_week_out = next(
        (w for w in weeks_out if w.week_number == current_week_number), None
    )

    # Overall completion
    total_non_rest = sum(
        1
        for w in plan.weeks
        for s in w.sessions
        if s.session_type != "rest"
    )
    completed_non_rest = sum(
        1
        for w in plan.weeks
        for s in w.sessions
        if s.session_type != "rest" and s.completed
    )
    overall_pct = (
        (completed_non_rest / total_non_rest * 100.0) if total_non_rest > 0 else 0.0
    )

    return TrainingPlanOut(
        id=plan.id,
        goal_type=plan.goal_type,
        goal_date=plan.goal_date,
        goal_time=plan.goal_time,
        level=plan.level,
        weeks_total=plan.weeks_total,
        start_date=plan.start_date,
        status=plan.status,
        current_week_number=current_week_number,
        weeks_remaining=weeks_remaining,
        overall_completion_pct=round(overall_pct, 1),
        current_week=current_week_out,
        weeks=weeks_out,
    )


def _compute_week_out(week: TrainingPlanWeek) -> PlanWeekOut:
    """Compute completion_pct for a week and build the output schema."""
    sessions_out = [PlanSessionOut.model_validate(s) for s in week.sessions]

    non_rest = [s for s in sessions_out if s.session_type != "rest"]
    completed_count = sum(1 for s in non_rest if s.completed)
    completion_pct = (
        (completed_count / len(non_rest) * 100.0) if non_rest else 0.0
    )

    return PlanWeekOut(
        id=week.id,
        week_number=week.week_number,
        phase=week.phase,
        target_km=week.target_km,
        description=week.description,
        sessions=sessions_out,
        completion_pct=round(completion_pct, 1),
    )
