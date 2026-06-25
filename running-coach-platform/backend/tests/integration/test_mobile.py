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
    # Brain fields flow through to the app via the metrics dump.
    for key in ("tsb", "ctl", "atl", "injury_level", "moderate_ratio", "load_source"):
        assert key in body["metrics"]
    assert "snapshot" in body and body["snapshot"]["runs_count"] >= 0


def test_overview_includes_prediction_and_plan_with_goal(client):
    client.post("/api/ingest")
    client.put(
        "/api/profile",
        json={
            "level": "advanced",
            "risk_tolerance": "aggressive",
            "goal": {"goal_type": "marathon", "target_date": "2027-04-11",
                     "target_time": "03:30:00"},
        },
    )
    body = client.get("/api/mobile/overview").json()
    assert body["profile"]["level"] == "advanced"
    assert body["prediction"]["goal_type"] == "marathon"
    assert body["plan"]["weeks_to_race"] >= 1
    assert len(body["plan"]["phases"]) >= 1
