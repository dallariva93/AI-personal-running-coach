"""Health Connect import (Roadmap A2): runs + wellness without Garmin.

The Android ``HealthConnectSyncWorker`` reads running sessions (and sleep/HRV)
from Android Health Connect and POSTs a compact batch here. This service maps
each session onto the existing :class:`RunSummary` contract — deriving pace from
distance+duration (v0 has no real per-km splits) and inferring the session type
from the fields available — then reuses :func:`upsert_activity`. Wellness rows
upsert the day's check-in with ``source="health_connect"``, honouring the A4
source precedence so a voice/manual entry is never overwritten.

Dedup note (v0): sessions are deduped on ``health_connect_id``. A run that also
came from Strava (no shared id) is accepted as a duplicate; a date+duration±2%
heuristic is documented as backlog.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.collection.synthesize import _infer_type
from app.db.models import Activity
from app.logging_config import get_logger
from app.schemas import (
    DailyCheckin,
    HealthConnectImportIn,
    HealthConnectRun,
    RunSummary,
)
from app.services.checkin import save_checkin
from app.services.ingest import upsert_activity

logger = get_logger("app.services.health_connect")


def _derive_pace(distance_km: float, duration_min: float) -> str | None:
    """Average pace "M:SS/km" from distance + duration (v0, no real splits)."""
    if distance_km <= 0 or duration_min <= 0:
        return None
    sec_per_km = (duration_min * 60.0) / distance_km
    minutes, seconds = divmod(int(round(sec_per_km)), 60)
    return f"{minutes}:{seconds:02d}/km"


def _hr_from_samples(samples: list[int] | None) -> tuple[int | None, int | None]:
    """(avg, max) bpm from a sampled series, or (None, None)."""
    valid = [s for s in (samples or []) if s and s > 0]
    if not valid:
        return None, None
    return round(sum(valid) / len(valid)), max(valid)


def _run_to_summary(run: HealthConnectRun) -> RunSummary:
    avg_hr, max_hr = run.avg_hr, run.max_hr
    if avg_hr is None or max_hr is None:
        s_avg, s_max = _hr_from_samples(run.hr_samples)
        avg_hr = avg_hr if avg_hr is not None else s_avg
        max_hr = max_hr if max_hr is not None else s_max

    # Reuse the Garmin type cascade with the fields Health Connect gives us
    # (name → trail/distance → easy). No training-effect signal available.
    activity_type = _infer_type({
        "activityName": run.name or "",
        "distance": run.distance_km * 1000.0,
        "elevationGain": run.elevation_gain_m or 0.0,
    })

    return RunSummary(
        health_connect_id=run.health_connect_id,
        date=run.date,
        start_time=run.start_time,
        sport="run",
        activity_type=activity_type,
        duration_min=run.duration_min,
        distance_km=run.distance_km,
        avg_pace=_derive_pace(run.distance_km, run.duration_min),
        avg_hr=avg_hr,
        max_hr=max_hr,
        elevation_gain_m=run.elevation_gain_m,
        route_polyline=run.route_polyline,
        notes=run.name,
    )


def import_health_connect(
    db: Session, payload: HealthConnectImportIn
) -> tuple[list[Activity], int]:
    """Persist a Health Connect batch. Returns (activities, wellness_days)."""
    activities: list[Activity] = []
    for run in payload.runs:
        activities.append(upsert_activity(db, _run_to_summary(run)))

    wellness_days = 0
    for w in payload.wellness:
        if w.sleep_h is None and w.hrv_rmssd is None:
            continue
        save_checkin(
            db,
            DailyCheckin(
                date=w.date,
                sleep_h=w.sleep_h,
                hrv_rmssd=w.hrv_rmssd,
                source="health_connect",  # A4 precedence: never overwrites voice
            ),
        )
        wellness_days += 1

    db.flush()
    logger.info(
        "Health Connect import: %d run(s), %d wellness day(s)",
        len(activities), wellness_days,
    )
    return activities, wellness_days
