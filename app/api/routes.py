"""REST API routes (JSON).

Mounted under ``/api``. The dashboard (HTML/HTMX) lives separately in main.py.
"""

from __future__ import annotations

import csv
import io
import json as _json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import __version__
from app.config import get_settings
from app.db.database import db_healthy, get_session
from app.db.models import Activity
from app.logging_config import get_logger
from app.processing import (
    aerobic_efficiency,
    build_periodization,
    build_snapshot,
    compute_metrics,
    compute_personal_records,
    predict_race_time,
    trail_metrics,
    weekly_buckets,
)
from app.schemas import (
    ActivityOut,
    ActivityPatch,
    AthleteProfile,
    AthleteSnapshot,
    CoachActionRequest,
    CoachDecision,
    CoachEventOut,
    DailyCheckin,
    ExecutionResult,
    GamificationData,
    HeatmapResponse,
    HeatmapRoute,
    ManualActivityIn,
    NotificationAck,
    NotificationOut,
    OnboardingStatus,
    PeriodizationPlan,
    PeriodStats,
    PersonalRecord,
    RacePrediction,
    ReportOut,
    RunSummary,
    ShoeIn,
    ShoeOut,
    TrailMetrics,
    TrainingMetrics,
    Vo2maxHistory,
    Vo2maxPoint,
    WeeklyBucket,
)
from app.services import (
    get_profile,
    hrv_history,
    ingest_cross_training,
    ingest_runs,
    latest_checkin,
    list_activities,
    list_cross_training,
    list_reports,
    run_single_analysis,
    run_weekly_plan,
    save_checkin,
    save_profile,
    upsert_activity,
)
from app.services.ingest import _all_summaries

router = APIRouter(prefix="/api", tags=["api"])
logger = get_logger("app.api")


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


def _adapt_after_change(session: Session, run_analysis: bool = False) -> None:
    """Best-effort post-sync pipeline: score executions, then adapt the plan.

    Compliance (Roadmap #9) is evaluated first so the adaptive engine (#8) can
    reason over what was actually executed. Never propagates: a failure here must
    not break the ingest/check-in call. Retries once with a short backoff before
    giving up (P0-9: no more silent failure).

    ``run_analysis=True`` (set when a sync brought >=1 new activity, Roadmap
    Q2) also generates the single-run coaching report, so the latest run
    always has one without the athlete tapping "Analizza". Its own Garmin
    pre-sync is skipped (``presync=False``): the ingest that triggered this
    already fetched everything fresh.
    """
    from app.utils import retry_call

    def _pipeline() -> None:
        from app.services.adaptive_plan import adapt_plan_after_sync
        from app.services.decision_service import (
            build_today_decision,
            record_decision_notification,
        )
        from app.services.execution_service import evaluate_plan_executions

        evaluate_plan_executions(session)
        adapt_plan_after_sync(session)
        if run_analysis:
            try:
                run_single_analysis(session, presync=False)
            except ValueError:
                pass  # no running activity to analyse yet
        decision = build_today_decision(session, persist=True)
        record_decision_notification(session, decision)
        _commit(session)

    try:
        retry_call(_pipeline, retries=2, base_delay=0.5, description="post-sync pipeline")
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        logger.error("Post-sync pipeline failed after retry: %s", exc, exc_info=True)


@router.post("/ingest", response_model=list[ActivityOut])
def post_ingest(limit: int | None = None, session: Session = Depends(get_session)):
    from app.services.sync_state import record_ingest, should_skip_ingest

    if should_skip_ingest(session):
        logger.info("ingest skipped, recent")
        return list_activities(session, limit=limit or get_settings().fetch_limit)

    before_count = session.scalar(select(func.count()).select_from(Activity)) or 0
    saved = ingest_runs(session, limit=limit)
    _commit(session)
    for a in saved:
        session.refresh(a)
    after_count = session.scalar(select(func.count()).select_from(Activity)) or 0
    record_ingest(session)
    _commit(session)
    _adapt_after_change(session, run_analysis=after_count > before_count)
    return saved


@router.post("/ingest/wellness")
def post_ingest_wellness(session: Session = Depends(get_session)) -> dict:
    """Auto-fetch Garmin wellness data (sleep, HRV, stress) for missing days."""
    from app.services.ingest_wellness import ingest_wellness

    count = ingest_wellness(session)
    _commit(session)
    return {"days_upserted": count}


