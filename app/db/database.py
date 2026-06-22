"""SQLite persistence layer built on SQLAlchemy 2.0.

We keep this deliberately tiny: a single engine, a session factory, and a
couple of helpers. SQLite is the only supported backend (free, file-based,
zero-ops) but the SQLAlchemy abstraction keeps the door open for Turso/Postgres
later without touching the rest of the code.
"""

from __future__ import annotations

import os
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


_engine = None
_SessionFactory: sessionmaker[Session] | None = None


def _ensure_sqlite_dir(database_url: str) -> None:
    """Create the parent directory for a file-based SQLite database."""
    prefix = "sqlite:///"
    if database_url.startswith(prefix):
        db_path = database_url[len(prefix):]
        if db_path and db_path != ":memory:":
            Path(db_path).expanduser().parent.mkdir(parents=True, exist_ok=True)


def get_engine():
    """Return the process-wide engine, creating it on first use."""
    global _engine, _SessionFactory
    if _engine is None:
        database_url = os.environ.get("DATABASE_URL") or get_settings().database_url
        _ensure_sqlite_dir(database_url)
        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        _engine = create_engine(database_url, connect_args=connect_args, future=True)
        _SessionFactory = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    if _SessionFactory is None:
        get_engine()
    assert _SessionFactory is not None
    return _SessionFactory


def init_db() -> None:
    """Create all tables. Idempotent — safe to call on every startup."""
    # Import models so they are registered on the metadata before create_all.
    from app.db import models  # noqa: F401

    Base.metadata.create_all(bind=get_engine())


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope: commits on success, rolls back on error."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a session (no auto-commit; caller commits)."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def reset_engine() -> None:
    """Drop the cached engine (used by tests to switch databases)."""
    global _engine, _SessionFactory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionFactory = None
