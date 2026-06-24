"""Unit tests for aerobic efficiency and decoupling."""

from __future__ import annotations

from datetime import date, timedelta

from app.processing import aerobic_efficiency, decoupling
from app.processing.efficiency import pace_to_seconds
from app.schemas import RunSummary

REF = date(2026, 6, 24)


def _easy(d: str, pace: str, hr: int) -> RunSummary:
    return RunSummary(date=d, distance_km=10, activity_type="easy",
                      duration_min=60, avg_pace=pace, avg_hr=hr)


def test_pace_to_seconds():
    assert pace_to_seconds("5:00/km") == 300
    assert pace_to_seconds("4:30") == 270
    assert pace_to_seconds("1:30:00") == 5400
    assert pace_to_seconds(None) is None
    assert pace_to_seconds("abc") is None


def test_efficiency_unknown_without_samples():
    idx, trend = aerobic_efficiency([], ref=REF)
    assert idx is None and trend == "unknown"


def test_efficiency_improving_when_faster_at_same_hr():
    # Older runs slower at HR 150; recent runs faster at the same HR.
    runs = []
    for i in range(4):  # older half, ~6 weeks ago
        runs.append(_easy((REF - timedelta(days=40 - i)).isoformat(), "5:30/km", 150))
    for i in range(4):  # recent half
        runs.append(_easy((REF - timedelta(days=10 - i)).isoformat(), "5:00/km", 150))
    idx, trend = aerobic_efficiency(runs, ref=REF)
    assert trend == "improving"
    assert idx is not None


def test_efficiency_stable():
    runs = [
        _easy((REF - timedelta(days=d)).isoformat(), "5:00/km", 150)
        for d in (40, 35, 8, 3)
    ]
    _, trend = aerobic_efficiency(runs, ref=REF)
    assert trend == "stable"


def test_decoupling_none_without_splits():
    assert decoupling(_easy("2026-06-20", "5:00/km", 150)) is None


def test_decoupling_detects_drift():
    # Second half slower at higher HR -> positive decoupling.
    splits = ["5:00|150", "5:00|150", "5:20|160", "5:25|162"]
    run = RunSummary(date="2026-06-20", distance_km=4, duration_min=21, splits_km=splits)
    drift = decoupling(run)
    assert drift is not None and drift > 0
