# syntax=docker/dockerfile:1
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first for better layer caching.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code and bundled demo data.
COPY app ./app
COPY data/demo_activities.json ./data/demo_activities.json
COPY pyproject.toml ./

# Persist the SQLite database and reports in a mounted volume.
VOLUME ["/app/data"]

EXPOSE 8000

# Default: serve the dashboard + API. Override CMD for CLI usage, e.g.:
#   docker run --rm ai-running-coach python -m app.cli analyze
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
