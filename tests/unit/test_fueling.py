"""Unit tests for fueling & hydration guidance (Fase F)."""

from __future__ import annotations

from app.processing.fueling import fueling_guidance


def test_short_and_easy_sessions_get_no_fueling():
    assert fueling_guidance("easy", 8.0, 48, None) is None
    assert fueling_guidance("tempo", 10.0, 55, None) is None
    assert fueling_guidance("long", 12.0, 72, None) is None  # under 75 min


def test_long_run_over_threshold_gets_guidance():
    g = fueling_guidance("long", 20.0, 120, None)
    assert g is not None
    assert "30-60 g" in g  # 75-150 min band


def test_very_long_run_needs_more_carbs():
    g = fueling_guidance("long", 32.0, 200, None)
    assert "60-90 g" in g


def test_heat_raises_fluids_and_adds_note():
    base = fueling_guidance("long", 30.0, 180, None)
    hot = fueling_guidance("long", 30.0, 180, 30.0)
    assert "400-800 ml" in base and "caldo" not in base
    assert "600-1000 ml" in hot and "caldo intenso" in hot


def test_warm_band_is_between():
    warm = fueling_guidance("long", 30.0, 180, 24.0)
    assert "500-900 ml" in warm and "clima caldo" in warm


def test_race_adds_dress_rehearsal_reminder():
    g = fueling_guidance("race", 42.195, 240, None)
    assert "mai nulla di nuovo in gara" in g


def test_duration_estimated_from_distance_when_missing():
    # 20 km × 6 min/km = 120 min → fueled.
    assert fueling_guidance("long", 20.0, None, None) is not None
    # 10 km × 6 = 60 min → below threshold.
    assert fueling_guidance("long", 10.0, None, None) is None
