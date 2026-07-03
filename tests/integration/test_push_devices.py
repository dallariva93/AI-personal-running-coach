"""Tests for FCM push delivery and device registration (Roadmap A3)."""

from __future__ import annotations

import json
from datetime import date
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.db.models import Device
from app.services import push as push_module
from app.services.event_service import log_event


def _generate_sa() -> dict:
    """Build a service-account dict with a real RSA key for JWT signing."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    return {
        "private_key": pem,
        "client_email": "firebase-adminsdk@project.iam.gserviceaccount.com",
        "project_id": "test-project",
    }


# ── Device registration endpoints ───────────────────────────────────────────


def test_register_device_creates_row(client):
    r = client.post(
        "/api/devices",
        json={"fcm_token": "token-abc", "platform": "android"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["fcm_token"] == "token-abc"
    assert body["platform"] == "android"
    assert "id" in body


def test_register_device_upserts_on_same_token(client):
    client.post("/api/devices", json={"fcm_token": "token-xyz"})
    r = client.post(
        "/api/devices",
        json={"fcm_token": "token-xyz", "platform": "ios"},
    )
    assert r.status_code == 201
    assert r.json()["platform"] == "ios"
    # Only one row for that token.
    from app.db.database import get_session_factory

    s = get_session_factory()()
    count = s.query(Device).filter_by(fcm_token="token-xyz").count()
    s.close()
    assert count == 1


def test_unregister_device_removes_row(client):
    client.post("/api/devices", json={"fcm_token": "to-delete"})
    r = client.delete("/api/devices/to-delete")
    assert r.status_code == 200
    assert r.json()["deleted"] is True


def test_unregister_unknown_token_returns_false(client):
    r = client.delete("/api/devices/nonexistent")
    assert r.status_code == 200
    assert r.json()["deleted"] is False


# ── Push no-op without FCM credentials ──────────────────────────────────────


def test_send_to_all_noop_without_credentials(session):
    push_module.reset_token_cache()
    result = push_module.send_to_all(session, "Title", "Body")
    assert result == 0


def test_log_event_does_not_push_without_credentials(session):
    """log_event with notifiable=True must not raise even when FCM is off."""
    event = log_event(
        session,
        date_str=date.today().isoformat(),
        event_type="decision",
        title="Test event",
        notifiable=True,
        priority="high",
    )
    assert event.id is not None
    assert event.notifiable is True


# ── Push with mocked FCM credentials ────────────────────────────────────────


def test_send_to_all_no_devices_returns_zero(session, monkeypatch, tmp_path):
    """With credentials configured but no registered devices, returns 0."""
    sa_path = tmp_path / "sa.json"
    sa_path.write_text(json.dumps(_generate_sa()))
    monkeypatch.setenv("FCM_CREDENTIALS_PATH", str(sa_path))
    from app.config import get_settings

    get_settings.cache_clear()
    push_module.reset_token_cache()
    try:
        assert push_module.send_to_all(session, "Title", "Body") == 0
    finally:
        push_module.reset_token_cache()
        get_settings.cache_clear()


def test_send_to_all_sends_to_registered_devices(session, monkeypatch, tmp_path):
    """With credentials + a registered device, send_to_all calls FCM endpoint."""
    sa_path = tmp_path / "sa.json"
    sa_path.write_text(json.dumps(_generate_sa()))
    monkeypatch.setenv("FCM_CREDENTIALS_PATH", str(sa_path))
    from app.config import get_settings

    get_settings.cache_clear()
    push_module.reset_token_cache()

    session.add(Device(fcm_token="device-token-1", platform="android"))
    session.flush()

    call_count = 0

    def fake_post(url, **kwargs):
        nonlocal call_count
        call_count += 1

        class _Resp:
            status_code = 200
            text = "{}"

            def raise_for_status(self):
                pass

            def json(self):
                return {"access_token": "fake-token", "expires_in": 3600}

        return _Resp()

    with patch.object(push_module.httpx, "post", side_effect=fake_post):
        sent = push_module.send_to_all(session, "Title", "Body", priority="high")

    try:
        assert sent == 1
        assert call_count >= 2  # at least 1 token request + 1 send
    finally:
        push_module.reset_token_cache()
        get_settings.cache_clear()


# ── Ack flow unchanged ──────────────────────────────────────────────────────


def test_ack_flow_unchanged(client):
    """The notification ack flow must still work with push integration in place."""
    client.post("/api/ingest")
    client.post(
        "/api/checkin",
        json={"date": date.today().isoformat(), "fatigue": 9, "soreness": 10, "sleep_h": 4},
    )
    client.post("/api/ingest")

    notes = client.get("/api/notifications").json()
    if notes:
        r = client.post("/api/notifications/ack", json={"ids": [notes[0]["id"]]})
        assert r.json()["acked"] >= 1
        remaining = client.get("/api/notifications").json()
        remaining_ids = [n["id"] for n in remaining]
        assert notes[0]["id"] not in remaining_ids
