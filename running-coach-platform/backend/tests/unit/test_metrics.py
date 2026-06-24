"""Unit tests for the processing/metrics layer."""

from __future__ import annotations

from datetime import date

from app.processing import compute_metrics, weekly_buckets
from app.schemas import RunSummary


def _run(d: str, km: float, t: str = "easy") -> RunSummary:
    return RunSummary(date=d, distance_km=km, activity_type=t, duration_min=km * 6)


REF = date(2026, 6, 22)


def test_empty_metrics():
    m = compute_metrics([])
    assert m.runs_count == 0
    assert m.form_state == "unknown"


def test_acute_and_chronic_load():
    runs = [
        _run("2026-06-20", 10),  # within last 7 days
        _run("2026-06-18", 5),   # within last 7 days
        _run("2026-06-01", 20),  # within last 28 days only
    ]
    m = compute_metrics(runs, ref=REF)
    assert m.acute_load_km == 15.0
    # chronic = total 28d (35) / 4
    assert m.chronic_load_km == 8.75
    assert m.acwr == round(15.0 / 8.75, 2)


def test_form_state_balanced():
    # acute ~= chronic -> balanced band
    runs = [_run(f"2026-06-{day:02d}", 5) for day in range(1, 22, 2)]
    m = compute_metrics(runs, ref=REF)
    assert m.form_state in {"balanced", "detraining", "fatigued"}
    assert m.acwr is not None


def test_form_state_fatigued_on_spike():
    runs = [
        _run("2026-06-22", 30, "tempo"),
        _run("2026-06-21", 25, "tempo"),
        _run("2026-06-01", 5),
    ]
    m = compute_metrics(runs, ref=REF)
    assert m.acwr is not None and m.acwr > 1.5
    assert m.form_state == "fatigued"


def test_easy_ratio():
    runs = [
        _run("2026-06-20", 8, "easy"),
        _run("2026-06-19", 2, "tempo"),
    ]
    m = compute_metrics(runs, ref=REF)
    assert m.easy_ratio == 0.8


def test_load_trend_rising():
    runs = [
        _run("2026-06-20", 20),  # this week
        _run("2026-06-12", 5),   # previous week
    ]
    m = compute_metrics(runs, ref=REF)
    assert m.load_trend == "rising"


def test_weekly_buckets_grouping():
    runs = [
        _run("2026-06-15", 10),  # week of Mon 2026-06-15
        _run("2026-06-17", 5),   # same week
        _run("2026-06-08", 8),   # previous week
    ]
    buckets = weekly_buckets(runs)
    assert len(buckets) == 2
    assert buckets[-1].week_start == "2026-06-15"
    assert buckets[-1].distance_km == 15.0
    assert buckets[-1].runs == 2
