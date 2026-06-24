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
from app.processing import compute_metrics, weekly_buckets
from app.schemas import ActivityOut, ReportOut, TrainingMetrics, WeeklyBucket
from app.services import list_activities
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
    """Everything the app needs to render its main screens in one request."""
    settings = get_settings()
    summaries = _all_summaries(session)
    metrics: TrainingMetrics = compute_metrics(summaries)
    weekly: list[WeeklyBucket] = weekly_buckets(summaries, weeks=8)
    activities = [ActivityOut.model_validate(a) for a in list_activities(session, limit=30)]

    return {
        "version": __version__,
        "mode": "garmin" if settings.garmin_enabled else "demo",
        "coach": "claude" if settings.ai_enabled else "offline",
        "metrics": metrics.model_dump(),
        "weekly": [w.model_dump() for w in weekly],
        "activities": [a.model_dump() for a in activities],
        "latest_analysis": _latest_report(session, "single"),
        "latest_plan": _latest_report(session, "weekly"),
    }
