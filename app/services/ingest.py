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
from app.collection.garmin_raw import GarminRawFetcher
from app.collection.sources import ActivitySource, GarminSource
from app.config import get_settings
from app.db.models import Activity, CoachingReport, RawActivityAsset
from app.exceptions import CollectionError
from app.logging_config import get_logger
from app.processing import (
    build_snapshot,
    compute_metrics,
    estimate_thresholds,
    weekly_buckets,
)
from app.schemas import CoachingResult, RunSummary
from app.services.checkin import hrv_history, latest_checkin
from app.services.profile import get_profile, save_profile
from app.storage import ObjectStore, get_object_store

logger = get_logger("app.services.ingest")


def _activity_to_summary(a: Activity) -> RunSummary:
    return RunSummary(
        garmin_activity_id=a.garmin_activity_id,
        strava_activity_id=a.strava_activity_id,
        health_connect_id=a.health_connect_id,
        live_id=a.live_id,
        date=a.date,
        start_time=a.start_time,
        sport=a.sport,
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
        laps=a.laps,
        is_indoor=a.is_indoor,
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
        altitude_profile=a.altitude_profile,
        route_polyline=a.route_polyline,
        shoe_id=a.shoe_id,
    )


# Source ranking for the same physical run. Garmin carries splits, HR zones,
# RPE and training load; Health Connect v0 derives pace from distance+duration
# and has no splits. When both describe the same activity the richer one wins.
_SOURCE_RANK = {"garmin": 3, "strava": 2, "health_connect": 1, "live": 0}

# Tolerances for deciding "this is the same run from another app". Two sources
# reading the same GPS track agree closely; the absolute floors keep short runs
# from failing a purely relative check.
_DUP_DURATION_TOL = 0.05
_DUP_DISTANCE_TOL = 0.05
_DUP_DURATION_FLOOR_MIN = 1.5
_DUP_DISTANCE_FLOOR_KM = 0.3


def _source_of(obj: Activity | RunSummary) -> str:
    if getattr(obj, "garmin_activity_id", None):
        return "garmin"
    if getattr(obj, "strava_activity_id", None):
        return "strava"
    if getattr(obj, "health_connect_id", None):
        return "health_connect"
    return "live"


def _close(a: float | None, b: float | None, tol: float, floor: float) -> bool:
    """True when two measurements of the same thing agree within tolerance."""
    if a is None or b is None:
        return False
    return abs(a - b) <= max(floor, tol * max(a, b))


def find_duplicate(session: Session, run: RunSummary) -> Activity | None:
    """The same physical run already stored under a *different* source id.

    Garmin and Health Connect both see the phone/watch's run but share no
    identifier, so an id-only upsert stores it twice — double-counting volume
    in every load metric downstream. Matching is deliberately conservative:
    same day, same sport, and both duration and distance within tolerance.
    """
    if not run.date:
        return None
    candidates = session.scalars(
        select(Activity).where(Activity.date == run.date, Activity.sport == run.sport)
    ).all()
    for other in candidates:
        # Never merge rows that both carry the *same kind* of id: two Garmin
        # activities on one day are two real runs, not a duplicate.
        if _source_of(other) == _source_of(run):
            continue
        if _close(
            run.duration_min, other.duration_min, _DUP_DURATION_TOL, _DUP_DURATION_FLOOR_MIN
        ) and _close(
            run.distance_km, other.distance_km, _DUP_DISTANCE_TOL, _DUP_DISTANCE_FLOOR_KM
        ):
            return other
    return None


