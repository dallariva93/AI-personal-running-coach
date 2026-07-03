"""Service layer for multi-week training plans."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.coaching.coach import Coach
from app.db.models import TrainingPlan, TrainingPlanSession, TrainingPlanWeek
from app.logging_config import get_logger
from app.schemas import (
    AthleteProfile,
    PlanGenerateRequest,
    PlanMoveResult,
    PlanSessionOut,
    PlanWeekOut,
    TrainingMetrics,
    TrainingPlanOut,
)

logger = get_logger("app.services.plan_service")

# Quality/hard session types (English + Italian labels) for adjacency warnings.
_HARD = {"tempo", "intervals", "intervalli", "vo2max", "threshold", "soglia", "race", "gara"}
_LONG = {"long", "lungo"}


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

    # Generate plan data from coach. The Digital Twin (A5) injects the athlete's
    # personal weekly ramp cap into the prompt when it has been learned.
    from app.services.athlete_model_service import personal_ramp_factor

    ramp_factor = personal_ramp_factor(db)
    ramp_pct = round((ramp_factor - 1) * 100, 1) if ramp_factor is not None else None
    plan_data = coach.plan_multiweek(request, profile, metrics, ramp_pct=ramp_pct)

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


def _session_date(start: date, week_number: int, day_of_week: int) -> date:
    return start + timedelta(days=(week_number - 1) * 7 + day_of_week)


def move_session(
    db: Session, session_id: int, target_date_str: str, ref: date | None = None
) -> PlanMoveResult:
    """Move a plan session to another calendar day (Calendar editor, Roadmap #12).

    Semantics: the moved session and whatever sits on the target day *swap*
    places (cross-week moves swap the week too), preserving the
    7-sessions-per-week invariant and the generated volumes/details. Completed
    sessions and the goal race never move. After the swap the plan is
    re-checked and safety warnings (quality days back-to-back, long run right
    after a hard day) are returned so the athlete sees the consequence of the
    edit — the deterministic "recalc" the roadmap asks for.

    Raises ``LookupError`` when the session doesn't exist and ``ValueError``
    for invalid moves.
    """
    ref = ref or date.today()
    sess = db.get(TrainingPlanSession, session_id)
    if sess is None:
        raise LookupError(f"Sessione {session_id} non trovata.")

    week = db.get(TrainingPlanWeek, sess.week_id)
    plan = db.get(TrainingPlan, week.plan_id) if week is not None else None
    if plan is None or plan.status != "active":
        raise ValueError("La seduta non appartiene a un piano attivo.")

    try:
        start = date.fromisoformat(plan.start_date)
        target = date.fromisoformat(target_date_str[:10])
    except (ValueError, TypeError) as exc:
        raise ValueError("Data di destinazione non valida (usa YYYY-MM-DD).") from exc

    plan_end = start + timedelta(days=plan.weeks_total * 7 - 1)
    if not (start <= target <= plan_end):
        raise ValueError("La data di destinazione è fuori dal piano.")
    if target < ref:
        raise ValueError("Non puoi spostare una seduta nel passato.")

    if sess.completed:
        raise ValueError("La seduta è già completata: non si sposta.")
    if (sess.session_type or "").lower() in ("race", "gara"):
        raise ValueError("La gara obiettivo non si sposta dal calendario.")

    source_date = _session_date(start, week.week_number, sess.day_of_week)
    if target == source_date:
        return PlanMoveResult(plan=_compute_plan_out(plan), warnings=[])

    target_offset = (target - start).days
    target_week_no = target_offset // 7 + 1
    target_dow = target_offset % 7
    target_week = next(
        (w for w in plan.weeks if w.week_number == target_week_no), None
    )
    if target_week is None:
        raise ValueError("Settimana di destinazione non trovata nel piano.")
    other = next(
        (s for s in target_week.sessions if s.day_of_week == target_dow), None
    )

    if other is not None:
        if other.completed:
            raise ValueError("Il giorno di destinazione ha una seduta già completata.")
        if (other.session_type or "").lower() in ("race", "gara"):
            raise ValueError("Il giorno di destinazione è la gara obiettivo.")

    before = {
        "date": source_date.isoformat(),
        "session_type": sess.session_type,
        "title": sess.title,
    }

    # Swap positions (and weeks, for cross-week moves).
    source_dow = sess.day_of_week
    sess.day_of_week = target_dow
    if other is not None:
        other.day_of_week = source_dow
        other.week_id = week.id
    if target_week.id != week.id:
        sess.week_id = target_week.id
    db.flush()
    # week_id was swapped directly, so the in-memory week.sessions collections
    # are stale — expire everything and let the ORM reload fresh state.
    db.expire_all()

    warnings = _move_warnings(plan, start, {source_date, target})

    from app.services.event_service import log_event

    log_event(
        db,
        date_str=target.isoformat(),
        event_type="action",
        title=f"Seduta spostata: {sess.title}",
        detail=(
            f"{sess.title} spostata da {source_date.isoformat()} a {target.isoformat()}"
            + (f" (scambiata con {other.title})" if other is not None else "")
        ),
        before=before,
        after={"date": target.isoformat(), "session_type": sess.session_type},
        plan_session_id=sess.id,
    )

    return PlanMoveResult(plan=_compute_plan_out(plan), warnings=warnings)


def _move_warnings(
    plan: TrainingPlan, start: date, touched: set[date]
) -> list[str]:
    """Safety warnings around the days affected by a move."""
    by_date: dict[date, str] = {}
    for wk in plan.weeks:
        for s in wk.sessions:
            by_date[_session_date(start, wk.week_number, s.day_of_week)] = (
                s.session_type or ""
            ).lower()

    warnings: list[str] = []
    for day in sorted(touched):
        stype = by_date.get(day, "")
        for neighbor in (day - timedelta(days=1), day + timedelta(days=1)):
            ntype = by_date.get(neighbor, "")
            if stype in _HARD and ntype in _HARD:
                pair = " e ".join(
                    d.isoformat() for d in sorted((day, neighbor))
                )
                msg = f"Due sedute di qualità in giorni consecutivi ({pair})."
                if msg not in warnings:
                    warnings.append(msg)
        if stype in _LONG and by_date.get(day - timedelta(days=1), "") in _HARD:
            warnings.append(
                f"Il lungo del {day.isoformat()} cade il giorno dopo una seduta dura."
            )
        if stype in _HARD and by_date.get(day - timedelta(days=1), "") in _LONG:
            warnings.append(
                f"Seduta di qualità il {day.isoformat()} subito dopo il lungo."
            )
    return warnings


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
