"""Orchestration: glue the independent layers into useful workflows.

This is the only module that knows about all four layers at once. Everything
else stays decoupled and unit-testable in isolation.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.coaching import get_coach
from app.coaching.coach import Coach
from app.collection import get_source
from app.collection.sources import ActivitySource
from app.config import get_settings
from app.db.models import Activity, CoachingReport
from app.exceptions import CollectionError
from app.logging_config import get_logger
from app.processing import build_snapshot, compute_metrics, weekly_buckets
from app.schemas import CoachingResult, RunSummary
from app.services.checkin import latest_checkin
from app.services.profile import get_profile

logger = get_logger("app.services.ingest")


def _activity_to_summary(a: Activity) -> RunSummary:
    return RunSummary(
        garmin_activity_id=a.garmin_activity_id,
        date=a.date,
        activity_type=a.activity_type,
        duration_min=a.duration_min,
        distance_km=a.distance_km,
        avg_pace=a.avg_pace,
        avg_hr=a.avg_hr,
        max_hr=a.max_hr,
        elevation_gain_m=a.elevation_gain_m,
        avg_cadence=a.avg_cadence,
        rpe=a.rpe,
        notes=a.notes,
        hr_zones=a.hr_zones,
        splits_km=a.splits_km,
        temperature_c=a.temperature_c,
        humidity_pct=a.humidity_pct,
        elevation_loss_m=a.elevation_loss_m,
        garmin_training_load=a.garmin_training_load,
        vigorous_minutes=a.vigorous_minutes,
        moderate_minutes=a.moderate_minutes,
        body_battery_delta=a.body_battery_delta,
        stamina_drop=a.stamina_drop,
        avg_grade_adjusted_pace=a.avg_grade_adjusted_pace,
        fastest_split_1k=a.fastest_split_1k,
        fastest_split_5k=a.fastest_split_5k,
        vo2max=a.vo2max,
        aerobic_te_message=a.aerobic_te_message,
        anaerobic_te_message=a.anaerobic_te_message,
    )


def upsert_activity(session: Session, run: RunSummary) -> Activity:
    """Insert or update an activity, keyed on the Garmin id when present."""
    existing: Activity | None = None
    if run.garmin_activity_id:
        existing = session.scalar(
            select(Activity).where(Activity.garmin_activity_id == run.garmin_activity_id)
        )
    if existing is None:
        existing = Activity(garmin_activity_id=run.garmin_activity_id)
        session.add(existing)

    existing.date = run.date
    existing.activity_type = run.activity_type
    existing.duration_min = run.duration_min
    existing.distance_km = run.distance_km
    existing.avg_pace = run.avg_pace
    existing.avg_hr = run.avg_hr
    existing.max_hr = run.max_hr
    existing.elevation_gain_m = run.elevation_gain_m
    existing.avg_cadence = run.avg_cadence
    if run.rpe is not None:
        existing.rpe = run.rpe
    if run.notes is not None:
        existing.notes = run.notes
    existing.hr_zones = run.hr_zones
    existing.splits_km = run.splits_km
    existing.temperature_c = run.temperature_c
    existing.humidity_pct = run.humidity_pct
    existing.elevation_loss_m = run.elevation_loss_m
    # Garmin rich metrics: only overwrite when the new payload actually carries
    # the value, so a transient details fetch failure does not erase good data
    # from a previous successful sync.
    if run.garmin_training_load is not None:
        existing.garmin_training_load = run.garmin_training_load
    if run.vigorous_minutes is not None:
        existing.vigorous_minutes = run.vigorous_minutes
    if run.moderate_minutes is not None:
        existing.moderate_minutes = run.moderate_minutes
    if run.body_battery_delta is not None:
        existing.body_battery_delta = run.body_battery_delta
    if run.stamina_drop is not None:
        existing.stamina_drop = run.stamina_drop
    if run.avg_grade_adjusted_pace is not None:
        existing.avg_grade_adjusted_pace = run.avg_grade_adjusted_pace
    if run.fastest_split_1k is not None:
        existing.fastest_split_1k = run.fastest_split_1k
    if run.fastest_split_5k is not None:
        existing.fastest_split_5k = run.fastest_split_5k
    if run.vo2max is not None:
        existing.vo2max = run.vo2max
    if run.aerobic_te_message is not None:
        existing.aerobic_te_message = run.aerobic_te_message
    if run.anaerobic_te_message is not None:
        existing.anaerobic_te_message = run.anaerobic_te_message
    return existing


def ingest_runs(
    session: Session, limit: int | None = None, source: ActivitySource | None = None
) -> list[Activity]:
    """Pull recent runs from the configured source and persist them."""
    settings = get_settings()
    limit = limit or settings.fetch_limit
    source = source or get_source(settings)
    runs = source.get_recent_runs(limit)
    saved = [upsert_activity(session, r) for r in runs]
    session.flush()
    return saved


def sync_before_analysis(
    session: Session, source: ActivitySource | None = None
) -> int:
    """Run a best-effort ingest before any AI analysis.

    Ensures that the activities the coach reasons about are as fresh as
    possible (new runs since last ingest, plus any Garmin rich-metrics
    that arrived after the initial sync). Failures are logged but never
    propagated: an offline / rate-limited Garmin must not block the
    analysis on data we already have.

    Returns the number of activities touched (0 on failure).
    """
    try:
        saved = ingest_runs(session, source=source)
    except (CollectionError, Exception) as exc:  # noqa: BLE001
        logger.warning("Pre-analysis sync skipped: %s", exc)
        return 0
    return len(saved)


def list_activities(session: Session, limit: int = 50) -> list[Activity]:
    return list(
        session.scalars(select(Activity).order_by(Activity.date.desc()).limit(limit)).all()
    )


def list_reports(session: Session, limit: int = 20) -> list[CoachingReport]:
    return list(
        session.scalars(
            select(CoachingReport).order_by(CoachingReport.created_at.desc()).limit(limit)
        ).all()
    )


def _all_summaries(session: Session) -> list[RunSummary]:
    rows = session.scalars(select(Activity).order_by(Activity.date.desc())).all()
    return [_activity_to_summary(a) for a in rows]


def run_single_analysis(
    session: Session,
    activity_id: int | None = None,
    coach: Coach | None = None,
    ref: date | None = None,
    source: ActivitySource | None = None,
) -> CoachingReport:
    """Analyse one run (most recent by default) and persist the report.

    Triggers a Garmin sync first so any new activities and rich metrics
    that have appeared since the last ingest are reflected in the analysis.
    """
    sync_before_analysis(session, source=source)
    summaries = _all_summaries(session)
    if not summaries:
        raise ValueError("Nessuna attività disponibile: esegui prima un ingest.")

    if activity_id is not None:
        target = session.get(Activity, activity_id)
        if target is None:
            raise ValueError(f"Attività {activity_id} non trovata.")
        target_summary = _activity_to_summary(target)
    else:
        target = session.scalar(select(Activity).order_by(Activity.date.desc()).limit(1))
        target_summary = summaries[0]

    history = [s for s in summaries if s.date < target_summary.date or s != target_summary][:10]
    profile = get_profile(session)
    metrics = compute_metrics(
        summaries, ref=ref, profile=profile, checkin=latest_checkin(session)
    )

    coach = coach or get_coach()
    result = coach.analyze_run(target_summary, history, metrics, profile)
    return _persist_report(session, result, metrics, activity_id=target.id if target else None)


def run_weekly_plan(
    session: Session,
    coach: Coach | None = None,
    ref: date | None = None,
    source: ActivitySource | None = None,
) -> CoachingReport:
    """Produce a weekly analysis + plan and persist the report.

    Triggers a Garmin sync first so every activity in the week has the
    latest rich metrics (training load, stamina, etc.) populated.
    """
    sync_before_analysis(session, source=source)
    summaries = _all_summaries(session)
    if not summaries:
        raise ValueError("Nessuna attività disponibile: esegui prima un ingest.")

    profile = get_profile(session)
    metrics = compute_metrics(
        summaries, ref=ref, profile=profile, checkin=latest_checkin(session)
    )
    weekly = [b.model_dump() for b in weekly_buckets(summaries)]
    snapshot = build_snapshot(summaries, ref=ref)
    coach = coach or get_coach()
    result = coach.plan_week(summaries, metrics, weekly, profile, snapshot)
    return _persist_report(session, result, metrics, activity_id=None)


def _persist_report(
    session: Session, result: CoachingResult, metrics, activity_id: int | None
) -> CoachingReport:
    report = CoachingReport(
        activity_id=activity_id,
        scope=result.scope,
        model=result.model,
        analysis=result.analysis,
        next_workout=result.next_workout,
        metrics=metrics.model_dump(),
    )
    session.add(report)
    session.flush()
    return report
