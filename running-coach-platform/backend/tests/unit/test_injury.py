"""Unit tests for the composite injury-risk model."""

from __future__ import annotations

from datetime import date, timedelta

from app.processing import compute_metrics, injury_risk
from app.schemas import RunSummary

REF = date(2026, 6, 24)


def _run(d: str, km: float, t: str = "easy") -> RunSummary:
    return RunSummary(date=d, distance_km=km, activity_type=t, duration_min=km * 6)


def test_low_risk_for_steady_training():
    runs = []
    for w in range(6):
        monday = REF - timedelta(days=REF.weekday()) - timedelta(weeks=w)
        for off in (0, 2, 4):
            runs.append(_run((monday + timedelta(days=off)).isoformat(), 8))
    m = compute_metrics(runs, ref=REF)
    risk = injury_risk(runs, m, ref=REF)
    assert risk.level == "low"
    assert risk.score < 30


def test_high_risk_on_spike_and_consecutive_days():
    # Huge volume jump + many consecutive days + close hard sessions.
    runs = [_run((REF - timedelta(days=i)).isoformat(), 14, "tempo") for i in range(10)]
    runs.append(_run("2026-06-01", 5))  # a little chronic base
    m = compute_metrics(runs, ref=REF)
    risk = injury_risk(runs, m, ref=REF)
    assert risk.level == "high"
    assert risk.score >= 60
    assert risk.factors  # explains why


def test_volume_jump_is_flagged():
    runs = [
        _run("2026-06-23", 10), _run("2026-06-21", 10), _run("2026-06-19", 10),  # ~30 this wk
        _run("2026-06-16", 4),  # ~4 last wk -> big jump
    ]
    m = compute_metrics(runs, ref=REF)
    risk = injury_risk(runs, m, ref=REF)
    assert any("volume" in f for f in risk.factors)


def test_metrics_expose_injury_fields():
    runs = [_run("2026-06-23", 10), _run("2026-06-22", 10, "tempo")]
    m = compute_metrics(runs, ref=REF)
    assert m.injury_level in {"low", "moderate", "high"}
    assert m.injury_score is not None
