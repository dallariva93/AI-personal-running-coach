"""Unit tests for internal/external load and the Fitness/Fatigue model."""

from __future__ import annotations

from datetime import date

from app.processing import (
    compute_metrics,
    equivalent_flat_km,
    estimate_rpe,
    fitness_fatigue,
    intensity_class,
    internal_load,
    is_truly_easy,
)
from app.schemas import AthleteProfile, HRZones, RunSummary

REF = date(2026, 6, 22)


def _run(d: str, km: float, t: str = "easy", **kw) -> RunSummary:
    return RunSummary(date=d, distance_km=km, activity_type=t, duration_min=km * 6, **kw)


def test_intensity_class_three_states_from_hr_reserve():
    p = AthleteProfile(max_hr=185, resting_hr=50)  # ceiling 0.82≈161, floor 0.88≈169
    assert intensity_class(_run("2026-06-20", 10, avg_hr=150), p) == "easy"
    assert intensity_class(_run("2026-06-20", 10, avg_hr=163), p) == "moderate"
    assert intensity_class(_run("2026-06-20", 10, avg_hr=172), p) == "hard"


def test_intensity_class_raised_easy_ceiling():
    # 158 bpm (~80% HRR) was "not easy" under the old 0.75 cutoff; now easy.
    p = AthleteProfile(max_hr=185, resting_hr=50)
    run = _run("2026-06-20", 10, "easy", avg_hr=158)
    assert intensity_class(run, p) == "easy"
    assert is_truly_easy(run, p) is True


def test_intensity_class_medio_is_moderate_not_hard():
    assert intensity_class(_run("2026-06-20", 8, "medio")) == "moderate"
    assert intensity_class(_run("2026-06-20", 8, "lungo")) == "easy"
    assert intensity_class(_run("2026-06-20", 8, "tempo")) == "hard"


def test_metrics_expose_intensity_distribution():
    runs = [
        _run("2026-06-20", 8, "easy", avg_hr=140),
        _run("2026-06-19", 6, "medio", avg_hr=163),
        _run("2026-06-18", 4, "tempo", avg_hr=175),
    ]
    p = AthleteProfile(max_hr=185, resting_hr=50)
    m = compute_metrics(runs, ref=REF, profile=p)
    assert m.easy_ratio is not None and m.moderate_ratio is not None and m.hard_ratio is not None
    # Ratios cover the whole window (each rounded to 2 decimals).
    assert abs((m.easy_ratio + m.moderate_ratio + m.hard_ratio) - 1.0) < 0.02
    assert m.moderate_ratio > 0 and m.hard_ratio > 0  # medio + tempo present


def test_estimate_rpe_prefers_explicit_value():
    run = _run("2026-06-20", 10, "easy", rpe=7)
    assert estimate_rpe(run) == 7.0


def test_estimate_rpe_from_hr_reserve():
    profile = AthleteProfile(max_hr=190, resting_hr=50)
    hard = _run("2026-06-20", 10, "easy", avg_hr=170)  # ~86% reserve
    easy = _run("2026-06-20", 10, "easy", avg_hr=120)  # ~50% reserve
    assert estimate_rpe(hard, profile) > estimate_rpe(easy, profile)


def test_estimate_rpe_falls_back_to_label():
    assert estimate_rpe(_run("2026-06-20", 10, "intervalli")) > estimate_rpe(
        _run("2026-06-20", 10, "recupero")
    )


def test_internal_load_is_rpe_times_minutes():
    run = _run("2026-06-20", 10, "easy", rpe=5)  # duration 60 min
    assert internal_load(run) == 300.0


def test_internal_load_zero_duration():
    assert internal_load(RunSummary(date="2026-06-20", distance_km=0, duration_min=0)) == 0.0


def test_equivalent_flat_km_adds_climb():
    flat = _run("2026-06-20", 10, "easy")
    hilly = _run("2026-06-20", 10, "easy", elevation_gain_m=300)
    assert equivalent_flat_km(flat) == 10.0
    assert equivalent_flat_km(hilly) == 13.0  # +300m * 0.01


def test_is_truly_easy_uses_zones_over_label():
    profile = AthleteProfile(zones=HRZones(z2_hr=(140, 155), z4_hr=(169, 178)))
    # Labelled "easy" but HR sits in Z4 -> not truly easy.
    mislabelled = _run("2026-06-20", 10, "easy", avg_hr=172)
    assert is_truly_easy(mislabelled, profile) is False


def test_is_truly_easy_falls_back_to_label():
    assert is_truly_easy(_run("2026-06-20", 10, "easy")) is True
    assert is_truly_easy(_run("2026-06-20", 10, "tempo")) is False


def test_hr_zone_lookup():
    zones = HRZones(z1_hr=(120, 140), z2_hr=(141, 155), z4_hr=(169, 178))
    assert zones.zone_of(130) == 1
    assert zones.zone_of(150) == 2
    assert zones.zone_of(175) == 4
    assert zones.zone_of(200) is None
    assert zones.zone_of(None) is None


def test_fitness_fatigue_none_without_data():
    assert fitness_fatigue([], ref=REF) == (None, None, None)


def test_fitness_fatigue_fresh_after_taper():
    # Solid base then a quiet final week -> positive TSB (fresh).
    base = [_run(f"2026-05-{day:02d}", 10, "easy") for day in range(1, 28, 2)]
    m = compute_metrics(base, ref=REF)
    assert m.tsb is not None and m.tsb > 0
    assert m.form_state in {"fresh", "detraining"}
    assert m.ctl is not None and m.atl is not None


def test_fitness_fatigue_fatigued_on_overload():
    runs = [_run(f"2026-06-{day:02d}", 18, "tempo", rpe=8) for day in range(16, 23)]
    m = compute_metrics(runs, ref=REF)
    assert m.tsb is not None and m.tsb < 0
    assert m.form_state == "fatigued"
    assert m.acute_load_internal > 0


def test_internal_load_personalised_by_profile():
    profile = AthleteProfile(max_hr=190, resting_hr=50)
    run = _run("2026-06-20", 10, "easy", avg_hr=175)  # hard despite the label
    assert internal_load(run, profile) > internal_load(_run("2026-06-20", 10, "easy"))
