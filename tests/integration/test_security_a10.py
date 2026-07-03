"""Security & GDPR (FINAL_ROADMAP §5-bis, Passo 8 / A10).

Acceptance, verbatim from the brief: the Strava token never appears in
plaintext to a direct SQL query; delete-my-data leaves only empty tables;
429 past the threshold; rotate invalidates the old token.
"""

from __future__ import annotations

import time

import pytest
from sqlalchemy import inspect, text

from app.db.database import Base, get_engine, get_session_factory
from app.db.models import StravaAccount
from app.security.crypto import decrypt_secret, encrypt_secret, is_encrypted

# ── Pillar 1: at-rest encryption of Strava tokens ────────────────────────────


def test_encrypt_decrypt_round_trip(db_env):
    ct = encrypt_secret("super-secret-token")
    assert is_encrypted(ct) and "super-secret-token" not in ct
    assert decrypt_secret(ct) == "super-secret-token"
    # Idempotent on already-encrypted input; plaintext passes through decrypt.
    assert encrypt_secret(ct) == ct
    assert decrypt_secret("legacy-plaintext") == "legacy-plaintext"


def test_strava_token_never_plaintext_in_db(session):
    session.add(
        StravaAccount(
            athlete_id=42,
            access_token="tok-in-chiaro",
            refresh_token="ref-in-chiaro",
            expires_at=int(time.time()) + 3600,
        )
    )
    session.commit()

    # Direct SQL, bypassing the ORM: the brief's leaked-DB scenario.
    with get_engine().connect() as conn:
        raw = conn.execute(
            text("SELECT access_token, refresh_token FROM strava_accounts")
        ).fetchone()
    assert raw[0].startswith("enc:") and raw[1].startswith("enc:")
    assert "tok-in-chiaro" not in raw[0]
    assert "ref-in-chiaro" not in raw[1]

    # While the ORM (and thus every caller) still sees plaintext.
    acct = session.query(StravaAccount).one()
    assert acct.access_token == "tok-in-chiaro"
    assert acct.refresh_token == "ref-in-chiaro"


def test_decrypt_with_wrong_key_fails_loudly(db_env, monkeypatch):
    ct = encrypt_secret("secret")
    from cryptography.fernet import Fernet

    monkeypatch.setenv("DATA_ENCRYPTION_KEY", Fernet.generate_key().decode())
    from app.config import get_settings

    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="DATA_ENCRYPTION_KEY"):
        decrypt_secret(ct)


# ── Pillar 2: right to erasure ───────────────────────────────────────────────


def test_delete_my_data_requires_confirmation(client):
    resp = client.request("DELETE", "/api/me/data")
    assert resp.status_code == 400
    assert "confirm=DELETE" in resp.json()["detail"]


def test_delete_my_data_empties_every_table(client):
    # Populate a realistic spread of tables: runs, report, check-in, plan.
    client.post("/api/ingest")
    client.post("/api/checkin", json={"date": "2026-06-24", "fatigue": 3, "sleep_h": 8})
    client.post(
        "/api/plan/generate",
        json={"goal_type": "10k", "goal_date": "2026-12-31", "weeks": 4,
              "days_per_week": 3, "long_run_day": 6},
    )

    resp = client.request("DELETE", "/api/me/data", params={"confirm": "DELETE"})
    assert resp.status_code == 200
    counts = resp.json()["deleted"]
    assert counts["activities"] > 0  # something was actually there

    # Every ORM table is now empty (alembic_version is not ORM-managed).
    db = get_session_factory()()
    try:
        with get_engine().connect() as conn:
            for table in Base.metadata.tables:
                n = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
                assert n == 0, f"table {table} still has {n} rows"
    finally:
        db.close()
    # And the schema itself survives (only rows were deleted).
    assert "activities" in inspect(get_engine()).get_table_names()


# ── Pillar 3: rate limiting ──────────────────────────────────────────────────


def _limited_client(monkeypatch, per_minute: int):
    from fastapi.testclient import TestClient

    from app.config import get_settings
    from app.main import app

    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", str(per_minute))
    get_settings.cache_clear()
    return TestClient(app)


def test_rate_limit_returns_429_past_threshold(db_env, monkeypatch):
    with _limited_client(monkeypatch, per_minute=5) as c:
        codes = [c.get("/api/version").status_code for _ in range(8)]
    assert codes[:5] == [200] * 5
    assert 429 in codes[5:], codes


def test_rate_limit_429_carries_retry_after(db_env, monkeypatch):
    with _limited_client(monkeypatch, per_minute=1) as c:
        c.get("/api/version")
        resp = c.get("/api/version")
    assert resp.status_code == 429
    assert resp.headers.get("Retry-After") == "60"


def test_health_probe_exempt_from_rate_limit(db_env, monkeypatch):
    with _limited_client(monkeypatch, per_minute=1) as c:
        codes = [c.get("/api/health").status_code for _ in range(5)]
    assert codes == [200] * 5  # Fly's probe must never be throttled


# ── Pillar 4: API-token rotation ─────────────────────────────────────────────


def _authed_client(monkeypatch, token: str):
    from fastapi.testclient import TestClient

    from app.config import get_settings
    from app.main import app

    monkeypatch.setenv("API_TOKEN", token)
    get_settings.cache_clear()
    return TestClient(app)


def test_rotate_invalidates_old_token(db_env, monkeypatch):
    with _authed_client(monkeypatch, "old-token") as c:
        headers_old = {"Authorization": "Bearer old-token"}
        assert c.get("/api/version", headers=headers_old).status_code == 200

        resp = c.post("/api/auth/rotate", headers=headers_old)
        assert resp.status_code == 200
        new_token = resp.json()["token"]
        assert new_token and new_token != "old-token"

        # Old token dead, new token live.
        assert c.get("/api/version", headers=headers_old).status_code == 401
        assert (
            c.get(
                "/api/version", headers={"Authorization": f"Bearer {new_token}"}
            ).status_code
            == 200
        )

    # Only the hash is persisted — the token itself is nowhere in the DB.
    with get_engine().connect() as conn:
        stored = conn.execute(
            text("SELECT value FROM sync_state WHERE key = 'api_token_hash'")
        ).scalar()
    assert stored is not None and new_token not in stored
    assert len(stored) == 64  # sha256 hex


def test_rotate_requires_auth_enabled(client):
    # Test env has no API_TOKEN → auth off → nothing to rotate.
    resp = client.post("/api/auth/rotate")
    assert resp.status_code == 400
