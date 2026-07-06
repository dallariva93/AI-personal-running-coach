"""Import of phone-recorded live runs (G1, milestone M1).

The Android offline queue POSTs each finished recording here — possibly more
than once (WorkManager retries after any network hiccup), so the whole import
is idempotent on the client-generated ``live_id``: `upsert_activity` updates
the same row instead of duplicating. The recording never gets lost and never
gets doubled — the two failure modes that matter.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.collection.synthesize import _infer_type
from app.db.models import Activity
from app.logging_config import get_logger
from app.processing.live import derive_avg_pace, derive_hr, derive_splits
from app.schemas import LiveRunIn, RunSummary
from app.services.ingest import upsert_activity

logger = get_logger("app.services.live_import")


def import_live_run(db: Session, payload: LiveRunIn) -> Activity:
    """Synthesize Garmin-grade fields from the recording and persist it."""
    avg_hr, max_hr = derive_hr(payload.samples)
    summary = RunSummary(
        live_id=payload.live_id,
        date=payload.date,
        start_time=payload.start_time,
        sport="run",
        # Same cascade as every other source: athlete-named type wins, then
        # distance (>=14 km → lungo), defaulting to easy. No training effect
        # exists on a phone recording, so the cascade degrades exactly as
        # designed for Health Connect (A2).
        activity_type=_infer_type({
            "activityName": payload.name or "",
            "distance": payload.distance_km * 1000.0,
            "elevationGain": 0.0,
        }),
        duration_min=payload.duration_min,
        distance_km=payload.distance_km,
        avg_pace=derive_avg_pace(payload.distance_km, payload.duration_min),
        avg_hr=avg_hr,
        max_hr=max_hr,
        splits_km=derive_splits(payload.samples, payload.laps, payload.distance_km),
        route_polyline=payload.route_polyline,
        notes=payload.name,
    )
    activity = upsert_activity(db, summary)
    db.flush()
    logger.info(
        "Live run imported: live_id=%s date=%s %.2fkm (%d samples, %d laps)",
        payload.live_id, payload.date, payload.distance_km,
        len(payload.samples), len(payload.laps),
    )
    return activity
