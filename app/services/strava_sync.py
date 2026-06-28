"""Strava orchestration: OAuth token lifecycle + webhook event processing.

This is the glue between the low-level :mod:`app.collection.strava` client and
our database. It owns three responsibilities:

1. **Token lifecycle** — store the athlete's OAuth tokens and refresh the
   short-lived (6 h) access token lazily before each API call.
2. **Webhook inbox** — persist incoming push events durably, then drain them
   out-of-band (the lightweight "job queue" pattern). The webhook handler must
   answer within ~2 s, so the heavy work (fetch + map + upsert) happens here.
3. **Subscription bootstrap** — ensure a Strava push subscription exists.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.collection.strava import StravaClient, synthesize_strava
from app.config import Settings, get_settings
from app.db.models import Activity, StravaAccount, StravaWebhookEvent
from app.exceptions import CollectionError
from app.logging_config import get_logger
from app.services.ingest import upsert_activity

logger = get_logger("app.services.strava_sync")

# A webhook event is retried up to this many times before being parked as error.
_MAX_ATTEMPTS = 3
# Refresh the access token this many seconds before it actually expires.
_REFRESH_SKEW = 120


# ── account / token lifecycle ────────────────────────────────────────────────


def get_account(session: Session) -> StravaAccount | None:
    """Return the connected Strava account (single-athlete app → one row)."""
    return session.scalars(select(StravaAccount).limit(1)).first()


def save_tokens(
    session: Session, token_response: dict[str, Any], scope: str | None = None
) -> StravaAccount:
    """Upsert the Strava account from a token exchange/refresh response.

    The initial ``authorization_code`` exchange includes an ``athlete`` block;
    a ``refresh_token`` exchange does not, so we fall back to the existing row.
    """
    athlete = token_response.get("athlete") or {}
    athlete_id = athlete.get("id")

    account = get_account(session)
    if account is None and athlete_id is None:
        raise CollectionError("Strava token response missing athlete id")

    if account is None:
        account = StravaAccount(athlete_id=int(athlete_id))
        session.add(account)

    if athlete_id is not None:
        account.athlete_id = int(athlete_id)
        name = " ".join(
            p for p in (athlete.get("firstname"), athlete.get("lastname")) if p
        ).strip()
        if name:
            account.athlete_name = name

    account.access_token = token_response["access_token"]
    account.refresh_token = token_response["refresh_token"]
    account.expires_at = int(token_response.get("expires_at") or 0)
    if scope:
        account.scope = scope
    session.flush()
    return account


def valid_access_token(
    session: Session,
    account: StravaAccount,
    client: StravaClient | None = None,
) -> str:
    """Return a non-expired access token, refreshing via Strava if needed."""
    now = int(time.time())
    if account.expires_at - _REFRESH_SKEW > now:
        return account.access_token
    client = client or StravaClient(get_settings())
    logger.info("Refreshing Strava access token for athlete %s", account.athlete_id)
    refreshed = client.refresh_token(account.refresh_token)
    save_tokens(session, refreshed)
    return account.access_token


def connect_account(
    session: Session, code: str, scope: str | None, client: StravaClient | None = None
) -> StravaAccount:
    """Complete the OAuth flow: exchange the code and persist the tokens."""
    client = client or StravaClient(get_settings())
    token_response = client.exchange_code(code)
    return save_tokens(session, token_response, scope=scope)


# ── webhook inbox (the job queue) ────────────────────────────────────────────


def enqueue_event(session: Session, payload: dict[str, Any]) -> StravaWebhookEvent:
    """Persist an incoming webhook event as ``pending`` work."""
    event = StravaWebhookEvent(
        object_type=str(payload.get("object_type", "")),
        object_id=int(payload.get("object_id") or 0),
        aspect_type=str(payload.get("aspect_type", "")),
        owner_id=int(payload.get("owner_id") or 0),
        event_time=int(payload.get("event_time") or 0),
        updates=payload.get("updates") if isinstance(payload.get("updates"), dict) else None,
        status="pending",
    )
    session.add(event)
    session.flush()
    return event


def count_pending(session: Session) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(StravaWebhookEvent)
            .where(StravaWebhookEvent.status == "pending")
        )
        or 0
    )


def _is_run(activity: dict[str, Any]) -> bool:
    sport = str(activity.get("sport_type") or activity.get("type") or "").lower()
    return "run" in sport


def process_event(
    session: Session,
    event: StravaWebhookEvent,
    client: StravaClient | None = None,
) -> str:
    """Process a single webhook event. Returns the resulting status.

    * ``activity``/``create``|``update`` → fetch + map + upsert (running only).
    * ``activity``/``delete`` → remove the stored activity if present.
    * anything else (athlete updates, deauthorizations) → ``skipped``.
    """
    event.attempts += 1
    if event.object_type != "activity":
        return _finish(session, event, "skipped")

    if event.aspect_type == "delete":
        existing = session.scalar(
            select(Activity).where(Activity.strava_activity_id == str(event.object_id))
        )
        if existing is not None:
            session.delete(existing)
        return _finish(session, event, "done")

    account = get_account(session)
    if account is None:
        return _finish(session, event, "error", "no connected Strava account")

    try:
        client = client or StravaClient(get_settings())
        token = valid_access_token(session, account, client)
        activity = client.get_activity(token, event.object_id)
    except CollectionError as exc:
        status = "pending" if event.attempts < _MAX_ATTEMPTS else "error"
        return _finish(session, event, status, str(exc))

    if not _is_run(activity):
        return _finish(session, event, "skipped")

    run = synthesize_strava(activity)
    upsert_activity(session, run)
    return _finish(session, event, "done")


def _finish(
    session: Session, event: StravaWebhookEvent, status: str, error: str | None = None
) -> str:
    event.status = status
    event.error = error
    if status != "pending":
        event.processed_at = datetime.now(UTC)
    session.flush()
    return status


def process_pending(
    session: Session, client: StravaClient | None = None, limit: int = 50
) -> dict[str, int]:
    """Drain pending webhook events. Commits per event for robustness.

    Returns a small summary, e.g. ``{"done": 3, "skipped": 1, "error": 0}``.
    """
    events = list(
        session.scalars(
            select(StravaWebhookEvent)
            .where(StravaWebhookEvent.status == "pending")
            .order_by(StravaWebhookEvent.id)
            .limit(limit)
        ).all()
    )
    client = client or StravaClient(get_settings())
    summary: dict[str, int] = {}
    for event in events:
        try:
            status = process_event(session, event, client)
            session.commit()
        except Exception as exc:  # noqa: BLE001 - one bad event must not abort the rest
            session.rollback()
            logger.exception("Strava event %s processing crashed: %s", event.id, exc)
            event.status = "error"
            event.error = str(exc)
            event.processed_at = datetime.now(UTC)
            session.commit()
            status = "error"
        summary[status] = summary.get(status, 0) + 1
    return summary


# ── subscription bootstrap ───────────────────────────────────────────────────


def ensure_subscription(
    settings: Settings | None = None, client: StravaClient | None = None
) -> dict[str, Any]:
    """Create the Strava push subscription if one does not already exist.

    Idempotent: Strava allows a single subscription per application, so we
    check first and only create when missing.
    """
    settings = settings or get_settings()
    client = client or StravaClient(settings)
    callback_url = settings.strava_webhook_callback_url
    if not callback_url:
        raise CollectionError("STRAVA_PUBLIC_BASE_URL not configured")

    existing = client.view_subscriptions()
    if existing:
        return {"status": "exists", "subscription": existing[0]}

    created = client.create_subscription(
        callback_url, settings.strava_webhook_verify_token
    )
    return {"status": "created", "subscription": created}


def subscription_active(client: StravaClient | None = None) -> bool:
    client = client or StravaClient(get_settings())
    return bool(client.view_subscriptions())
