"""Persist and retrieve daily wellness check-ins (GAP 9)."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DailyCheckinRow
from app.schemas import DailyCheckin

# Source precedence (A4): a voice debrief beats a manual entry, which beats an
# automatic Garmin/Health-Connect proxy. A NULL/legacy source is treated as
# manual-tier. A lower-precedence save may only FILL gaps a stronger source
# left empty — it must never overwrite what a stronger source already recorded.
_SOURCE_RANK = {
    "garmin_proxy": 0,
    "health_connect": 0,
    "manual": 1,
    "voice": 2,
}

_CHECKIN_FIELDS = ("sleep_h", "fatigue", "soreness", "motivation", "notes", "hrv_rmssd")


def _rank(source: str | None) -> int:
    return _SOURCE_RANK.get(source or "", 1)  # unknown/legacy → manual-tier


def _row_to_schema(row: DailyCheckinRow) -> DailyCheckin:
    return DailyCheckin(
        date=row.date,
        sleep_h=row.sleep_h,
        fatigue=row.fatigue,
        soreness=row.soreness,
        motivation=row.motivation,
        notes=row.notes,
        hrv_rmssd=row.hrv_rmssd,
        source=row.source,
    )


def save_checkin(session: Session, checkin: DailyCheckin) -> DailyCheckinRow:
    """Insert or update the check-in for its date (one per day).

    Honours source precedence (A4): if a lower-precedence source (e.g. the
    Garmin proxy) writes over a day already recorded by a stronger one (e.g. a
    voice debrief), it only fills the fields the stronger source left empty and
    keeps the stronger source label — it never clobbers real answers.
    """
    row = session.scalar(
        select(DailyCheckinRow).where(DailyCheckinRow.date == checkin.date)
    )
    if row is None:
        row = DailyCheckinRow(date=checkin.date)
        session.add(row)
        for field in _CHECKIN_FIELDS:
            setattr(row, field, getattr(checkin, field))
        row.source = checkin.source
        session.flush()
        return row

    if _rank(checkin.source) < _rank(row.source):
        # Weaker source: only fill gaps, keep the stronger label untouched.
        for field in _CHECKIN_FIELDS:
            if getattr(row, field) is None:
                setattr(row, field, getattr(checkin, field))
    else:
        # Equal-or-stronger source: full overwrite and adopt (or keep) the label.
        for field in _CHECKIN_FIELDS:
            setattr(row, field, getattr(checkin, field))
        row.source = checkin.source or row.source
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
