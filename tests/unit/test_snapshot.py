"""Unit tests for the athlete snapshot (long-horizon memory)."""

from __future__ import annotations

from datetime import date, timedelta

from app.processing import build_snapshot
from app.schemas import RunSummary

REF = date(2026, 6, 24)


def test_empty_snapshot():
    snap = build_snapshot([], ref=REF)
    assert snap.runs_count == 0
    assert snap.best_10k is None


def test_snapshot_aggregates_window():
    runs = [
        RunSummary(date="2026-06-20", distance_km=10, duration_min=45, activity_type="easy"),
        RunSummary(date="2026-05-01", distance_km=21.1, duration_min=100, activity_type="lungo"),
        RunSummary(date="2026-04-10", distance_km=5, duration_min=22, activity_type="gara"),
        RunSummary(date="2024-01-01", distance_km=30, duration_min=180),  # outside 6 months
    ]
    snap = build_snapshot(runs, ref=REF)
    assert snap.runs_count == 3  # the 2024 run is excluded
    assert snap.longest_run_km == 21.1
    assert snap.best_10k == "45:00"
    assert snap.best_half == "1:40:00"
    assert snap.best_5k == "22:00"
    assert snap.avg_weekly_volume_km > 0


def test_snapshot_picks_fastest_effort():
    runs = [
        RunSummary(date=(REF - timedelta(days=5)).isoformat(), distance_km=10,
                   duration_min=50, activity_type="easy"),
        RunSummary(date=(REF - timedelta(days=3)).isoformat(), distance_km=10,
                   duration_min=42, activity_type="tempo"),
    ]
    snap = build_snapshot(runs, ref=REF)
    assert snap.best_10k == "42:00"  # the faster of the two


def test_snapshot_api(client):
    client.post("/api/ingest")
    resp = client.get("/api/snapshot")
    assert resp.status_code == 200
    assert "avg_weekly_volume_km" in resp.json()