@router.post("/ingest/cross-training", response_model=list[ActivityOut])
def post_ingest_cross_training(
    limit: int | None = None, session: Session = Depends(get_session)
):
    """Manually sync bike/swim/strength activities from Garmin (Feature 24)."""
    saved = ingest_cross_training(session, limit=limit)
    _commit(session)
    for a in saved:
        session.refresh(a)
    _adapt_after_change(session)
    return saved


@router.get("/activities/cross-training", response_model=list[ActivityOut])
def get_cross_training(
    limit: int = 50, session: Session = Depends(get_session)
) -> list[Activity]:
    """List stored bike/swim/strength activities, newest first (Feature 24)."""
    return list_cross_training(session, limit=limit)


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
    _adapt_after_change(session)
    return latest_checkin(session)


@router.get("/coach/today", response_model=CoachDecision)
def get_coach_today(session: Session = Depends(get_session)) -> CoachDecision:
    """Today's dominant coaching decision (Coach Decision Engine, Roadmap #7)."""
    from app.services.decision_service import get_today_decision

    decision = get_today_decision(session)
    _commit(session)
    return decision


@router.get("/coach/decisions", response_model=list[CoachDecision])
def get_coach_decisions(
    days: int = 14, session: Session = Depends(get_session)
) -> list[CoachDecision]:
    """Recent persisted decisions (decision history)."""
    from app.services.decision_service import recent_decisions

    return recent_decisions(session, days=days)


