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

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")
    get_settings.cache_clear()
    reset_engine()
    init_db()
    yield
    reset_engine()
    get_settings.cache_clear()


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
def client(db_env):
    """FastAPI TestClient against the temporary database."""
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c
