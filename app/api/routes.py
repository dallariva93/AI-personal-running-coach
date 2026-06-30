"""REST API routes (JSON).

Mounted under ``/api``. The dashboard (HTML/HTMX) lives separately in main.py.
"""

from __future__ import annotations

import csv
import io
import json as _json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from app import __version__
from app.config import get_settings
from app.db.database import db_healthy, get_session
from app.db.models import Activity
from app.processing import (
    aerobic_efficiency,
    build_periodization,
    build_snapshot,
    compute_badges,
    compute_metrics,
    compute_personal_records,
    compute_streak,
    predict_race_time,
    trail_metrics,
    weekly_buckets,
)
from app.schemas import (
    ActivityOut,
    ActivityPatch,
    AthleteProfile,
    AthleteSnapshot,
    Badge,
    DailyCheckin,
    GamificationData,
    HeatmapResponse,
    HeatmapRoute,
    ManualActivityIn,
    PeriodizationPlan,
    PeriodStats,
    PersonalRecord,
    RacePrediction,
    ReportOut,
    RunSummary,
    TrailMetrics,
    TrainingMetrics,
    WeeklyBucket,
)
from app.services import (
    get_profile,
    ingest_runs,
    latest_checkin,
    list_activities,
    list_reports,
    run_single_analysis,
    run_weekly_plan,
    save_checkin,
    save_profile,
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
        "strava_enabled": s.strava_enabled,
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


@router.patch("/activities/{activity_id}", response_model=ActivityOut)
def patch_activity(
    activity_id: int,
    payload: ActivityPatch,
    session: Session = Depends(get_session),
) -> Activity:
    """Partial update: write only the fields explicitly provided (RPE, notes)."""
    activity = session.get(Activity, activity_id)
    if activity is None:
        raise HTTPException(status_code=404, detail="Attività non trovata.")
    if payload.rpe is not None:
        activity.rpe = payload.rpe
    if payload.notes is not None:
        activity.notes = payload.notes
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


@router.get("/profile", response_model=AthleteProfile)
def get_athlete_profile(session: Session = Depends(get_session)) -> AthleteProfile:
    return get_profile(session) or AthleteProfile()


@router.put("/profile", response_model=AthleteProfile)
def put_athlete_profile(
    payload: AthleteProfile, session: Session = Depends(get_session)
) -> AthleteProfile:
    save_profile(session, payload)
    _commit(session)
    return get_profile(session) or AthleteProfile()


@router.get("/plan/periodization", response_model=PeriodizationPlan)
def get_periodization(session: Session = Depends(get_session)) -> PeriodizationPlan:
    profile = get_profile(session)
    goal = profile.goal if profile else None
    metrics = compute_metrics(_all_summaries(session), profile=profile)
    baseline = max(metrics.chronic_load_km, metrics.acute_load_km / 1.5, 20.0)
    plan = build_periodization(goal, baseline_km=baseline) if goal else None
    if plan is None:
        raise HTTPException(
            status_code=404, detail="Nessun obiettivo con data gara configurato."
        )
    return plan


@router.get("/snapshot", response_model=AthleteSnapshot)
def get_snapshot(session: Session = Depends(get_session)) -> AthleteSnapshot:
    return build_snapshot(_all_summaries(session))


@router.get("/activities/{activity_id}/trail", response_model=TrailMetrics)
def get_trail_metrics(
    activity_id: int, session: Session = Depends(get_session)
) -> TrailMetrics:
    from app.services.ingest import _activity_to_summary

    activity = session.get(Activity, activity_id)
    if activity is None:
        raise HTTPException(status_code=404, detail="Attività non trovata.")
    tm = trail_metrics(_activity_to_summary(activity))
    if tm is None:
        raise HTTPException(status_code=404, detail="Nessun dato di dislivello per l'attività.")
    return tm


@router.get("/predict", response_model=RacePrediction)
def get_prediction(session: Session = Depends(get_session)) -> RacePrediction:
    profile = get_profile(session)
    goal = profile.goal if profile else None
    summaries = _all_summaries(session)
    _, eff_trend = aerobic_efficiency(summaries)
    prediction = predict_race_time(goal, build_snapshot(summaries), eff_trend)
    if prediction is None:
        raise HTTPException(
            status_code=404, detail="Nessun obiettivo gara configurato."
        )
    return prediction


@router.get("/checkin", response_model=DailyCheckin | None)
def get_checkin(session: Session = Depends(get_session)) -> DailyCheckin | None:
    return latest_checkin(session)


@router.post("/checkin", response_model=DailyCheckin, status_code=201)
def post_checkin(
    payload: DailyCheckin, session: Session = Depends(get_session)
) -> DailyCheckin:
    save_checkin(session, payload)
    _commit(session)
    return latest_checkin(session)


@router.get("/metrics", response_model=TrainingMetrics)
def get_metrics(session: Session = Depends(get_session)) -> TrainingMetrics:
    return compute_metrics(
        _all_summaries(session),
        profile=get_profile(session),
        checkin=latest_checkin(session),
    )


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


@router.get("/personal-records", response_model=list[PersonalRecord])
def get_personal_records(session: Session = Depends(get_session)) -> list[PersonalRecord]:
    """Best-ever performances per canonical distance, derived from stored activities."""
    from sqlalchemy import select as sa_select

    from app.db.models import Activity as ActivityModel

    activities = session.scalars(sa_select(ActivityModel)).all()
    return [PersonalRecord(**r) for r in compute_personal_records(list(activities))]


@router.get("/gamification", response_model=GamificationData)
def get_gamification(session: Session = Depends(get_session)) -> GamificationData:
    """Current running streak and earned badges."""
    from sqlalchemy import select as sa_select

    from app.db.models import Activity as ActivityModel

    activities = list(session.scalars(sa_select(ActivityModel)).all())
    current, best = compute_streak(activities)
    badges = [Badge(**b) for b in compute_badges(activities, current, best)]
    return GamificationData(
        streak_days=current,
        streak_days_best=best,
        total_badges_earned=sum(1 for b in badges if b.earned),
        badges=badges,
    )


@router.get("/stats", response_model=PeriodStats)
def get_stats(period: str = "all-time", session: Session = Depends(get_session)):
    """Aggregate running statistics for a time window (month|year|all-time)."""
    from datetime import date as _date

    from sqlalchemy import select as sa_select

    from app.db.models import Activity as ActivityModel
    from app.processing.records import _pace_sec

    _VALID_PERIODS = {"month", "year", "all-time"}
    if period not in _VALID_PERIODS:
        raise HTTPException(
            status_code=422,
            detail=f"period must be one of {sorted(_VALID_PERIODS)}",
        )

    stmt = sa_select(ActivityModel)
    today = _date.today()
    if period == "year":
        stmt = stmt.where(ActivityModel.date >= f"{today.year}-01-01")
    elif period == "month":
        stmt = stmt.where(ActivityModel.date >= f"{today.year}-{today.month:02d}-01")

    acts = list(session.scalars(stmt).all())

    total_km = sum(a.distance_km for a in acts)
    total_min = sum(a.duration_min for a in acts)
    total_elev = int(sum(a.elevation_gain_m or 0 for a in acts))
    longest = max((a.distance_km for a in acts), default=0.0)

    if total_km > 0:
        s = (total_min * 60) / total_km
        avg_pace = f"{int(s // 60)}:{int(s % 60):02d}/km"
    else:
        avg_pace = None

    fastest = min(
        (a.avg_pace for a in acts if a.avg_pace and a.distance_km >= 1.0),
        key=_pace_sec,
        default=None,
    )

    return PeriodStats(
        period=period,
        total_runs=len(acts),
        total_km=round(total_km, 1),
        total_duration_h=round(total_min / 60, 1),
        total_elevation_m=total_elev,
        avg_pace=avg_pace,
        longest_run_km=round(longest, 1),
        fastest_pace=fastest,
    )


@router.get("/export")
def export_data(format: str = "csv", session: Session = Depends(get_session)):
    """Download all activities as CSV or JSON (attachment)."""
    from sqlalchemy import select as sa_select

    from app.db.models import Activity as ActivityModel

    acts = list(
        session.scalars(
            sa_select(ActivityModel).order_by(ActivityModel.date.desc())
        ).all()
    )

    if format.lower() == "json":
        data = [ActivityOut.model_validate(a).model_dump() for a in acts]
        content = _json.dumps(data, indent=2, default=str)
        return StreamingResponse(
            iter([content]),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=activities.json"},
        )

    buf = io.StringIO()
    fields = list(ActivityOut.model_fields.keys())
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for a in acts:
        writer.writerow(ActivityOut.model_validate(a).model_dump())
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=activities.csv"},
    )


@router.get("/activities/heatmap", response_model=HeatmapResponse)
def get_heatmap(session: Session = Depends(get_session)) -> HeatmapResponse:
    rows = session.query(Activity).filter(
        Activity.route_polyline.isnot(None)
    ).order_by(Activity.date.desc()).limit(500).all()
    routes = []
    for row in rows:
        try:
            pts = _json.loads(row.route_polyline or "[]")
            if isinstance(pts, list) and len(pts) >= 2:
                routes.append(HeatmapRoute(
                    activity_id=row.id,
                    date=row.date if row.date else "",
                    distance_km=row.distance_km or 0.0,
                    points=pts,
                ))
        except Exception:
            continue
    total_activities = session.query(Activity).count()
    return HeatmapResponse(
        routes=routes,
        total_with_gps=len(routes),
        total_activities=total_activities,
    )


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
