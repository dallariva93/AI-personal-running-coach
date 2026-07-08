"""Capture Garmin's native daily wellness snapshots (GARMIN_DATA_PLAN.md phase 0c).

A cheap daily job that stores Garmin's own live values verbatim in
``daily_wellness`` the day they exist, because Garmin may stop exposing them
over time (A3). Distinct from :mod:`app.services.ingest_wellness`, which maps
the same raw data onto the subjective 1-10 check-in scale for the coach.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collection.wellness_snapshot import build_wellness_snapshot
from app.config import get_settings
from app.db.models import DailyWellnessRow
from app.logging_config import get_logger
from app.schemas import DailyWellnessSnapshot

logger = get_logger("app.services.wellness_snapshot")

_UPSERT_FIELDS = (
    "sleep_seconds",
    "sleep_score",
    "hrv_last_night_avg",
    "hrv_status",
    "resting_hr",
    "body_battery_charged",
    "body_battery_drained",
    "stress_avg",
    "training_readiness_score",
    "training_readiness_level",
)


def _safe(fn: Any, *args: Any) -> Any:
    """Call a Garmin endpoint, swallowing failures (A11: one bad call is not fatal)."""
    try:
        return fn(*args)
    except Exception as exc:  # noqa: BLE001 - a single endpoint must not abort the snapshot
        logger.debug("wellness snapshot API call failed: %s", exc)
        return None


def _snapshot_for_day(client: Any, date_str: str) -> DailyWellnessSnapshot:
    return build_wellness_snapshot(
        date_str,
        sleep=_safe(client.get_sleep_data, date_str),
        hrv=_safe(client.get_hrv_data, date_str),
        stress=_safe(client.get_stress_data, date_str),
        body_battery=_safe(client.get_body_battery, date_str, date_str),
        resting_hr=_safe(client.get_rhr_day, date_str),
        training_readiness=_safe(client.get_training_readiness, date_str),
    )


def _upsert(session: Session, snap: DailyWellnessSnapshot) -> None:
    """Insert or update the row for ``snap.date``, only filling non-None metrics.

    Never nulls a previously captured value: a later refresh where an endpoint
    momentarily returns nothing must not erase yesterday's good reading.
    """
    row = session.scalars(
        select(DailyWellnessRow).where(DailyWellnessRow.date == snap.date)
    ).first()
    if row is None:
        row = DailyWellnessRow(date=snap.date)
        session.add(row)
    for field in _UPSERT_FIELDS:
        value = getattr(snap, field)
        if value is not None:
            setattr(row, field, value)
    row.source = snap.source


def snapshot_daily_wellness(
    session: Session, days: int = 7, client: Any | None = None
) -> int:
    """Snapshot native Garmin wellness for each missing recent day.

    Skips days already captured (except today, always refreshed) so re-runs are
    cheap and idempotent. ``client`` may be injected for testing; otherwise a
    :class:`~app.collection.sources.GarminSource` client is built. Returns the
    number of days written.
    """
    if client is None:
        settings = get_settings()
        if not settings.garmin_enabled:
            logger.info("Garmin not configured — wellness snapshot skipped")
            return 0
        from app.collection.sources import GarminSource

        try:
            client = GarminSource(settings).get_client()
        except Exception as exc:  # noqa: BLE001 - login failure is non-fatal, just skip
            logger.warning("Garmin login failed for wellness snapshot: %s", exc)
            return 0

    today = date.today()
    cutoff = (today - timedelta(days=days)).isoformat()
    today_str = today.isoformat()
    existing = {
        row.date
        for row in session.scalars(
            select(DailyWellnessRow).where(DailyWellnessRow.date >= cutoff)
        ).all()
        if row.date != today_str  # always re-fetch today
    }

    written = 0
    for i in range(days):
        date_str = (today - timedelta(days=i)).isoformat()
        if date_str in existing:
            continue
        snapshot = _snapshot_for_day(client, date_str)
        if snapshot.is_empty():
            continue
        _upsert(session, snapshot)
        written += 1

    logger.info("Wellness snapshot: %d day(s) written", written)
    return written
