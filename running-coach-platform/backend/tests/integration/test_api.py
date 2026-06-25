"""Integration tests for the FastAPI REST API and dashboard."""

from __future__ import annotations


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["mode"] == "demo"  # no Garmin creds in tests


def test_ingest_then_list_activities(client):
    resp = client.post("/api/ingest")
    assert resp.status_code == 200
    assert len(resp.json()) == 9  # cycling filtered out

    resp = client.get("/api/activities")
    assert resp.status_code == 200
    assert len(resp.json()) == 9


def test_metrics_endpoint(client):
    client.post("/api/ingest")
    resp = client.get("/api/metrics")
    assert resp.status_code == 200
    assert "form_state" in resp.json()


def test_weekly_metrics_endpoint(client):
    client.post("/api/ingest")
    resp = client.get("/api/metrics/weekly")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_analyze_endpoint(client):
    client.post("/api/ingest")
    resp = client.post("/api/analyze")
    assert resp.status_code == 200
    body = resp.json()
    assert body["scope"] == "single"
    assert body["analysis"]


def test_weekly_plan_endpoint(client):
    client.post("/api/ingest")
    resp = client.post("/api/plan/weekly")
    assert resp.status_code == 200
    assert resp.json()["scope"] == "weekly"


def test_analyze_without_data_returns_400(client, monkeypatch):
    # Analysis pre-syncs; point the source at an empty one so the DB stays empty
    # and the genuine "no data" guard (400) is exercised.
    from app.services import ingest as ingest_mod

    monkeypatch.setattr(ingest_mod, "get_source", lambda settings=None: type(
        "_Empty", (), {"get_recent_runs": lambda self, limit=0: []}
    )())
    resp = client.post("/api/analyze")
    assert resp.status_code == 400


def test_manual_activity_creation(client):
    payload = {
        "date": "2026-06-22",
        "activity_type": "easy",
        "duration_min": 40,
        "distance_km": 7.5,
        "avg_hr": 140,
        "rpe": 4,
    }
    resp = client.post("/api/activities", json=payload)
    assert resp.status_code == 201
    assert resp.json()["distance_km"] == 7.5


def test_dashboard_renders(client):
    client.post("/api/ingest")
    resp = client.get("/")
    assert resp.status_code == 200
    assert "AI Running Coach" in resp.text
    assert "Stato di forma" in resp.text


def test_reports_listing(client):
    client.post("/api/ingest")
    client.post("/api/analyze")
    resp = client.get("/api/reports")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1
