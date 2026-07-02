"""Tiny key-value bookkeeping for background sync (Roadmap Q2).

Lets ``POST /api/ingest`` skip a redundant Garmin fetch when called again
within a few minutes: the periodic WorkManager sync and an app-open expedited
sync can legitimately land close together.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.db.models import SyncState

_LAST_INGEST_KEY = "last_ingest_at"
SKIP_WINDOW = timedelta(minutes=10)


def should_skip_ingest(session: Session, now: datetime | None = None) -> bool:
    """True when the last successful ingest completed less than 10 min ago."""
    now = now or datetime.now(UTC)
    row = session.get(SyncState, _LAST_INGEST_KEY)
    if row is None:
        return False
    try:
        last = datetime.fromisoformat(row.value)
    except ValueError:
        return False
    return now - last < SKIP_WINDOW


def record_ingest(session: Session, now: datetime | None = None) -> None:
    """Stamp the current time as the last successful ingest."""
    now = now or datetime.now(UTC)
    row = session.get(SyncState, _LAST_INGEST_KEY)
    if row is None:
        session.add(SyncState(key=_LAST_INGEST_KEY, value=now.isoformat()))
    else:
        row.value = now.isoformat()
    session.flush()
