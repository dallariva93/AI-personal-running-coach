"""Coach event log + notification queue (Roadmap #5 and #6).

Records what the coach changed, when, why and from which signals, keeping the
before/after state. A ``notifiable`` event that hasn't been ``notified`` is a
pending notification — so the audit log doubles as the notification source, and
notifications stay tied to real decisions/adaptations (never generic).

v2 (P3-2): time-window aware delivery, priority levels (high/medium/low), and
cooldown to avoid re-notifying the same event type within a short period.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CoachEvent
from app.logging_config import get_logger
from app.schemas import CoachEventOut, NotificationOut, TrainingMetrics

logger = get_logger(__name__)

# Cooldown (hours): don't show a new notification of the same event_type if one
# was already notified within this window (P3-2).
_COOLDOWN_HOURS = 6

# Time windows (24h, local) when each priority is relevant (P3-2).
# High-priority (safety) notifications are always shown.
# Medium-priority notifications are shown 6:00-22:00.
# Low-priority notifications are shown 8:00-21:00.
_WINDOW = {
    "high": (0, 24),
    "medium": (6, 22),
    "low": (8, 21),
}


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


def _maybe_push(db: Session, event: CoachEvent) -> None:
    """Fire-and-forget FCM push for a freshly logged notifiable event.

    Respects the priority time-window (same as ``pending_notifications``) so
    low-priority events don't buzz the athlete at 3 AM. Never raises: push
    failure is logged and swallowed so the DB transaction is unaffected.
    """
    if not event.notifiable:
        return
    priority = event.priority or "medium"
    if not _in_time_window(priority):
        return
    try:
        from app.services.push import send_to_all

        # Forward a deep-link payload (A4) so tapping the notification can open
        # the right surface (e.g. the voice-debrief sheet).
        after = event.after or {}
        data: dict = {}
        if after.get("deep_link"):
            data["deep_link"] = after["deep_link"]
        if after.get("activity_id") is not None:
            data["activity_id"] = after["activity_id"]
        data["event_id"] = event.id
        send_to_all(db, event.title, event.detail or event.title, priority, data or None)
    except Exception:
        logger.exception("Push delivery failed for event %s (non-fatal)", event.id)


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
    priority: str | None = None,
) -> CoachEvent | None:
    """Append an event. If ``dedupe_key`` already exists, do nothing (idempotent).

    ``priority`` (high/medium/low) is stored when ``notifiable`` is True.
    """
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
        priority=priority if notifiable else None,
    )
    db.add(event)
    db.flush()
    _maybe_push(db, event)
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


def _in_time_window(priority: str | None, now: datetime | None = None) -> bool:
    """True if the current hour falls within the delivery window for ``priority``."""
    if priority is None:
        priority = "medium"
    now = now or datetime.now()
    start, end = _WINDOW.get(priority, _WINDOW["medium"])
    return start <= now.hour < end


def _recently_notified(
    db: Session, event_type: str, hours: int = _COOLDOWN_HOURS
) -> bool:
    """True if a similar event_type was notified within the cooldown window."""
    cutoff = datetime.now() - timedelta(hours=hours)
    row = db.scalar(
        select(CoachEvent)
        .where(CoachEvent.event_type == event_type)
        .where(CoachEvent.notified.is_(True))
        .where(CoachEvent.created_at >= cutoff)
        .limit(1)
    )
    return row is not None


def pending_notifications(
    db: Session, limit: int = 20, now: datetime | None = None
) -> list[NotificationOut]:
    """Notifiable events not yet delivered, filtered by time-window and cooldown.

    Priority order: high first, then medium, then low. Within each priority,
    oldest first. Events outside their time-window or within cooldown of a
    recently notified same-type event are suppressed (P3-2).
    """
    now = now or datetime.now()
    rows = db.scalars(
        select(CoachEvent)
        .where(CoachEvent.notifiable.is_(True), CoachEvent.notified.is_(False))
        .order_by(CoachEvent.created_at.asc())
        .limit(limit * 3)
    ).all()

    result: list[NotificationOut] = []
    _priority_order = {"high": 0, "medium": 1, "low": 2}

    for r in rows:
        priority = r.priority or "medium"
        if not _in_time_window(priority, now):
            continue
        if _recently_notified(db, r.event_type):
            continue
        result.append(
            NotificationOut(
                id=r.id,
                title=r.title,
                body=r.detail or r.title,
                date=r.date,
                event_type=r.event_type,
                priority=priority,
            )
        )
        if len(result) >= limit:
            break

    result.sort(key=lambda n: (_priority_order.get(n.priority, 1), n.date))
    return result


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