def find_existing_duplicates(session: Session) -> list[tuple[Activity, Activity]]:
    """Duplicate pairs already stored as ``(keep, drop)``, richest source first.

    The id-only upsert that shipped first let the same run land twice (once per
    source). Those rows are still there and double-count in every load metric,
    so they need finding and merging, not just preventing.
    """
    rows = list(session.scalars(select(Activity).order_by(Activity.date.desc())).all())
    by_day: dict[tuple[str, str], list[Activity]] = {}
    for row in rows:
        by_day.setdefault((row.date, row.sport), []).append(row)

    pairs: list[tuple[Activity, Activity]] = []
    merged_ids: set[int] = set()
    for group in by_day.values():
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                if a.id in merged_ids or b.id in merged_ids:
                    continue
                if _source_of(a) == _source_of(b):
                    continue
                if not (
                    _close(a.duration_min, b.duration_min,
                           _DUP_DURATION_TOL, _DUP_DURATION_FLOOR_MIN)
                    and _close(a.distance_km, b.distance_km,
                               _DUP_DISTANCE_TOL, _DUP_DISTANCE_FLOOR_KM)
                ):
                    continue
                keep, drop = (
                    (a, b)
                    if _SOURCE_RANK[_source_of(a)] >= _SOURCE_RANK[_source_of(b)]
                    else (b, a)
                )
                pairs.append((keep, drop))
                merged_ids.add(drop.id)
    return pairs


def merge_duplicates(session: Session, dry_run: bool = True) -> list[dict]:
    """Merge duplicate activities, keeping the richest source of each pair.

    The surviving row inherits the other's external ids (so a future sync from
    either source matches it directly) and any field the richer source happens
    to be missing. Returns one report dict per pair, whether or not applied.
    """
    report: list[dict] = []
    for keep, drop in find_existing_duplicates(session):
        report.append({
            "date": keep.date,
            "distance_km": round(keep.distance_km or 0.0, 1),
            "kept": {"id": keep.id, "source": _source_of(keep)},
            "dropped": {"id": drop.id, "source": _source_of(drop)},
        })
        if dry_run:
            continue
        # Fill only genuine gaps: the richer source stays authoritative.
        for field in (
            "start_time", "avg_hr", "max_hr", "elevation_gain_m", "avg_cadence",
            "rpe", "notes", "hr_zones", "splits_km", "laps", "route_polyline",
        ):
            if getattr(keep, field, None) is None and getattr(drop, field, None) is not None:
                setattr(keep, field, getattr(drop, field))
        # Inherit the other source's ids so neither can re-create the duplicate
        # on the next sync. Each id column is UNIQUE, so the losing row has to
        # release its value (and that has to reach the database) before the
        # surviving row can take it.
        inherited = {
            field: getattr(drop, field)
            for field in (
                "garmin_activity_id", "strava_activity_id", "health_connect_id", "live_id",
            )
            if getattr(drop, field) and not getattr(keep, field)
        }
        for field in inherited:
            setattr(drop, field, None)
        session.flush()
        for field, value in inherited.items():
            setattr(keep, field, value)
        session.delete(drop)
    if not dry_run and report:
        session.flush()
        logger.info("Uniti %d duplicati", len(report))
    return report


