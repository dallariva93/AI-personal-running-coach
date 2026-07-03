"""Auto-ingest Garmin wellness data (sleep, HRV, stress, body battery) as checkins."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import DailyCheckinRow
from app.logging_config import get_logger
from app.schemas import DailyCheckin
from app.services.checkin import save_checkin

logger = get_logger("app.services.wellness")


def _safe(fn: Any, *args: Any) -> Any:
    try:
        return fn(*args)
    except Exception as exc:
        logger.debug("wellness API call failed: %s", exc)
        return None


def _extract_sleep_h(raw: Any) -> float | None:
    if not isinstance(raw, dict):
        return None
    dto = raw.get("dailySleepDTO") or {}
    secs = dto.get("sleepTimeSeconds") or dto.get("sleepTime")
    if secs and secs > 0:
        return round(secs / 3600, 1)
    return None


def _extract_hrv(raw: Any) -> float | None:
    if not isinstance(raw, dict):
        return None
    # Structure: {"hrv": {"lastNight": [{"rmssd": float, ...}]}}
    inner = raw.get("hrv") or raw
    last_night = inner.get("lastNight") or []
    vals = [x["rmssd"] for x in last_night if isinstance(x, dict) and x.get("rmssd")]
    if vals:
        return round(sum(vals) / len(vals), 1)
    return None


def _extract_fatigue(raw: Any) -> int | None:
    """Map average Garmin stress score (0–100) to fatigue (1–10)."""
    if not isinstance(raw, dict):
        return None
    avg = raw.get("avgStressLevel") or raw.get("averageStressLevel")
    if avg is not None and avg > 0:
        return max(1, min(10, round(avg / 10)))
    return None


def _extract_motivation(raw: Any) -> int | None:
    """Map peak body-battery charge (0–100) to motivation (1–10)."""
    if not isinstance(raw, list | dict):
        return None
    items = raw if isinstance(raw, list) else [raw]
    vals = [x["charged"] for x in items if isinstance(x, dict) and x.get("charged") is not None]
    if vals:
        return max(1, min(10, round(max(vals) / 10)))
    return None


def ingest_wellness(session: Session, days: int = 30) -> int:
    """Fetch Garmin wellness data for each missing day and persist as check-ins.

    Skips historical days that already have a check-in; always refreshes today.
    Returns the number of days upserted.
    """
    settings = get_settings()
    if not settings.garmin_enabled:
        logger.info("Garmin not configured — wellness ingest skipped")
        return 0

    from app.collection.sources import GarminSource

    source = GarminSource(settings)
    try:
        client = source.get_client()
    except Exception as exc:
        logger.warning("Garmin login failed for wellness ingest: %s", exc)
        return 0

    today = date.today()
    cutoff = (today - timedelta(days=days)).isoformat()

    # Collect dates that already have data (skip them for efficiency).
    existing = {
        row.date
        for row in session.scalars(
            select(DailyCheckinRow).where(DailyCheckinRow.date >= cutoff)
        ).all()
        if row.date != today.isoformat()  # always re-fetch today
    }

    upserted = 0
    for i in range(days):
        target = today - timedelta(days=i)
        date_str = target.isoformat()

        if date_str in existing:
            continue

        sleep_h = _extract_sleep_h(_safe(client.get_sleep_data, date_str))
        hrv_rmssd = _extract_hrv(_safe(client.get_hrv_data, date_str))
        fatigue = _extract_fatigue(_safe(client.get_stress_data, date_str))
        motivation = _extract_motivation(_safe(client.get_body_battery, date_str, date_str))

        if all(v is None for v in (sleep_h, hrv_rmssd, fatigue, motivation)):
            continue

        save_checkin(
            session,
            DailyCheckin(
                date=date_str,
                sleep_h=sleep_h,
                hrv_rmssd=hrv_rmssd,
                fatigue=fatigue,
                motivation=motivation,
                source="garmin_proxy",  # never overwrites a voice debrief (A4)
            ),
        )
        upserted += 1

    logger.info("Wellness ingest: %d day(s) upserted", upserted)
    return upserted
