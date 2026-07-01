"""Coach event log + notification queue (Roadmap #5 and #6).

Records what the coach changed, when, why and from which signals, keeping the
before/after state. A ``notifiable`` event that hasn't been ``notified`` is a
pending notification — so the audit log doubles as the notification source, and
notifications stay tied to real decisions/adaptations (never generic).
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CoachEvent
from app.schemas import CoachEventOut, NotificationOut, TrainingMetrics


def signal_list(m: TrainingMetrics) -> list[str]:
    """Compact 'why' signals for an audit entry, e.g. ['readiness rosso', 'TSB -28']."""
    out: list[str] = []
    if m.readiness_state and m.readiness_state not in ("unknown", "green"):
        label = {"red": "rosso", "amber": "giallo"}.get(m.readiness_state, m.readiness_state)
        out.append(f"readiness {label}")
    if m.tsb is not None and m.tsb <= -15:
        out.append(f"TSB {m.tsb:+.0f}")
    if m.acwr is not None and m.acwr >= 1.4:
        out.append(f"ACWR {m.acwr:.2f}")
    if m.injury_level in ("moderate", "high"):
        out.append(f"rischio infortuni {m.injury_level}")
    return out


def log_event(
    db: Session,
    *,
    date_str: str,
    event_type: str,
    title: str,
    detail: str = "",
    signals: list[str] | None = None,
    before: dict | None = None,
    after: dict | None = None,
    plan_session_id: int | None = None,
    notifiable: bool = False,
    dedupe_key: str | None = None,
) -> CoachEvent | None:
    """Append an event. If ``dedupe_key`` already exists, do nothing (idempotent)."""
    if dedupe_key is not None:
        existing = db.scalar(select(CoachEvent).where(CoachEvent.dedupe_key == dedupe_key))
        if existing is not None:
            return None
    event = CoachEvent(
        date=date_str,
        event_type=event_type,
        title=title,
        detail=detail,
        signals=signals,
        before=before,
        after=after,
        plan_session_id=plan_session_id,
        notifiable=notifiable,
        notified=False,
        dedupe_key=dedupe_key,
    )
    db.add(event)
    db.flush()
    return event


def recent_events(db: Session, days: int = 30, limit: int = 100) -> list[CoachEventOut]:
    """The coach diary: recent events newest-first."""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    rows = db.scalars(
        select(CoachEvent)
        .where(CoachEvent.date >= cutoff)
        .order_by(CoachEvent.created_at.desc())
        .limit(limit)
    ).all()
    return [_to_out(r) for r in rows]


def pending_notifications(db: Session, limit: int = 20) -> list[NotificationOut]:
    """Notifiable events not yet delivered, oldest first."""
    rows = db.scalars(
        select(CoachEvent)
        .where(CoachEvent.notifiable.is_(True), CoachEvent.notified.is_(False))
        .order_by(CoachEvent.created_at.asc())
        .limit(limit)
    ).all()
    return [
        NotificationOut(
            id=r.id,
            title=r.title,
            body=r.detail or r.title,
            date=r.date,
            event_type=r.event_type,
        )
        for r in rows
    ]


def mark_notified(db: Session, ids: list[int]) -> int:
    """Mark the given events delivered. Returns how many were updated."""
    if not ids:
        return 0
    rows = db.scalars(select(CoachEvent).where(CoachEvent.id.in_(ids))).all()
    for r in rows:
        r.notified = True
    db.flush()
    return len(rows)


def _to_out(r: CoachEvent) -> CoachEventOut:
    return CoachEventOut(
        id=r.id,
        date=r.date,
        event_type=r.event_type,
        title=r.title,
        detail=r.detail or "",
        signals=list(r.signals or []) or None,
        before=r.before,
        after=r.after,
        plan_session_id=r.plan_session_id,
        notifiable=r.notifiable,
        notified=r.notified,
        created_at=r.created_at.isoformat() if r.created_at else None,
    )
