"""REST API routes (JSON).

Mounted under ``/api``. The dashboard (HTML/HTMX) lives separately in main.py.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app import __version__
from app.config import get_settings
from app.db.database import db_healthy, get_session
from app.db.models import Activity
from app.processing import compute_metrics, weekly_buckets
from app.schemas import (
    ActivityOut,
    ManualActivityIn,
    ReportOut,
    RunSummary,
    TrainingMetrics,
    WeeklyBucket,
)
from app.services import (
    ingest_runs,
    list_activities,
    list_reports,
    run_single_analysis,
    run_weekly_plan,
    upsert_activity,
)
from app.services.ingest import _all_summaries

router = APIRouter(prefix="/api", tags=["api"])


def _commit(session: Session) -> None:
    session.commit()


@router.get("/health")
def health() -> dict:
    """Liveness + capability snapshot. Always 200 if the process is up."""
    s = get_settings()
    return {
        "status": "ok",
        "version": __version__,
        "env": s.app_env,
        "garmin_enabled": s.garmin_enabled,
        "ai_enabled": s.ai_enabled,
        "ai_fallback_offline": s.ai_fallback_offline,
        "backup_enabled": s.backup_enabled,
        "auth_enabled": s.auth_enabled,
        "mode": "garmin" if s.garmin_enabled else "demo",
        "coach": "claude" if s.ai_enabled else "offline",
    }


@router.get("/ready")
def ready() -> JSONResponse:
    """Readiness probe: verifies the database is reachable."""
    ok = db_healthy()
    return JSONResponse(
        {"status": "ready" if ok else "unavailable", "database": ok},
        status_code=200 if ok else 503,
    )


@router.get("/version")
def version() -> dict:
    return {"version": __version__}


@router.get("/activities", response_model=list[ActivityOut])
def get_activities(limit: int = 50, session: Session = Depends(get_session)) -> list[Activity]:
    return list_activities(session, limit=limit)


@router.post("/activities", response_model=ActivityOut, status_code=201)
def create_activity(
    payload: ManualActivityIn, session: Session = Depends(get_session)
) -> Activity:
    run = RunSummary(**payload.model_dump())
    activity = upsert_activity(session, run)
    _commit(session)
    session.refresh(activity)
    return activity


@router.post("/ingest", response_model=list[ActivityOut])
def post_ingest(limit: int | None = None, session: Session = Depends(get_session)):
    saved = ingest_runs(session, limit=limit)
    _commit(session)
    for a in saved:
        session.refresh(a)
    return saved


@router.get("/metrics", response_model=TrainingMetrics)
def get_metrics(session: Session = Depends(get_session)) -> TrainingMetrics:
    return compute_metrics(_all_summaries(session))


@router.get("/metrics/weekly", response_model=list[WeeklyBucket])
def get_weekly(weeks: int = 8, session: Session = Depends(get_session)) -> list[WeeklyBucket]:
    return weekly_buckets(_all_summaries(session), weeks=weeks)


@router.get("/reports", response_model=list[ReportOut])
def get_reports(limit: int = 20, session: Session = Depends(get_session)):
    reports = list_reports(session, limit=limit)
    return [_report_to_out(r) for r in reports]


@router.post("/analyze", response_model=ReportOut)
def post_analyze(activity_id: int | None = None, session: Session = Depends(get_session)):
    try:
        report = run_single_analysis(session, activity_id=activity_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _commit(session)
    session.refresh(report)
    return _report_to_out(report)


@router.post("/plan/weekly", response_model=ReportOut)
def post_weekly_plan(session: Session = Depends(get_session)):
    try:
        report = run_weekly_plan(session)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _commit(session)
    session.refresh(report)
    return _report_to_out(report)


def _report_to_out(report) -> ReportOut:
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