def upsert_activity(session: Session, run: RunSummary) -> Activity:
    """Insert or update an activity, keyed on the Garmin or Strava id.

    An activity is matched on whichever external id the payload carries
    (Garmin first, then Strava), so the same run synced from either source
    updates one row rather than creating duplicates.
    """
    existing: Activity | None = None
    if run.garmin_activity_id:
        existing = session.scalar(
            select(Activity).where(Activity.garmin_activity_id == run.garmin_activity_id)
        )
    if existing is None and run.strava_activity_id:
        existing = session.scalar(
            select(Activity).where(Activity.strava_activity_id == run.strava_activity_id)
        )
    if existing is None and run.health_connect_id:
        existing = session.scalar(
            select(Activity).where(Activity.health_connect_id == run.health_connect_id)
        )
    if existing is None and run.live_id:
        existing = session.scalar(
            select(Activity).where(Activity.live_id == run.live_id)
        )
    # No id matched: the same run may still be here under another source's id
    # (Garmin + Health Connect see the same activity but share no identifier).
    if existing is None:
        existing = find_duplicate(session, run)
        if existing is not None:
            # Read both sources BEFORE linking ids: attaching the incoming id
            # would otherwise change what `existing` looks like it came from.
            incoming_source = _source_of(run)
            stored_source = _source_of(existing)
            logger.info(
                "Attività duplicata riconosciuta (%s già presente come %s): unita invece "
                "di essere duplicata — %s, %.1f km",
                incoming_source, stored_source, run.date, run.distance_km,
            )
            # Link the new id onto the existing row so the next sync matches
            # directly and this fuzzy path is never needed again.
            if run.garmin_activity_id and not existing.garmin_activity_id:
                existing.garmin_activity_id = run.garmin_activity_id
            if run.strava_activity_id and not existing.strava_activity_id:
                existing.strava_activity_id = run.strava_activity_id
            if run.health_connect_id and not existing.health_connect_id:
                existing.health_connect_id = run.health_connect_id
            if run.live_id and not existing.live_id:
                existing.live_id = run.live_id
            # A poorer source must not degrade a richer one: Health Connect's
            # derived pace would overwrite Garmin's measured one, and its
            # missing RPE/splits would look like "no data" rather than "not
            # carried by this source".
            if _SOURCE_RANK[incoming_source] < _SOURCE_RANK[stored_source]:
                session.flush()
                return existing

    if existing is None:
        existing = Activity(
            garmin_activity_id=run.garmin_activity_id,
            strava_activity_id=run.strava_activity_id,
            health_connect_id=run.health_connect_id,
            live_id=run.live_id,
        )
        session.add(existing)
    else:
        if run.strava_activity_id and not existing.strava_activity_id:
            existing.strava_activity_id = run.strava_activity_id
        if run.health_connect_id and not existing.health_connect_id:
            existing.health_connect_id = run.health_connect_id
        if run.live_id and not existing.live_id:
            existing.live_id = run.live_id

    existing.date = run.date
    if run.start_time is not None:
        existing.start_time = run.start_time
    existing.sport = run.sport
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
    # Semi-structured + Garmin rich metrics: only overwrite when the new
    # payload actually carries the value, so a transient details-fetch failure
    # does not erase good data from a previous successful sync.
    if run.hr_zones is not None:
        existing.hr_zones = run.hr_zones
    if run.splits_km is not None:
        existing.splits_km = run.splits_km
    if run.laps is not None:
        existing.laps = run.laps
    # A source that knows it was indoors wins; one that simply doesn't carry
    # the flag must not clear it (Health Connect has no such marker).
    if run.is_indoor:
        existing.is_indoor = True
    if run.temperature_c is not None:
        existing.temperature_c = run.temperature_c
    if run.humidity_pct is not None:
        existing.humidity_pct = run.humidity_pct
    if run.elevation_loss_m is not None:
        existing.elevation_loss_m = run.elevation_loss_m
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
    if run.aerobic_training_effect is not None:
        existing.aerobic_training_effect = run.aerobic_training_effect
    if run.anaerobic_training_effect is not None:
        existing.anaerobic_training_effect = run.anaerobic_training_effect
    if run.aerobic_te_message is not None:
        existing.aerobic_te_message = run.aerobic_te_message
    if run.anaerobic_te_message is not None:
        existing.anaerobic_te_message = run.anaerobic_te_message
    if run.altitude_profile is not None:
        existing.altitude_profile = run.altitude_profile
    if run.route_polyline is not None:
        existing.route_polyline = run.route_polyline
    if run.shoe_id is not None:
        existing.shoe_id = run.shoe_id
    return existing


def ingest_runs(
    session: Session, limit: int | None = None, source: ActivitySource | None = None
) -> list[Activity]:
    """Pull recent runs from the configured source and persist them.

    Side-effect: when raw archival is configured (S3 bucket + Garmin
    source), every recent activity (running or not) is also archived to
    object storage in the same call. Archival errors are logged but do
    not interrupt the summary ingest.
    """
    settings = get_settings()
    limit = limit or settings.fetch_limit
    source = source or get_source(settings)

    # For Garmin source, skip the heavy get_activity_details call for
    # activities that already have GPS data — avoids N redundant API calls
    # on every re-sync of existing activities.
    skip_gps_for: set[str] | None = None
    if isinstance(source, GarminSource):
        skip_gps_for = {
            a.garmin_activity_id
            for a in session.scalars(
                select(Activity).where(
                    Activity.garmin_activity_id.isnot(None),
                    Activity.route_polyline.isnot(None),
                )
            ).all()
            if a.garmin_activity_id
        }

    runs = source.get_recent_runs(limit, skip_gps_for=skip_gps_for)
    saved = [upsert_activity(session, r) for r in runs]
    session.flush()
    _refresh_physiology(session)

    # Cross-training is load too: a week with two hours on the bike and two gym
    # sessions is not a light week, even though it adds no running kilometres.
    # It used to arrive only via its own manual endpoint, so in practice it
    # never arrived at all. Best-effort: it must not break the run sync.
    _try_ingest_cross_training(session, source, limit)

    # Garmin rarely records temperature, and without it a coach reads August
    # heat as a loss of form. Only the runs just synced are considered, so this
    # is a couple of calls, not a sweep.
    _try_fill_weather(session, len(saved))

    # Fuelling belongs to the same picture as the load: a stalled block from an
    # energy deficit looks identical to one from too much training. A short
    # window, because a diary entry added two days late is normal.
    _try_sync_nutrition(session)

    if settings.raw_archive_active and isinstance(source, GarminSource):
        _try_sync_raw_assets(session, source, limit)

    return saved


