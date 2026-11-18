"""Unit tests for plan explainability (Fase F)."""

from __future__ import annotations

from app.processing.plan_explain import week_rationale


def test_base_week_states_phase_intent_and_countdown():
    r = week_rationale("Base", 2, 20)
    assert "Base" in r and "aerobic" in r.lower()
    assert "18 settimane" in r


def test_deload_week_explains_the_cutback():
    r = week_rationale("Base", 4, 20, is_deload=True)
    assert "scarico" in r.lower()
    assert "-20%" in r or "20%" in r


def test_taper_week_explains_sharpening():
    r = week_rationale("Taper", 18, 20)
    assert "taper" in r.lower()
    assert "2 settimane" in r


def test_race_week_is_reassuring():
    r = week_rationale("Gara", 20, 20, is_race_week=True)
    assert "gara" in r.lower()


def test_unknown_phase_has_a_safe_fallback():
    r = week_rationale("Sconosciuta", 1, 10)
    assert r  # never empty
