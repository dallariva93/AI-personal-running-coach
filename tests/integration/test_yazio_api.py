"""Integration: the Yazio REST endpoints.

They exist because `fly ssh console` goes through Fly's control plane, which can
be unreachable (corporate network, Fly API outage) while the app itself is
perfectly healthy. This route uses only the app's own public URL.

That convenience is exactly why the first test here is about authentication: an
endpoint that connects accounts and pulls personal data must never be reachable
without the bearer token, and the MCP mount's public path must not extend to it.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.services.yazio_sync import upsert_day


@pytest.fixture
def authed(db_env, monkeypatch):
    """A client with API_TOKEN enforced, plus the token to use."""
    from app.config import get_settings
    from app.main import app

    monkeypatch.setenv("API_TOKEN", "test-api-token")
    get_settings.cache_clear()
    with TestClient(app) as client:
        yield client, {"Authorization": "Bearer test-api-token"}
    get_settings.cache_clear()


# ── auth ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/yazio/status"),
        ("post", "/api/yazio/connect"),
        ("post", "/api/yazio/sync"),
        ("post", "/api/yazio/disconnect"),
    ],
)
def test_yazioEndpoints_requireTheToken(authed, method, path):
    """Without the bearer token none of these may do anything."""
    client, _ = authed

    assert getattr(client, method)(path).status_code == 401


def test_yazioConnect_withoutCredentials_refusesClearly(authed, monkeypatch):
    """A misconfigured deploy must say so, not fail deep inside the client."""
    from app.config import get_settings

    client, headers = authed
    monkeypatch.setenv("YAZIO_USERNAME", "")
    monkeypatch.setenv("YAZIO_PASSWORD", "")
    get_settings.cache_clear()

    resp = client.post("/api/yazio/connect", headers=headers)

    assert resp.status_code == 400
    assert "YAZIO_USERNAME" in resp.json()["detail"]


def test_yazioConnect_whenYazioRefuses_returns502(authed, monkeypatch):
    """A rejection from Yazio is an upstream failure, not a bad request to us."""
    from app.config import get_settings
    from app.exceptions import CollectionError
    from app.services import yazio_sync

    client, headers = authed
    monkeypatch.setenv("YAZIO_USERNAME", "me@example.com")
    monkeypatch.setenv("YAZIO_PASSWORD", "pw")
    get_settings.cache_clear()

    def _refuse(*args, **kwargs):
        raise CollectionError("Login Yazio fallito: HTTP 401: invalid_grant")

    monkeypatch.setattr(yazio_sync, "connect_account", _refuse)

    resp = client.post("/api/yazio/connect", headers=headers)

    assert resp.status_code == 502
    assert "invalid_grant" in resp.json()["detail"]


# ── status / sync ────────────────────────────────────────────────────────────


def test_yazioStatus_whenNotConnected_reportsIt(authed):
    client, headers = authed

    body = client.get("/api/yazio/status", headers=headers).json()

    assert body["connected"] is False
    assert body["days_stored"] == 0


def test_yazioStatus_reportsStoredDays(authed, session):
    client, headers = authed
    upsert_day(session, {"date": "2026-06-21", "energy_kcal": 2100})
    upsert_day(session, {"date": "2026-06-22", "energy_kcal": 2400})
    session.commit()

    body = client.get("/api/yazio/status", headers=headers).json()

    assert body["days_stored"] == 2
    assert body["latest_day"] == "2026-06-22"


def test_yazioSync_withoutAccount_is409(authed):
    """Nothing to sync is a conflict with the current state, not an error."""
    client, headers = authed

    resp = client.post("/api/yazio/sync", headers=headers)

    assert resp.status_code == 409


def test_yazioDisconnect_withoutAccount_isHonest(authed):
    client, headers = authed

    assert client.post("/api/yazio/disconnect", headers=headers).json() == {
        "disconnected": False
    }