def _try_ingest_cross_training(
    session: Session, source: ActivitySource, limit: int
) -> None:
    """Pull bike/swim/strength alongside the runs, never raising into the run path."""
    try:
        saved = ingest_cross_training(session, limit=limit, source=source)
        if saved:
            logger.info("Cross-training sincronizzato: %d sedute", len(saved))
    except Exception as exc:  # noqa: BLE001 - a secondary signal must not block ingest
        logger.warning("Sync cross-training fallito: %s", exc)


def _try_fill_weather(session: Session, recent_count: int) -> None:
    """Look up the weather for the runs just synced. Never raises."""
    if recent_count <= 0:
        return
    try:
        from app.services.weather_backfill import fill_missing_weather

        fill_missing_weather(session, limit=recent_count, throttle_s=0.0)
    except Exception as exc:  # noqa: BLE001 - weather is a nice-to-have
        logger.warning("Recupero meteo fallito: %s", exc)


def _try_sync_nutrition(session: Session) -> None:
    """Import the last few days of nutrition, if Yazio is connected. Never raises."""
    try:
        from app.services.yazio_sync import is_connected, try_sync_nutrition

        if not is_connected(session):
            return
        try_sync_nutrition(session, throttle_s=0.0)
    except Exception as exc:  # noqa: BLE001 - nutrition is context, not a dependency
        logger.warning("Sync nutrizione fallito: %s", exc)


def sync_raw_assets(
    session: Session,
    source: GarminSource,
    limit: int,
    store: ObjectStore | None = None,
) -> list[RawActivityAsset]:
    """Archive every raw Garmin payload (all activity types) to object storage.

    Skips ``(activity_id, kind)`` pairs already recorded in
    ``raw_activity_assets``: re-syncs are cheap and idempotent. Returns
    the newly created rows.
    """
    if store is None:
        store = get_object_store()
    if store is None:
        logger.debug("Raw archive skipped: object store not configured")
        return []

    activities = source.get_recent_activities(limit)
    if not activities:
        return []

    client = source.get_client()
    fetcher = GarminRawFetcher(client=client, store=store)
    new_rows: list[RawActivityAsset] = []

    for activity in activities:
        activity_id = activity.get("activityId")
        if activity_id is None:
            continue
        activity_id_str = str(activity_id)
        type_field = activity.get("activityType") or {}
        type_key = type_field.get("typeKey") if isinstance(type_field, dict) else None

        existing_kinds = set(
            session.scalars(
                select(RawActivityAsset.kind).where(
                    RawActivityAsset.garmin_activity_id == activity_id_str
                )
            ).all()
        )

        assets = fetcher.fetch_all(
            activity_id=activity_id_str,
            activity_type_key=type_key,
            already_archived_kinds=existing_kinds,
        )
        for asset in assets:
            row = RawActivityAsset(
                garmin_activity_id=asset.activity_id,
                activity_type_key=asset.activity_type_key,
                kind=asset.kind,
                s3_key=asset.s3_key,
                content_type=asset.content_type,
                size_bytes=asset.size_bytes,
                sha256=asset.sha256,
            )
            session.add(row)
            new_rows.append(row)

    if new_rows:
        session.flush()
        logger.info(
            "Archived %d raw assets across %d activities",
            len(new_rows),
            len({r.garmin_activity_id for r in new_rows}),
        )
    return new_rows


