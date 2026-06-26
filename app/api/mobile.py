"""Mobile-friendly API surface.

The native app prefers a single aggregated call over many round-trips, so this
router exposes ``/api/mobile/overview`` returning everything the home and plan
screens need: capabilities, form metrics, weekly load, recent activities and the
latest single-run analysis and weekly plan.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import __version__
from app.config import get_settings
from app.db.database import get_session
from app.db.models import CoachingReport
from app.processing import (
    aerobic_efficiency,
    build_periodization,
    build_snapshot,
    compute_metrics,
    predict_race_time,
    weekly_buckets,
)
from app.schemas import ActivityOut, ReportOut, TrainingMetrics, WeeklyBucket
from app.services import get_profile, latest_checkin, list_activities
from app.services.ingest import _all_summaries

router = APIRouter(prefix="/api/mobile", tags=["mobile"])


def _latest_report(session: Session, scope: str) -> ReportOut | None:
    report = session.scalar(
        select(CoachingReport)
        .where(CoachingReport.scope == scope)
        .order_by(CoachingReport.created_at.desc())
        .limit(1)
    )
    if report is None:
        return None
    return ReportOut(
        id=report.id,
        activity_id=report.activity_id,
        scope=report.scope,
        model=report.model,
        analysis=report.analysis,
        next_workout=report.next_workout,
        metrics=report.metrics,
        created_at=report.created_at.isoformat() if report.created_at else None,
    )


@router.get("/overview")
def overview(session: Session = Depends(get_session)) -> dict:
    """Everything the app needs to render its main screens in one request.

    Brain-aware: the metrics carry the full Fitness/Fatigue, periodization,
    injury, readiness and intensity signals, and the response also bundles the
    athlete profile, the 6-month snapshot, the goal-race prediction and the
    periodization plan so the app can render the coaching screens natively.
    """
    settings = get_settings()
    summaries = _all_summaries(session)
    profile = get_profile(session)
    checkin = latest_checkin(session)
    metrics: TrainingMetrics = compute_metrics(summaries, profile=profile, checkin=checkin)
    weekly: list[WeeklyBucket] = weekly_buckets(summaries, weeks=8)
    activities = [ActivityOut.model_validate(a) for a in list_activities(session, limit=30)]
    snapshot = build_snapshot(summaries)

    goal = profile.goal if profile else None
    prediction = plan = None
    if goal:
        _, eff_trend = aerobic_efficiency(summaries)
        prediction = predict_race_time(goal, snapshot, eff_trend)
        baseline = max(metrics.chronic_load_km, metrics.acute_load_km / 1.5, 20.0)
        plan = build_periodization(goal, baseline_km=baseline)

    return {
        "version": __version__,
        "mode": "garmin" if settings.garmin_enabled else "demo",
        "coach": "claude" if settings.ai_enabled else "offline",
        "metrics": metrics.model_dump(),
        "weekly": [w.model_dump() for w in weekly],
        "activities": [a.model_dump() for a in activities],
        "latest_analysis": _latest_report(session, "single"),
        "latest_plan": _latest_report(session, "weekly"),
        "profile": profile.model_dump() if profile else None,
        "snapshot": snapshot.model_dump(),
        "prediction": prediction.model_dump() if prediction else None,
        "plan": plan.model_dump() if plan else None,
        "checkin": checkin.model_dump() if checkin else None,
    }
