"""Tests for the trail engine, adaptive planning and Garmin-data synergy."""

from __future__ import annotations

from datetime import date

from app.processing import (
    adapt_plan,
    aerobic_efficiency,
    compute_metrics,
    is_trail,
    trail_metrics,
)
from app.schemas import AthleteProfile, Goal, RunSummary, TrainingMetrics

REF = date(2026, 6, 24)


# -- Trail engine (GAP 20) --------------------------------------------------
def test_is_trail_by_climb_density():
    flat = RunSummary(date="2026-06-20", distance_km=10, duration_min=50, elevation_gain_m=50)
    hilly = RunSummary(date="2026-06-20", distance_km=10, duration_min=70, elevation_gain_m=600)
    assert is_trail(flat) is False
    assert is_trail(hilly) is True


def test_trail_metrics_none_without_climb():
    assert trail_metrics(RunSummary(date="2026-06-20", distance_km=10, duration_min=50)) is None


def test_trail_metrics_values():
    run = RunSummary(
        date="2026-06-20", distance_km=10, duration_min=60,
        elevation_gain_m=600, elevation_loss_m=550,
    )
    tm = trail_metrics(run)
    assert tm is not None
    assert tm.is_trail is True
    assert tm.vertical_speed_m_per_h == 600  # 600 m in 1 h
    assert tm.climb_per_km == 60.0
    assert tm.equivalent_flat_km == 16.0  # 10 + 600*0.01
    assert tm.time_on_feet_min == 60


def test_trail_note_in_offline_analysis():
    from app.coaching.coach import OfflineCoach

    run = RunSummary(
        date="2026-06-24", distance_km=12, duration_min=90,
        activity_type="trail", elevation_gain_m=700,
    )
    m = compute_metrics([run], ref=REF)
    analysis = OfflineCoach().analyze_run(run, [], m).analysis.lower()
    assert "trail" in analysis


# -- Adaptive planning engine (Fase 4) --------------------------------------
def test_adapt_plan_neutral_by_default():
    factor, notes = adapt_plan(TrainingMetrics())
    assert factor == 1.0
    assert notes == []


def test_adapt_plan_cuts_for_high_injury_and_red_readiness():
    m = TrainingMetrics(injury_level="high", readiness_state="red")
    factor, notes = adapt_plan(m)
    assert factor < 1.0
    assert any("infortunio" in n for n in notes)
    assert any("recupero" in n for n in notes)


def test_adapt_plan_flags_behind_target():
    m = TrainingMetrics(race_probability=0.2, weeks_to_race=10)
    _, notes = adapt_plan(m)
    assert any("dietro" in n for n in notes)


def test_adaptive_reduces_phase_target_in_metrics():
    # A heavy, injury-prone block should pull the phase volume target down.
    runs = [
        RunSummary(date=(REF.replace(day=d)).isoformat(), distance_km=16,
                   activity_type="tempo", duration_min=90, rpe=8)
        for d in range(18, 25)
    ]
    goal = Goal(goal_type="marathon", target_date="2026-12-06")
    m = compute_metrics(runs, ref=REF, profile=AthleteProfile(goal=goal))
    assert m.injury_level in {"moderate", "high"}
    assert m.adaptive_notes  # at least one adjustment recorded


# -- Garmin data synergy ----------------------------------------------------
def test_efficiency_prefers_grade_adjusted_pace():
    # GAP pace is much faster than raw pace on a climb; efficiency should use it.
    runs = [
        RunSummary(date=(REF.replace(day=d)).isoformat(), distance_km=10,
                   activity_type="easy", duration_min=60, avg_hr=150,
                   avg_pace="6:00/km", avg_grade_adjusted_pace="5:00/km")
        for d in (3, 8, 18, 23)
    ]
    idx, _ = aerobic_efficiency(runs, ref=REF)
    # 5:00/km = 300s over HR 150 -> 2.0, not 6:00 (360/150 = 2.4).
    assert idx == 2.0


def test_metrics_expose_vo2max():
    runs = [
        RunSummary(date="2026-06-20", distance_km=10, duration_min=50, vo2max=52.0),
        RunSummary(date="2026-06-23", distance_km=8, duration_min=40, vo2max=53.5),
    ]
    m = compute_metrics(runs, ref=REF)
    assert m.vo2max == 53.5  # most recent


def test_trail_api(client):
    client.post("/api/ingest")
    payload = {
        "date": "2026-06-22", "activity_type": "trail",
        "distance_km": 12, "duration_min": 95,
    }
    created = client.post("/api/activities", json=payload).json()
    # Manual activity has no elevation -> 404; just assert the endpoint wiring.
    resp = client.get(f"/api/activities/{created['id']}/trail")
    assert resp.status_code in (200, 404)
