"""Tests for recalibrating internal load on real Garmin training-load data."""

from __future__ import annotations

from datetime import date

from app.processing import compute_metrics
from app.processing.load import (
    GARMIN_LOAD_TO_SRPE,
    _srpe_load,
    calibrate_garmin_factor,
    internal_load,
)
from app.schemas import RunSummary

REF = date(2026, 6, 7)


def _run(d, km, dur, hr, rpe, gl, t="easy"):
    return RunSummary(
        date=d, activity_type=t, distance_km=km, duration_min=dur,
        avg_hr=hr, max_hr=190, rpe=rpe, garmin_training_load=gl,
    )


def test_internal_load_prefers_garmin_with_default_factor():
    run = _run("2026-06-04", 9.27, 42, 175, 7, 258.0, "tempo")
    assert internal_load(run) == round(258.0 * GARMIN_LOAD_TO_SRPE, 1)


def test_internal_load_explicit_factor():
    run = _run("2026-06-04", 9.27, 42, 175, 7, 200.0, "tempo")
    assert internal_load(run, None, 1.2) == 240.0


def test_internal_load_falls_back_to_srpe_without_garmin():
    run = RunSummary(date="2026-06-04", activity_type="easy", distance_km=10,
                     duration_min=60, rpe=5)
    assert run.garmin_training_load is None
    assert internal_load(run) == 300.0  # 5 * 60, unchanged sRPE path


def test_heat_not_double_applied_to_garmin_load():
    # Garmin load already reflects heat-elevated HR → no extra heat multiplier.
    run = _run("2026-06-04", 10, 60, 150, 5, 120.0)
    run.temperature_c = 32
    run.humidity_pct = 80
    assert internal_load(run, None, 2.0) == 240.0  # 120 * 2.0, no heat factor


def test_calibrate_none_without_enough_pairs():
    runs = [_run("2026-06-04", 10, 60, 150, 5, 120.0)]
    assert calibrate_garmin_factor(runs) is None


def test_calibrate_ignores_runs_without_rpe_or_hr():
    runs = [
        RunSummary(date=f"2026-06-0{i}", activity_type="easy", distance_km=10,
                   duration_min=60, garmin_training_load=100.0)
        for i in range(1, 5)
    ]  # no rpe, no hr -> not trustworthy pairs
    assert calibrate_garmin_factor(runs) is None


def test_calibrate_sum_ratio_preserves_total_load():
    runs = [
        _run("2026-06-02", 8, 48, 135, 3, 70.0),
        _run("2026-06-04", 9.27, 42, 175, 7, 258.0, "tempo"),
        _run("2026-06-07", 18, 108, 150, 5, 190.0, "lungo"),
    ]
    factor = calibrate_garmin_factor(runs)
    assert factor is not None
    # sum(garmin * factor) ≈ sum(sRPE): total internal load is preserved.
    total_srpe = sum(_srpe_load(r) for r in runs)
    total_calibrated = sum(internal_load(r, None, factor) for r in runs)
    assert abs(total_calibrated - total_srpe) / total_srpe < 0.01


def test_load_source_reported_in_metrics():
    garmin_runs = [
        _run(f"2026-06-0{i}", 10, 60, 150, 5, 120.0) for i in range(1, 6)
    ]
    assert compute_metrics(garmin_runs, ref=REF).load_source == "garmin"

    srpe_runs = [
        RunSummary(date=f"2026-06-0{i}", activity_type="easy", distance_km=10,
                   duration_min=60, rpe=5)
        for i in range(1, 6)
    ]
    assert compute_metrics(srpe_runs, ref=REF).load_source == "srpe"

    mixed = garmin_runs[:3] + srpe_runs[3:]
    assert compute_metrics(mixed, ref=REF).load_source == "mixed"


def test_real_padova_activity_ratio():
    # The real dump: hard 42' run, Garmin load 258, RPE 7 -> sRPE ~294.
    run = _run("2026-06-04", 9.27, 42.05, 175, 7, 258.18, "tempo")
    ratio = _srpe_load(run) / run.garmin_training_load
    assert 1.0 < ratio < 1.3  # hard efforts sit near ~1.15
