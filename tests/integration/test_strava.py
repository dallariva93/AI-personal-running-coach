"""Integration tests for Strava token lifecycle, event queue and webhooks."""

from __future__ import annotations

import time

from sqlalchemy import select

from app.db.models import Activity, StravaAccount, StravaWebhookEvent
from app.services import strava_sync


class FakeStravaClient:
    """In-memory stand-in for :class:`app.collection.strava.StravaClient`."""

    def __init__(self, activity=None, refreshed=None):
        self.activity = activity or {}
        self.refreshed = refreshed
        self.refresh_calls = 0

    def get_activity(self, access_token, activity_id):
        return self.activity

    def refresh_token(self, refresh_token):
        self.refresh_calls += 1
        return self.refreshed


def _make_account(session, expires_in=9999):
    account = StravaAccount(
        athlete_id=42,
        access_token="tok",
        refresh_token="ref",
        expires_at=int(time.time()) + expires_in,
    )
    session.add(account)
    session.flush()
    return account


def test_save_tokens_from_exchange_response(session):
    account = strava_sync.save_tokens(
        session,
        {
            "access_token": "a1",
            "refresh_token": "r1",
            "expires_at": 1234567890,
            "athlete": {"id": 7, "firstname": "Gianni", "lastname": "X"},
        },
        scope="read,activity:read_all",
    )
    assert account.athlete_id == 7
    assert account.athlete_name == "Gianni X"
    assert account.scope == "read,activity:read_all"


def test_valid_access_token_refreshes_when_expired(session):
    account = _make_account(session, expires_in=-100)  # already expired
    fake = FakeStravaClient(
        refreshed={
            "access_token": "new",
            "refresh_token": "newref",
            "expires_at": int(time.time()) + 9999,
        }
    )
    token = strava_sync.valid_access_token(session, account, fake)
    assert fake.refresh_calls == 1
    assert token == "new"


def test_valid_access_token_skips_refresh_when_fresh(session):
    account = _make_account(session, expires_in=9999)
    fake = FakeStravaClient()
    token = strava_sync.valid_access_token(session, account, fake)
    assert fake.refresh_calls == 0
    assert token == "tok"


def test_process_create_event_upserts_running_activity(session):
    _make_account(session)
    event = strava_sync.enqueue_event(
        session,
        {"object_type": "activity", "object_id": 555, "aspect_type": "create", "owner_id": 42},
    )
    fake = FakeStravaClient(
        activity={"id": 555, "type": "Run", "distance": 5000.0, "moving_time": 1500}
    )
    status = strava_sync.process_event(session, event, fake)
    assert status == "done"
    act = session.scalar(select(Activity).where(Activity.strava_activity_id == "555"))
    assert act is not None
    assert act.distance_km == 5.0


def test_process_event_skips_non_running(session):
    _make_account(session)
    event = strava_sync.enqueue_event(
        session,
        {"object_type": "activity", "object_id": 8, "aspect_type": "create", "owner_id": 42},
    )
    fake = FakeStravaClient(activity={"id": 8, "type": "Ride", "distance": 20000.0})
    assert strava_sync.process_event(session, event, fake) == "skipped"
    assert session.scalar(select(Activity).where(Activity.strava_activity_id == "8")) is None


def test_process_delete_event_removes_activity(session):
    _make_account(session)
    session.add(Activity(strava_activity_id="99", date="2026-06-22", activity_type="easy"))
    session.flush()
    event = strava_sync.enqueue_event(
        session,
        {"object_type": "activity", "object_id": 99, "aspect_type": "delete", "owner_id": 42},
    )
    # delete events need no client (no API fetch).
    assert strava_sync.process_event(session, event, None) == "done"
    assert session.scalar(select(Activity).where(Activity.strava_activity_id == "99")) is None


def test_count_pending(session):
    strava_sync.enqueue_event(
        session,
        {"object_type": "activity", "object_id": 1, "aspect_type": "create", "owner_id": 42},
    )
    assert strava_sync.count_pending(session) == 1


def test_webhook_verify_handshake(client):
    resp = client.get(
        "/api/strava/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.challenge": "abc123",
            "hub.verify_token": "running-coach",
        },
    )
    assert resp.status_code == 200
    assert resp.json() == {"hub.challenge": "abc123"}


def test_webhook_verify_rejects_bad_token(client):
    resp = client.get(
        "/api/strava/webhook",
        params={"hub.mode": "subscribe", "hub.challenge": "x", "hub.verify_token": "wrong"},
    )
    assert resp.status_code == 403


def test_webhook_post_enqueues_event(client):
    payload = {
        "object_type": "activity",
        "object_id": 314,
        "aspect_type": "create",
        "owner_id": 42,
        "event_time": 1700000000,
    }
    resp = client.post("/api/strava/webhook", json=payload)
    assert resp.status_code == 200
    assert resp.json()["status"] == "queued"
    # The event was persisted to the durable inbox.
    from app.db.database import get_session_factory

    s = get_session_factory()()
    try:
        row = s.scalar(select(StravaWebhookEvent).where(StravaWebhookEvent.object_id == 314))
        assert row is not None
        assert row.aspect_type == "create"
    finally:
        s.close()


def test_status_reports_disabled_without_credentials(client):
    resp = client.get("/api/strava/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is False
    assert body["connected"] is False


def test_connect_returns_503_when_disabled(client):
    resp = client.get("/api/strava/connect", follow_redirects=False)
    assert resp.status_code == 503


def test_process_returns_503_when_disabled(client):
    assert client.post("/api/strava/process").status_code == 503


def test_backfill_returns_503_when_disabled(client):
    assert client.post("/api/strava/backfill").status_code == 503


def test_webhook_post_ignores_malformed_payload(client):
    # Non-dict / missing object_type → acknowledged (200) but not enqueued.
    resp = client.post("/api/strava/webhook", json={"foo": "bar"})
    assert resp.status_code == 200
    assert resp.json()["detail"] == "ignored"
