"""Shared pytest fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def raw_activities() -> list[dict]:
    """Raw Garmin-style activity payloads loaded from a fixture file."""
    return json.loads((FIXTURES / "garmin_activities.json").read_text(encoding="utf-8"))


@pytest.fixture
def db_env(tmp_path, monkeypatch):
    """Point the app at a fresh temporary SQLite database for each test."""
    from app.config import get_settings
    from app.db.database import init_db, reset_engine
    from app.services.auth_service import reset_cache as reset_auth_cache
    from app.services.cache import invalidate_all
    from app.storage import get_object_store

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")
    # Force demo mode by clearing Garmin credentials
    monkeypatch.setenv("GARMIN_EMAIL", "")
    monkeypatch.setenv("GARMIN_PASSWORD", "")
    # A10: fixed Fernet key so token encryption is deterministic and no key
    # file gets written into the repo's data/ dir; rate limiting off so the
    # suite's rapid-fire requests don't trip 429 (a dedicated test re-enables it).
    monkeypatch.setenv(
        "DATA_ENCRYPTION_KEY", "5Fz1E0GDeLDMbpZytc3-BgcTvV6C05DsZ2ollT4YnZY="
    )
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    get_settings.cache_clear()
    reset_engine()
    # The Q5 in-process cache is a module global: drop it so a fresh test DB
    # can't be served a payload cached against the previous one. Same for the
    # A10 rotated-token hash cache.
    invalidate_all()
    reset_auth_cache()
    # The object-store client is @lru_cache'd on settings: drop it so a test that
    # expects "no S3 configured" isn't served a real store cached by an earlier
    # test (fragile only when a local .env carries real S3 credentials).
    get_object_store.cache_clear()
    init_db()
    yield
    reset_engine()
    get_settings.cache_clear()
    get_object_store.cache_clear()


@pytest.fixture
def session(db_env):
    """A SQLAlchemy session bound to the temporary test database."""
    from app.db.database import get_session_factory

    s = get_session_factory()()
    try:
        yield s
        s.commit()
    finally:
        s.close()


@pytest.fixture
def demo_source():
    """A DemoSource backed by the test fixtures file."""
    from app.collection.sources import DemoSource

    return DemoSource(FIXTURES / "garmin_activities.json")


@pytest.fixture
def empty_source():
    """An activity source that returns no runs.

    Needed since analysis now triggers a pre-sync (``sync_before_analysis``):
    to exercise the genuine "no data" guard the source must yield nothing.
    """

    class _EmptySource:
        def get_recent_runs(self, limit: int = 0) -> list:
            return []

    return _EmptySource()


@pytest.fixture
def client(db_env):
    """FastAPI TestClient against the temporary database."""
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c