def _try_sync_raw_assets(session: Session, source: GarminSource, limit: int) -> None:
    """Best-effort raw archive. Never raises into the summary ingest path."""
    try:
        sync_raw_assets(session, source, limit)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Raw archive step failed: %s", exc)


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


def _refresh_physiology(session: Session) -> None:
    """Auto-fill the athlete's thresholds from recent hard efforts (GAP 7).

    Only writes when the profile exists and the LT2 pace hasn't been set by
    hand, so the estimate tracks fitness without overriding manual input.
    """
    profile = get_profile(session)
    if profile is None:
        return
    if profile.physiology and profile.physiology.lt2_pace:
        return
    estimated = estimate_thresholds(_all_summaries(session))
    if estimated is None:
        return
    profile.physiology = estimated
    save_profile(session, profile)


def list_activities(session: Session, limit: int = 50) -> list[Activity]:
    """List running activities only (cross-training has its own listing)."""
    return list(
        session.scalars(
            select(Activity)
            .where(Activity.sport == "run")
            .order_by(Activity.date.desc())
            .limit(limit)
        ).all()
    )


def list_cross_training(session: Session, limit: int = 50) -> list[Activity]:
    """List bike/swim/strength activities (Feature 24), newest first."""
    return list(
        session.scalars(
            select(Activity)
            .where(Activity.sport != "run")
            .order_by(Activity.date.desc())
            .limit(limit)
        ).all()
    )


def ingest_cross_training(
    session: Session, limit: int | None = None, source: ActivitySource | None = None
) -> list[Activity]:
    """Pull recent bike/swim/strength activities from the source and persist.

    Garmin's manual-sync counterpart to :func:`ingest_runs`. Cross-training is
    stored in the same table but tagged with ``sport`` so it never enters the
    running load/form pipeline. Sources without cross-training support (e.g.
    minimal test doubles) are handled gracefully.
    """
    settings = get_settings()
    limit = limit or settings.fetch_limit
    source = source or get_source(settings)

    fetch = getattr(source, "get_recent_cross_training", None)
    if not callable(fetch):
        return []

    activities = fetch(limit)
    saved = [upsert_activity(session, a) for a in activities]
    session.flush()
    return saved


def list_reports(session: Session, limit: int = 20) -> list[CoachingReport]:
    return list(
        session.scalars(
            select(CoachingReport).order_by(CoachingReport.created_at.desc()).limit(limit)
        ).all()
    )


def _all_summaries(session: Session) -> list[RunSummary]:
    """Running activities only — the running coaching pipeline must stay pure.

    Cross-training (bike/swim/strength) is deliberately excluded so it never
    pollutes CTL/ATL/TSB, ACWR, intensity distribution, PRs or streaks.
    """
    rows = session.scalars(
        select(Activity).where(Activity.sport == "run").order_by(Activity.date.desc())
    ).all()
    return [_activity_to_summary(a) for a in rows]


def run_single_analysis(
    session: Session,
    activity_id: int | None = None,
    coach: Coach | None = None,
    ref: date | None = None,
    source: ActivitySource | None = None,
    presync: bool = True,
) -> CoachingReport:
    """Analyse one run (most recent by default) and persist the report.

    Triggers a Garmin sync first so any new activities and rich metrics
    that have appeared since the last ingest are reflected in the analysis.
    ``presync=False`` skips that sync — used right after an ingest already
    ran in the same request, so the auto-analysis doesn't trigger a second
    redundant Garmin fetch (Roadmap Q2).
    """
    if presync:
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
        summaries, ref=ref, profile=profile, checkin=latest_checkin(session),
        hrv_history=hrv_history(session, ref=ref),
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
        summaries, ref=ref, profile=profile, checkin=latest_checkin(session),
        hrv_history=hrv_history(session, ref=ref),
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
        confidence=result.confidence,
        missing_data=result.missing_data or None,
    )
    session.add(report)
    session.flush()
    return report
