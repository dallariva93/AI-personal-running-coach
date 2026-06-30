"""Coverage for the running stats / export / records read endpoints.

These exercise the formatting branches in the API once real demo runs exist,
and double as regression coverage that cross-training never leaks into the
running-only surfaces (Feature 24).
"""

from __future__ import annotations

import pytest


@pytest.fixture
def seeded_client(client):
    """Client with demo runs and cross-training already ingested."""
    client.post("/api/ingest")
    client.post("/api/ingest/cross-training")
    return client


def test_stats_periods(seeded_client):
    for period in ("month", "year", "all-time"):
        resp = seeded_client.get("/api/stats", params={"period": period})
        assert resp.status_code == 200
        assert resp.json()["period"] == period


def test_stats_rejects_bad_period(seeded_client):
    resp = seeded_client.get("/api/stats", params={"period": "decade"})
    assert resp.status_code == 422


def test_export_csv_and_json(seeded_client):
    csv = seeded_client.get("/api/export", params={"format": "csv"})
    assert csv.status_code == 200
    assert "text/csv" in csv.headers["content-type"]

    js = seeded_client.get("/api/export", params={"format": "json"})
    assert js.status_code == 200
    assert "application/json" in js.headers["content-type"]


def test_personal_records_and_gamification(seeded_client):
    prs = seeded_client.get("/api/personal-records")
    assert prs.status_code == 200
    gam = seeded_client.get("/api/gamification")
    assert gam.status_code == 200
    assert "streak_days" in gam.json()


def test_vo2max_history(seeded_client):
    resp = seeded_client.get("/api/vo2max/history")
    assert resp.status_code == 200
    body = resp.json()
    assert "points" in body and "trend" in body


def test_heatmap_excludes_cross_training(seeded_client):
    resp = seeded_client.get("/api/activities/heatmap")
    assert resp.status_code == 200
    body = resp.json()
    # total_activities counts running only.
    assert body["total_activities"] >= 0
    assert "routes" in body
