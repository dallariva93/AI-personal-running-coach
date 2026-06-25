"""Per-athlete tuning of the coaching thresholds (priority #4).

A beginner and a seasoned amateur should not be judged by the same numbers. The
athlete's ``level`` and ``risk_tolerance`` scale the key decision boundaries in
one place, so the whole system gets more or less conservative coherently instead
of via scattered magic numbers.

Pure functions: a profile (or None → sensible "intermediate / moderate"
defaults) maps to numeric thresholds.
"""

from __future__ import annotations

from app.schemas import AthleteProfile

LEVELS = ("beginner", "intermediate", "advanced")
RISK_LEVELS = ("conservative", "moderate", "aggressive")


def level_of(profile: AthleteProfile | None) -> str:
    if profile and profile.level in LEVELS:
        return profile.level
    return "intermediate"


def risk_of(profile: AthleteProfile | None) -> str:
    if profile and profile.risk_tolerance in RISK_LEVELS:
        return profile.risk_tolerance
    return "moderate"


def easy_hr_reserve_ceiling(profile: AthleteProfile | None) -> float:
    """Top of the easy/Z2 band as a fraction of HR reserve."""
    return {"beginner": 0.80, "intermediate": 0.82, "advanced": 0.84}[level_of(profile)]


def hard_hr_reserve_floor(profile: AthleteProfile | None) -> float:
    """Floor of the hard/Z4 band as a fraction of HR reserve."""
    return {"beginner": 0.86, "intermediate": 0.88, "advanced": 0.90}[level_of(profile)]


def tsb_fatigue_threshold(profile: AthleteProfile | None) -> float:
    """TSB below which form is 'fatigued'. More risk-tolerant → deeper tolerated."""
    return {"conservative": -20.0, "moderate": -25.0, "aggressive": -32.0}[risk_of(profile)]


def tsb_overreach_threshold(profile: AthleteProfile | None) -> float:
    """TSB below which it's clear overreaching (strong wording / forced deload)."""
    return tsb_fatigue_threshold(profile) - 10.0


def injury_cutoffs(profile: AthleteProfile | None) -> tuple[float, float]:
    """``(moderate_at, high_at)`` score cutoffs for the injury level."""
    return {
        "conservative": (25.0, 50.0),
        "moderate": (30.0, 60.0),
        "aggressive": (40.0, 72.0),
    }[risk_of(profile)]


def profile_tone(profile: AthleteProfile | None) -> str:
    """A short directive for the LLM tone, based on level + risk tolerance."""
    lvl = {
        "beginner": "atleta principiante: progressione prudente, spiega il perché",
        "intermediate": "atleta intermedio",
        "advanced": "atleta avanzato: può sostenere carichi e stimoli impegnativi",
    }[level_of(profile)]
    risk = {
        "conservative": "tolleranza al rischio bassa: privilegia la cautela",
        "moderate": "tolleranza al rischio media",
        "aggressive": "tolleranza al rischio alta: spingi sugli stimoli, "
        "allarmati solo su segnali davvero rossi",
    }[risk_of(profile)]
    return f"{lvl}; {risk}."
