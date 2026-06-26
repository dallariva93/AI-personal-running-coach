# syntax=docker/dockerfile:1
FROM python:3.14-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_ENV=production \
    DATABASE_URL=sqlite:///data/running_coach.db \
    DB_PATH=/app/data/running_coach.db

WORKDIR /app

# Minimal OS deps: curl for the healthcheck, gosu to drop privileges at runtime.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl gosu \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first for better layer caching.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code, migrations and bundled demo data.
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini pyproject.toml ./
COPY data/demo_activities.json ./data/demo_activities.json
COPY docker-entrypoint.sh ./docker-entrypoint.sh
# Strip Windows CRLF (\r\n→\n) in case the file was checked out on Windows
# before being sent to the Docker build context. Without this the shebang
# becomes '#!/usr/bin/env sh\r' and the container fails with exit 127.
RUN sed -i 's/\r$//' ./docker-entrypoint.sh && chmod +x ./docker-entrypoint.sh

# Create a non-root user that owns the app. The entrypoint starts as root only
# long enough to fix ownership of the mounted volume (Fly mounts it root-owned),
# then drops privileges to this user via gosu — so the server never runs as root.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app
ENV APP_USER=appuser

# Persist the SQLite database and reports in a mounted volume.
VOLUME ["/app/data"]

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://localhost:${PORT:-8000}/api/health || exit 1

ENTRYPOINT ["./docker-entrypoint.sh"]
