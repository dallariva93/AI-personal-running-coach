"""Integration tests for production-readiness features.

Covers readiness/version endpoints, security headers, gzip, and the optional
bearer-token authentication middleware.
"""

from __future__ import annotations

import pytest


def test_ready_endpoint(client):
    resp = client.get("/api/ready")
    assert resp.status_code == 200
    assert resp.json()["database"] is True


def test_version_endpoint(client):
    resp = client.get("/api/version")
    assert resp.status_code == 200
    assert "version" in resp.json()


def test_health_reports_capabilities(client):
    body = client.get("/api/health").json()
    for key in ("version", "env", "coach", "auth_enabled", "ai_fallback_offline"):
        assert key in body


def test_security_headers_present(client):
    resp = client.get("/api/health")
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert "Referrer-Policy" in resp.headers


def test_request_id_header(client):
    resp = client.get("/api/health")
    assert resp.headers.get("X-Request-ID")


@pytest.fixture
def auth_client(tmp_path, monkeypatch):
    """A client with token auth enabled."""
    from app.config import get_settings
    from app.db.database import init_db, reset_engine

    db_file = tmp_path / "auth.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")
    monkeypatch.setenv("API_TOKEN", "s3cret")
    get_settings.cache_clear()
    reset_engine()
    init_db()

    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c

    reset_engine()
    get_settings.cache_clear()


def test_health_is_public_even_with_auth(auth_client):
    # Platform probes must reach health without a token.
    assert auth_client.get("/api/health").status_code == 200
    assert auth_client.get("/api/ready").status_code == 200


def test_api_requires_token_when_enabled(auth_client):
    assert auth_client.get("/api/activities").status_code == 401


def test_api_accepts_valid_bearer_token(auth_client):
    resp = auth_client.get("/api/activities", headers={"Authorization": "Bearer s3cret"})
    assert resp.status_code == 200


def test_dashboard_shows_login_when_unauthorized(auth_client):
    resp = auth_client.get("/")
    assert resp.status_code == 401
    assert "Token di accesso" in resp.text


def test_dashboard_accepts_query_token_and_sets_cookie(auth_client):
    resp = auth_client.get("/?token=s3cret")
    assert resp.status_code == 200
    assert "coach_token" in resp.cookies
