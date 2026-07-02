"""Persist and retrieve daily wellness check-ins (GAP 9)."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DailyCheckinRow
from app.schemas import DailyCheckin


def _row_to_schema(row: DailyCheckinRow) -> DailyCheckin:
    return DailyCheckin(
        date=row.date,
        sleep_h=row.sleep_h,
        fatigue=row.fatigue,
        soreness=row.soreness,
        motivation=row.motivation,
        notes=row.notes,
        hrv_rmssd=row.hrv_rmssd,
    )


def save_checkin(session: Session, checkin: DailyCheckin) -> DailyCheckinRow:
    """Insert or update the check-in for its date (one per day)."""
    row = session.scalar(
        select(DailyCheckinRow).where(DailyCheckinRow.date == checkin.date)
    )
    if row is None:
        row = DailyCheckinRow(date=checkin.date)
        session.add(row)
    row.sleep_h = checkin.sleep_h
    row.fatigue = checkin.fatigue
    row.soreness = checkin.soreness
    row.motivation = checkin.motivation
    row.notes = checkin.notes
    row.hrv_rmssd = checkin.hrv_rmssd
    session.flush()
    return row


def latest_checkin(session: Session, within_days: int = 2) -> DailyCheckin | None:
    """Return the most recent check-in (used as today's readiness signal)."""
    row = session.scalar(
        select(DailyCheckinRow).order_by(DailyCheckinRow.date.desc()).limit(1)
    )
    return _row_to_schema(row) if row else None


def hrv_history(
    session: Session, ref: date | None = None, days: int = 35
) -> list[tuple[date, float]]:
    """Return ``(date, rmssd)`` pairs for the last ``days`` up to ``ref``.

    Feeds :func:`app.processing.recovery.hrv_baseline` (GAP Q1).
    """
    ref = ref or date.today()
    since = (ref - timedelta(days=days - 1)).isoformat()
    rows = session.scalars(
        select(DailyCheckinRow)
        .where(DailyCheckinRow.date >= since, DailyCheckinRow.date <= ref.isoformat())
        .where(DailyCheckinRow.hrv_rmssd.is_not(None))
    ).all()
    out: list[tuple[date, float]] = []
    for row in rows:
        try:
            d = date.fromisoformat(row.date)
        except ValueError:
            continue
        out.append((d, row.hrv_rmssd))
    return out