@router.post("/coach/today/action", response_model=CoachDecision)
def post_coach_action(
    payload: CoachActionRequest, session: Session = Depends(get_session)
) -> CoachDecision:
    """Act on today's decision (done | reduce | defer | problem) — Roadmap #2."""
    from app.services.decision_service import apply_coach_action

    try:
        decision = apply_coach_action(
            session, payload.action, payload.detail, rpe=payload.rpe
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _commit(session)
    return decision


@router.get("/plan/executions", response_model=list[ExecutionResult])
def get_plan_executions(
    days: int = 21, session: Session = Depends(get_session)
) -> list[ExecutionResult]:
    """Recent Workout Execution scores for the active plan (Roadmap #9)."""
    from app.services.execution_service import recent_executions

    return recent_executions(session, days=days)


@router.get("/coach/events", response_model=list[CoachEventOut])
def get_coach_events(
    days: int = 30, limit: int = 100, session: Session = Depends(get_session)
) -> list[CoachEventOut]:
    """The coach audit diary: decisions, adaptations and actions (Roadmap #5)."""
    from app.services.event_service import recent_events

    return recent_events(session, days=days, limit=limit)


@router.get("/notifications", response_model=list[NotificationOut])
def get_notifications(session: Session = Depends(get_session)) -> list[NotificationOut]:
    """Pending coach notifications tied to decisions/adaptations (Roadmap #6)."""
    from app.services.event_service import pending_notifications

    return pending_notifications(session)


@router.post("/notifications/ack")
def ack_notifications(
    payload: NotificationAck, session: Session = Depends(get_session)
) -> dict:
    """Mark notifications as delivered so they aren't shown again."""
    from app.services.event_service import mark_notified

    n = mark_notified(session, payload.ids)
    _commit(session)
    return {"acked": n}


@router.get("/metrics", response_model=TrainingMetrics)
def get_metrics(session: Session = Depends(get_session)) -> TrainingMetrics:
    return compute_metrics(
        _all_summaries(session),
        profile=get_profile(session),
        checkin=latest_checkin(session),
        hrv_history=hrv_history(session),
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

    activities = session.scalars(
        sa_select(ActivityModel).where(ActivityModel.sport == "run")
    ).all()
    return [PersonalRecord(**r) for r in compute_personal_records(list(activities))]


@router.get("/gamification", response_model=GamificationData)
def get_gamification(session: Session = Depends(get_session)) -> GamificationData:
    """Current plan-adherence streak (or legacy running streak) and earned badges."""
    from sqlalchemy import select as sa_select

    from app.db.models import Activity as ActivityModel
    from app.services.gamification_service import compute_gamification

    activities = list(
        session.scalars(sa_select(ActivityModel).where(ActivityModel.sport == "run")).all()
    )
    return compute_gamification(session, activities)


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

    stmt = sa_select(ActivityModel).where(ActivityModel.sport == "run")
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
            sa_select(ActivityModel)
            .where(ActivityModel.sport == "run")
            .order_by(ActivityModel.date.desc())
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


@router.get("/vo2max/history", response_model=Vo2maxHistory)
def get_vo2max_history(session: Session = Depends(get_session)) -> Vo2maxHistory:
    """Return the VO2max readings over time with a trend direction."""
    from sqlalchemy import select as sa_select

    from app.db.models import Activity as ActivityModel

    rows = session.scalars(
        sa_select(ActivityModel)
        .where(ActivityModel.vo2max.isnot(None), ActivityModel.sport == "run")
        .order_by(ActivityModel.date.asc())
    ).all()

    points = [Vo2maxPoint(date=str(r.date), vo2max=r.vo2max) for r in rows]

    if len(points) < 4:
        trend = "insufficient_data"
    else:
        mid = len(points) // 2
        first_avg = sum(p.vo2max for p in points[:mid]) / mid
        second_avg = sum(p.vo2max for p in points[mid:]) / (len(points) - mid)
        diff = second_avg - first_avg
        if diff > 0.5:
            trend = "improving"
        elif diff < -0.5:
            trend = "declining"
        else:
            trend = "stable"

    return Vo2maxHistory(points=points, trend=trend)


@router.get("/activities/heatmap", response_model=HeatmapResponse)
def get_heatmap(session: Session = Depends(get_session)) -> HeatmapResponse:
    rows = session.query(Activity).filter(
        Activity.route_polyline.isnot(None),
        Activity.sport == "run",
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
    total_activities = session.query(Activity).filter(Activity.sport == "run").count()
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
        confidence=report.confidence or "medium",
        missing_data=report.missing_data,
        created_at=report.created_at.isoformat() if report.created_at else None,
    )


# ── Onboarding checklist (Roadmap #4) ─────────────────────────────────────────


@router.get("/onboarding", response_model=OnboardingStatus)
def get_onboarding(session: Session = Depends(get_session)) -> OnboardingStatus:
    """Onboarding checklist status: which steps the athlete has completed."""
    from app.services.onboarding import get_onboarding_status

    return OnboardingStatus(**get_onboarding_status(session))


# ── Shoe tracking (Roadmap #6) ────────────────────────────────────────────────


@router.get("/shoes", response_model=list[ShoeOut])
def get_shoes(
    include_retired: bool = True, session: Session = Depends(get_session)
) -> list[ShoeOut]:
    from app.services.shoe_service import list_shoes

    return list_shoes(session, include_retired=include_retired)


@router.post("/shoes", response_model=ShoeOut, status_code=201)
def create_shoe(payload: ShoeIn, session: Session = Depends(get_session)) -> ShoeOut:
    from app.services.shoe_service import create_shoe

    shoe = create_shoe(session, payload)
    _commit(session)
    return shoe


@router.put("/shoes/{shoe_id}", response_model=ShoeOut)
def update_shoe(
    shoe_id: int, payload: ShoeIn, session: Session = Depends(get_session)
) -> ShoeOut:
    from app.services.shoe_service import update_shoe

    shoe = update_shoe(session, shoe_id, payload)
    if shoe is None:
        raise HTTPException(status_code=404, detail="Scarpa non trovata.")
    _commit(session)
    return shoe


@router.delete("/shoes/{shoe_id}")
def delete_shoe_endpoint(shoe_id: int, session: Session = Depends(get_session)) -> dict:
    from app.services.shoe_service import delete_shoe

    ok = delete_shoe(session, shoe_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Scarpa non trovata.")
    _commit(session)
    return {"deleted": True}


@router.patch("/activities/{activity_id}/shoe", response_model=ActivityOut)
def assign_shoe(
    activity_id: int,
    shoe_id: int | None = None,
    session: Session = Depends(get_session),
) -> Activity:
    from app.services.shoe_service import assign_activity_shoe

    ok = assign_activity_shoe(session, activity_id, shoe_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Attività o scarpa non trovata.")
    _commit(session)
    session.refresh(session.get(Activity, activity_id))
    return session.get(Activity, activity_id)
