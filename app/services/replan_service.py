"""Rolling-horizon re-plan (Fase D — plan architecture review, section 2.2).

A plan is a *living* system, not a one-shot PDF. This service re-derives the
**future** weeks of the active plan from the athlete's current form (refreshed
paces, ACWR-timed deloads), while the past and the current week stay immutable —
a rolling horizon. Volume continuity is kept by re-using the plan's *original*
baseline, so a fitter athlete gets faster paces without the whole ramp inflating.

Safe by construction: only weeks strictly after the current one, and only weeks
with no completed session, are ever replaced. Completed history is never touched.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import TrainingPlan
from app.logging_config import get_logger
from app.processing import compute_metrics
from app.processing.periodization import build_plan_spec
from app.schemas import PlanGenerateRequest
from app.services.checkin import hrv_history, latest_checkin
from app.services.event_service import log_event
from app.services.ingest import _all_summaries
from app.services.plan_service import _session_from_spec
from app.services.profile import get_profile

logger = get_logger("app.services.replan")


def _current_week_number(start: date, ref: date, weeks_total: int) -> int:
    days = (ref - start).days
    return max(1, min(weeks_total, days // 7 + 1))


def _reconstruct_request(plan: TrainingPlan) -> PlanGenerateRequest:
    """Rebuild the generation request from the persisted plan inputs.

    Older plans (created before the inputs were persisted) fall back to values
    inferred from the plan's own sessions, so re-planning still works.
    """
    dpw = plan.days_per_week
    long_day = plan.long_run_day
    if dpw is None or long_day is None:
        first = min(plan.weeks, key=lambda w: w.week_number, default=None)
        if first is not None:
            non_rest = [s for s in first.sessions if s.session_type != "rest"]
            dpw = dpw or max(3, min(6, len(non_rest)))
            longs = [s for s in first.sessions if s.session_type == "long"]
            long_day = long_day if long_day is not None else (
                longs[0].day_of_week if longs else 6
            )
    return PlanGenerateRequest(
        goal_type=plan.goal_type,
        goal_date=plan.goal_date,
        goal_time=plan.goal_time,
        level=plan.level,
        days_per_week=dpw or 4,
        long_run_day=long_day if long_day is not None else 6,
        runner_context=plan.runner_context,
    )


def replan_future_weeks(db: Session, ref: date | None = None) -> dict:
    """Re-derive the active plan's future weeks from current form. Idempotent-ish.

    Returns ``{"replanned": n, "from_week": w}``. A no-op (no active plan, or no
    future weeks left) returns ``{"replanned": 0}``.
    """
    ref = ref or date.today()
    plan = db.scalar(select(TrainingPlan).where(TrainingPlan.status == "active"))
    if plan is None:
        return {"replanned": 0}
    try:
        start = date.fromisoformat(plan.start_date)
    except (ValueError, TypeError):
        return {"replanned": 0}

    current_week_no = _current_week_number(start, ref, plan.weeks_total)
    future = [w for w in plan.weeks if w.week_number > current_week_no]
    if not future:
        return {"replanned": 0, "from_week": current_week_no}

    profile = get_profile(db)
    summaries = _all_summaries(db)
    metrics = compute_metrics(
        summaries, ref=ref, profile=profile, checkin=latest_checkin(db),
        hrv_history=hrv_history(db, ref=ref),
    ) if summaries else None

    from app.services.athlete_model_service import personal_ramp_factor

    ramp_factor = personal_ramp_factor(db)
    ramp_pct = round((ramp_factor - 1) * 100, 1) if ramp_factor is not None else None

    request = _reconstruct_request(plan)
    # Anchor to the ORIGINAL start date so the timeline (week count, phases) is
    # identical; refresh only form-derived aspects. Keep the original baseline.
    spec = build_plan_spec(
        request, profile=profile, metrics=metrics, ramp_pct=ramp_pct,
        ref=start, baseline_km=plan.baseline_km,
    )
    new_weeks = {w["week_number"]: w for w in spec.get("weeks", [])}

    replanned = 0
    for week in future:
        # Never rewrite a week the athlete has already started executing.
        if any(s.completed for s in week.sessions):
            continue
        # Never overwrite a week that carries the goal race or a tune-up race.
        if any((s.session_type or "").lower() in ("race", "gara") for s in week.sessions):
            continue
        new_week = new_weeks.get(week.week_number)
        if new_week is None:
            continue
        week.phase = new_week.get("phase", week.phase)
        week.target_km = float(new_week.get("target_km", week.target_km))
        week.description = new_week.get("description")
        # Replace the sessions wholesale (cascade delete-orphan removes the old).
        week.sessions = [
            _session_from_spec(week.id, s) for s in new_week.get("sessions", [])
        ]
        replanned += 1

    db.flush()
    if replanned:
        log_event(
            db,
            date_str=ref.isoformat(),
            event_type="plan_replanned",
            title="Piano ri-pianificato",
            detail=(
                f"Il coach ha ri-pianificato {replanned} settimane future dalla "
                f"forma attuale (dalla settimana {current_week_no + 1}). "
                "Storia e settimana in corso invariate."
            ),
            dedupe_key=f"{ref.isoformat()}:replan:{plan.id}",
        )
        logger.info(
            "Rolling re-plan: %d future week(s) re-derived from week %d",
            replanned, current_week_no + 1,
        )
    return {"replanned": replanned, "from_week": current_week_no}
