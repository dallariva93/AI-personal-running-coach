"""Integration tests for the mobile aggregated API."""

from __future__ import annotations


def test_overview_empty(client):
    resp = client.get("/api/mobile/overview")
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "demo"
    assert body["coach"] == "offline"
    assert body["activities"] == []
    assert body["latest_plan"] is None


def test_overview_after_ingest_and_plan(client):
    client.post("/api/ingest")
    client.post("/api/analyze")
    client.post("/api/plan/weekly")

    body = client.get("/api/mobile/overview").json()
    assert len(body["activities"]) == 9
    assert "form_state" in body["metrics"]
    assert isinstance(body["weekly"], list)
    assert body["latest_analysis"]["scope"] == "single"
    assert body["latest_plan"]["scope"] == "weekly"
    assert body["latest_plan"]["next_workout"]
