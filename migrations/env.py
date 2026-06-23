"""Alembic environment.

The target metadata is the app's SQLAlchemy ``Base`` and the database URL comes
from application settings (env var ``DATABASE_URL`` or ``.env``), so migrations
run against the same database the app uses.
"""

from __future__ import annotations

import os

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import get_settings
from app.db.database import Base
from app.db import models  # noqa: F401  (register models on Base.metadata)

config = context.config

database_url = os.environ.get("DATABASE_URL") or get_settings().database_url
config.set_main_option("sqlalchemy.url", database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,  # required for SQLite ALTER support
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # batch mode makes ALTER TABLE work on SQLite
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
