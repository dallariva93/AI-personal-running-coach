"""Strava OAuth + webhook endpoints.

The event-driven path, mirroring how Strava itself ingests from Garmin:

1. ``GET  /api/strava/connect``  → redirect the athlete to Strava's consent page.
2. ``GET  /api/strava/callback`` → exchange the code, store tokens, ensure the
   push subscription exists, then bounce back to the dashboard.
3. ``GET  /api/strava/webhook``  → subscription validation handshake.
4. ``POST /api/strava/webhook``  → receive a push event; persist it and return
   200 immediately, draining the queue in the background.

The webhook endpoints are public (Strava's servers call them with no auth) —
see ``_PUBLIC_PREFIXES`` in :mod:`app.middleware`.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.collection.strava import StravaClient, build_authorize_url
from app.config import get_settings
from app.db.database import get_session, session_scope
from app.exceptions import CollectionError
from app.logging_config import get_logger
from app.schemas import StravaStatus
from app.services import strava_sync

logger = get_logger("app.api.strava")

router = APIRouter(prefix="/api/strava", tags=["strava"])


def _require_enabled() -> None:
    if not get_settings().strava_enabled:
        raise HTTPException(status_code=503, detail="Strava non configurato.")


@router.get("/connect")
def connect() -> RedirectResponse:
    """Redirect the athlete to Strava's OAuth consent screen."""
    _require_enabled()
    settings = get_settings()
    redirect_uri = settings.strava_redirect_uri
    if not redirect_uri:
        raise HTTPException(status_code=503, detail="STRAVA_PUBLIC_BASE_URL non configurato.")
    url = build_authorize_url(settings.strava_client_id, redirect_uri)
    return RedirectResponse(url)


@router.get("/callback")
def callback(
    request: Request, session: Session = Depends(get_session)
) -> RedirectResponse:
    """OAuth redirect target: exchange the code and bootstrap the subscription."""
    _require_enabled()
    params = request.query_params
    if params.get("error"):
        return RedirectResponse("/?flash=strava_denied")
    code = params.get("code")
    if not code:
        raise HTTPException(status_code=400, detail="Codice OAuth mancante.")
    scope = params.get("scope")
    try:
        account = strava_sync.connect_account(session, code, scope)
        session.commit()
    except CollectionError as exc:
        session.rollback()
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    # Best-effort: make sure a push subscription exists so future activities
    # arrive automatically. A failure here doesn't undo the connection.
    try:
        strava_sync.ensure_subscription(get_settings())
    except CollectionError as exc:
        logger.warning("Could not ensure Strava subscription: %s", exc)

    logger.info("Strava connected for athlete %s", account.athlete_id)
    return RedirectResponse("/?flash=strava_connected")


@router.get("/webhook")
def webhook_verify(request: Request) -> JSONResponse:
    """Strava subscription validation handshake (GET with hub.* params)."""
    params = request.query_params
    mode = params.get("hub.mode")
    challenge = params.get("hub.challenge")
    verify_token = params.get("hub.verify_token")
    expected = get_settings().strava_webhook_verify_token
    if mode == "subscribe" and challenge and verify_token == expected:
        return JSONResponse({"hub.challenge": challenge})
    raise HTTPException(status_code=403, detail="Verifica webhook fallita.")


@router.post("/webhook")
async def webhook_event(
    request: Request,
    background: BackgroundTasks,
    session: Session = Depends(get_session),
) -> JSONResponse:
    """Receive a Strava push event. Persist it and ack fast (<2 s).

    Strava retries with backoff if we don't respond quickly, so we only
    validate + enqueue here and process out-of-band.
    """
    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001 - malformed body
        return JSONResponse({"detail": "invalid payload"}, status_code=200)

    if not isinstance(payload, dict) or "object_type" not in payload:
        return JSONResponse({"detail": "ignored"}, status_code=200)

    strava_sync.enqueue_event(session, payload)
    session.commit()
    background.add_task(_drain_queue)
    return JSONResponse({"status": "queued"})


def _drain_queue() -> None:
    """Background worker: drain pending webhook events in a fresh session."""
    try:
        with session_scope() as session:
            summary = strava_sync.process_pending(session)
        if summary:
            logger.info("Strava queue drained: %s", summary)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Strava queue drain failed: %s", exc)


@router.post("/process")
def process(session: Session = Depends(get_session)) -> dict:
    """Manually drain the webhook inbox (cron / debugging)."""
    _require_enabled()
    summary = strava_sync.process_pending(session)
    return {"processed": summary}


@router.post("/backfill")
def backfill(limit: int = 30, session: Session = Depends(get_session)) -> dict:
    """Import the athlete's recent Strava activities (one-off history seed)."""
    _require_enabled()
    account = strava_sync.get_account(session)
    if account is None:
        raise HTTPException(status_code=400, detail="Strava non collegato.")
    from app.collection.strava import (
        strava_sport,
        synthesize_cross_training_strava,
        synthesize_strava,
    )
    from app.services.ingest import upsert_activity

    client = StravaClient(get_settings())
    token = strava_sync.valid_access_token(session, account, client)
    activities = client.list_activities(token, per_page=limit)
    imported = 0
    for activity in activities:
        sport = strava_sport(activity)
        if sport is None:
            continue
        # The list endpoint returns summary activities; that's enough for the
        # core fields. Detailed splits/description fill in on the next webhook.
        if sport == "run":
            upsert_activity(session, synthesize_strava(activity))
        else:
            upsert_activity(session, synthesize_cross_training_strava(activity, sport))
        imported += 1
    session.commit()
    return {"imported": imported, "scanned": len(activities)}


@router.get("/status", response_model=StravaStatus)
def status(session: Session = Depends(get_session)) -> StravaStatus:
    """Connection + webhook status for the settings screen."""
    settings = get_settings()
    if not settings.strava_enabled:
        return StravaStatus(enabled=False)

    account = strava_sync.get_account(session)
    authorize_url = None
    if settings.strava_redirect_uri:
        authorize_url = build_authorize_url(
            settings.strava_client_id, settings.strava_redirect_uri
        )

    sub_active = False
    if account is not None:
        try:
            sub_active = strava_sync.subscription_active()
        except Exception:  # noqa: BLE001 - status must never 500
            sub_active = False

    return StravaStatus(
        enabled=True,
        connected=account is not None,
        athlete_id=account.athlete_id if account else None,
        athlete_name=account.athlete_name if account else None,
        subscription_active=sub_active,
        pending_events=strava_sync.count_pending(session),
        authorize_url=authorize_url,
    )
