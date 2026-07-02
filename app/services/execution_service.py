"""Workout Execution Score service (Roadmap #9).

For each recent plan session, find the running activity the athlete actually did
on that day, score how faithfully it matched the prescription and store the
result on the session. Also auto-completes a session when a matching activity is
found, so plan compliance reflects reality — which the adaptive engine then
reads.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Activity, TrainingPlan, TrainingPlanSession
from app.logging_config import get_logger
from app.processing import merge_day_activities, score_execution
from app.schemas import ExecutionResult
from app.services.ingest import _activity_to_summary

logger = get_logger("app.services.execution")

# How far back to (re)evaluate sessions on each pass. Matches the adherence
# streak's 60-day window (Roadmap Q4): sessions never scored within this
# range stay execution_status=None, which the adherence streak treats as
# "not skipped" (benefit of the doubt) rather than a broken streak.
_LOOKBACK_DAYS = 60
# A matching activity with at least this score auto-completes the session.
_AUTO_COMPLETE_SCORE = 50.0


def _session_date(start: date, week_number: int, day_of_week: int) -> date:
    return start + timedelta(days=(week_number - 1) * 7 + day_of_week)


def _activities_for(db: Session, target: date) -> list[Activity]:
    """All running activities on ``target`` — a warm-up and a quality run can
    share a day and must be judged together (Q3), not by "the longest run"."""
    return list(
        db.scalars(
            select(Activity).where(Activity.sport == "run", Activity.date == target.isoformat())
        ).all()
    )


def evaluate_plan_executions(db: Session, ref: date | None = None) -> list[ExecutionResult]:
    """Score recent plan sessions against real activities. Returns what changed."""
    ref = ref or date.today()
    plan = db.scalar(select(TrainingPlan).where(TrainingPlan.status == "active"))
    if plan is None:
        return []
    try:
        start = date.fromisoformat(plan.start_date)
    except (ValueError, TypeError):
        return []

    cutoff = ref - timedelta(days=_LOOKBACK_DAYS)
    results: list[ExecutionResult] = []

    for week in plan.weeks:
        for sess in week.sessions:
            sess_date = _session_date(start, week.week_number, sess.day_of_week)
            # Only score past/today sessions inside the lookback window.
            if sess_date > ref or sess_date < cutoff:
                continue
            if (sess.session_type or "").lower() in ("rest", "riposo"):
                continue

            activities = _activities_for(db, sess_date)
            session_out = _session_to_out(sess)
            if not activities:
                result = score_execution(session_out, None, sess_date.isoformat())
                principal = None
            else:
                summaries = [_activity_to_summary(a) for a in activities]
                merged, principal_idx, accessory_note = merge_day_activities(
                    summaries, sess.session_type
                )
                result = score_execution(session_out, merged, sess_date.isoformat())
                if accessory_note:
                    result.evidence.append(accessory_note)
                principal = activities[principal_idx]
                result.activity_id = principal.id

            _apply(sess, result, principal)
            results.append(result)

    db.flush()
    if results:
        logger.info("Execution scored for %d session(s)", len(results))
    return results


def recent_executions(db: Session, days: int = 21) -> list[ExecutionResult]:
    """Scored sessions from the active plan within the window, newest first."""
    plan = db.scalar(select(TrainingPlan).where(TrainingPlan.status == "active"))
    if plan is None:
        return []
    try:
        start = date.fromisoformat(plan.start_date)
    except (ValueError, TypeError):
        return []
    cutoff = date.today() - timedelta(days=days)
    out: list[ExecutionResult] = []
    for week in plan.weeks:
        for sess in week.sessions:
            if sess.execution_status is None:
                continue
            sess_date = _session_date(start, week.week_number, sess.day_of_week)
            if sess_date < cutoff:
                continue
            detail = sess.execution_detail or {}
            out.append(
                ExecutionResult(
                    plan_session_id=sess.id,
                    activity_id=sess.executed_activity_id,
                    date=sess_date.isoformat(),
                    execution_score=sess.execution_score or 0.0,
                    execution_status=sess.execution_status,
                    execution_notes=sess.execution_note or "",
                    evidence=list(sess.execution_evidence or []),
                    volume_score=detail.get("volume_score"),
                    intensity_score=detail.get("intensity_score"),
                    pace_score=detail.get("pace_score"),
                    structure_score=detail.get("structure_score"),
                    distribution_score=detail.get("distribution_score"),
                    time_in_zone_pct=detail.get("time_in_zone_pct"),
                )
            )
    out.sort(key=lambda r: r.date, reverse=True)
    return out


def _apply(
    sess: TrainingPlanSession, result: ExecutionResult, activity: Activity | None
) -> None:
    sess.execution_score = result.execution_score
    sess.execution_status = result.execution_status
    sess.execution_note = result.execution_notes
    sess.execution_evidence = result.evidence
    sess.execution_detail = {
        "volume_score": result.volume_score,
        "intensity_score": result.intensity_score,
        "pace_score": result.pace_score,
        "structure_score": result.structure_score,
        "distribution_score": result.distribution_score,
        "time_in_zone_pct": result.time_in_zone_pct,
    }
    if activity is not None:
        sess.executed_activity_id = activity.id
        if result.execution_score >= _AUTO_COMPLETE_SCORE and not sess.completed:
            sess.completed = True


def _session_to_out(sess: TrainingPlanSession):
    from app.schemas import PlanSessionOut

    return PlanSessionOut.model_validate(sess)
