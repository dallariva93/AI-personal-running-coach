"""Tests for per-athlete tuning (level / risk_tolerance) and smarter deload."""

from __future__ import annotations

from datetime import date

from app.coaching.coach import OfflineCoach
from app.processing import compute_metrics
from app.processing.metrics import _classify_form
from app.processing.tuning import (
    easy_hr_reserve_ceiling,
    injury_cutoffs,
    tsb_fatigue_threshold,
)
from app.schemas import AthleteProfile, RunSummary, TrainingMetrics

REF = date(2026, 6, 22)


def _run(d, km, t="tempo", **kw):
    return RunSummary(date=d, distance_km=km, activity_type=t, duration_min=km * 6, **kw)


# -- tuning tables ----------------------------------------------------------
def test_tuning_defaults_for_none():
    assert easy_hr_reserve_ceiling(None) == 0.82
    assert tsb_fatigue_threshold(None) == -25.0
    assert injury_cutoffs(None) == (30.0, 60.0)


def test_tuning_scales_with_level_and_risk():
    adv = AthleteProfile(level="advanced", risk_tolerance="aggressive")
    beg = AthleteProfile(level="beginner", risk_tolerance="conservative")
    assert easy_hr_reserve_ceiling(adv) > easy_hr_reserve_ceiling(beg)
    assert tsb_fatigue_threshold(adv) < tsb_fatigue_threshold(beg)  # tolerates deeper
    assert injury_cutoffs(adv)[1] > injury_cutoffs(beg)[1]  # flagged "high" later


# -- form state scales with risk tolerance ---------------------------------
def test_same_tsb_different_form_by_risk():
    # TSB -28: fatigued for a moderate athlete, still productive for aggressive.
    moderate = _classify_form(-28, 30, 1.0, 40, 35, fatigue_threshold=-25, overreach_threshold=-35)
    aggressive = _classify_form(
        -28, 30, 1.0, 40, 35, fatigue_threshold=-32, overreach_threshold=-42
    )
    assert moderate[0] == "fatigued"
    assert aggressive[0] == "balanced"


# -- injury cutoffs scale with risk ----------------------------------------
def test_injury_level_scales_with_risk():
    runs = [_run(f"2026-06-{d:02d}", 18, "tempo", rpe=7) for d in range(16, 23)]
    moderate = compute_metrics(runs, ref=REF, profile=AthleteProfile())
    aggressive = compute_metrics(
        runs, ref=REF, profile=AthleteProfile(risk_tolerance="aggressive")
    )
    # Same underlying score, stricter cutoff → aggressive is flagged lower.
    assert moderate.injury_score == aggressive.injury_score
    assert moderate.injury_level == "high"
    assert aggressive.injury_level == "moderate"


# -- profile persistence ----------------------------------------------------
def test_level_risk_round_trip(session):
    from app.services import get_profile, save_profile

    save_profile(session, AthleteProfile(level="advanced", risk_tolerance="aggressive"))
    session.commit()
    loaded = get_profile(session)
    assert loaded.level == "advanced"
    assert loaded.risk_tolerance == "aggressive"


def test_profile_defaults_when_unset(session):
    from app.services import get_profile, save_profile

    save_profile(session, AthleteProfile(age=30))
    session.commit()
    loaded = get_profile(session)
    assert loaded.level == "intermediate"
    assert loaded.risk_tolerance == "moderate"


# -- deload differentiation (priority #5) -----------------------------------
def test_programmed_deload_keeps_quality():
    m = TrainingMetrics(form_state="fatigued", chronic_load_km=50, acute_load_km=55)
    out = OfflineCoach().plan_week([], m, []).next_workout
    assert "scarico programmato" in out
    assert "qualità ridotta" in out


def test_forced_deload_is_all_easy():
    m = TrainingMetrics(
        form_state="fatigued", readiness_state="red", readiness=30,
        chronic_load_km=50, acute_load_km=55,
    )
    out = OfflineCoach().plan_week([], m, []).next_workout
    assert "scarico forzato" in out
    assert "qualità ridotta" not in out
