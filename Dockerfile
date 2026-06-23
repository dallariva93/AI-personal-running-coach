# syntax=docker/dockerfile:1
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_ENV=production \
    DATABASE_URL=sqlite:///data/running_coach.db \
    DB_PATH=/app/data/running_coach.db

WORKDIR /app

# Minimal OS deps: curl for the healthcheck.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
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
RUN chmod +x ./docker-entrypoint.sh

# Run as a non-root user; give it ownership of the writable data dir.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app
USER appuser

# Persist the SQLite database and reports in a mounted volume.
VOLUME ["/app/data"]

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://localhost:${PORT:-8000}/api/health || exit 1

ENTRYPOINT ["./docker-entrypoint.sh"]
