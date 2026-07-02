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
from app.db.models import Activity as ActivityModel
from app.db.models import CoachingReport
from app.processing import (
    aerobic_efficiency,
    build_periodization,
    build_snapshot,
    compute_badges,
    compute_metrics,
    compute_personal_records,
    compute_streak,
    predict_race_time,
    weekly_buckets,
)
from app.schemas import ActivityOut, ReportOut, TrainingMetrics, WeeklyBucket
from app.services import get_profile, hrv_history, latest_checkin, list_activities
from app.services.ingest import _all_summaries
from app.services.plan_service import get_current_plan
from app.services.workout_service import list_workouts

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
        confidence=report.confidence or "medium",
        missing_data=report.missing_data,
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
    from sqlalchemy import select as sa_select

    settings = get_settings()
    summaries = _all_summaries(session)
    # Running only: PRs, streaks and badges are running achievements and must
    # not count cross-training (Feature 24).
    all_activities_orm = list(
        session.scalars(sa_select(ActivityModel).where(ActivityModel.sport == "run")).all()
    )
    profile = get_profile(session)
    checkin = latest_checkin(session)
    metrics: TrainingMetrics = compute_metrics(
        summaries, profile=profile, checkin=checkin, hrv_history=hrv_history(session)
    )
    weekly: list[WeeklyBucket] = weekly_buckets(summaries, weeks=8)
    activities = [ActivityOut.model_validate(a) for a in list_activities(session, limit=30)]
    snapshot = build_snapshot(summaries)

    # Personal records + gamification (streak / badges).
    prs = compute_personal_records(all_activities_orm)
    pr_activity_ids = [r["activity_id"] for r in prs if r.get("activity_id")]
    streak_days, streak_best = compute_streak(all_activities_orm)
    raw_badges = compute_badges(all_activities_orm, streak_days, streak_best)
    gamification = {
        "streak_days": streak_days,
        "streak_days_best": streak_best,
        "total_badges_earned": sum(1 for b in raw_badges if b["earned"]),
        "badges": raw_badges,
    }

    goal = profile.goal if profile else None
    prediction = plan = None
    if goal:
        _, eff_trend = aerobic_efficiency(summaries)
        prediction = predict_race_time(goal, snapshot, eff_trend)
        baseline = max(metrics.chronic_load_km, metrics.acute_load_km / 1.5, 20.0)
        plan = build_periodization(goal, baseline_km=baseline)

    # Active multi-week training plan
    active_plan = get_current_plan(session)

    # Coach Decision Engine: the dominant "what to do today" (Roadmap #7).
    from app.services.decision_service import build_today_decision
    from app.services.event_service import pending_notifications

    today_decision = build_today_decision(session, persist=False)
    notifications = pending_notifications(session)

    # Workout library count
    saved_workouts = list_workouts(session)
    saved_workout_count = len(saved_workouts)

    # Onboarding checklist (Roadmap #4)
    from app.services.onboarding import get_onboarding_status
    from app.services.shoe_service import list_shoes

    onboarding = get_onboarding_status(session)
    shoes = [s.model_dump() for s in list_shoes(session)]

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
        "personal_records": prs,
        "pr_activity_ids": pr_activity_ids,
        "gamification": gamification,
        "active_plan": active_plan.model_dump() if active_plan else None,
        "saved_workout_count": saved_workout_count,
        "today_decision": today_decision.model_dump(),
        "notifications": [n.model_dump() for n in notifications],
        "onboarding": onboarding,
        "shoes": shoes,
    }
