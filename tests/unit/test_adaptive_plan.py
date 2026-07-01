"""Unit tests for adaptive plan v2 logic (P2-2: taper-aware, dynamic horizon)."""

from __future__ import annotations

from app.schemas import TrainingMetrics
from app.services.adaptive_plan import (
    _days_to_race,
    _dynamic_horizon,
    _is_severe,
    _is_taper,
    _should_ease,
)


def _m(**kw) -> TrainingMetrics:
    return TrainingMetrics(**kw)


def test_days_to_race_from_weeks():
    assert _days_to_race(_m(weeks_to_race=4)) == 28
    assert _days_to_race(_m()) is None


def test_is_taper_by_days():
    assert _is_taper(_m(weeks_to_race=1)) is True
    assert _is_taper(_m(weeks_to_race=3)) is False  # 21 days > 14


def test_is_taper_by_phase():
    assert _is_taper(_m(phase="taper")) is True
    assert _is_taper(_m(phase="race")) is True
    assert _is_taper(_m(phase="base")) is False


def test_is_taper_within_14_days():
    assert _is_taper(_m(weeks_to_race=2, phase="peak")) is True  # 14 days <= 14
    assert _is_taper(_m(weeks_to_race=3, phase="peak")) is False  # 21 > 14


def test_dynamic_horizon_by_phase():
    assert _dynamic_horizon(_m(phase="base")) == 10
    assert _dynamic_horizon(_m(phase="build")) == 10
    assert _dynamic_horizon(_m(phase="specific")) == 7
    assert _dynamic_horizon(_m(phase="peak")) == 7
    assert _dynamic_horizon(_m(phase="taper")) == 3
    assert _dynamic_horizon(_m(phase="race")) == 1
    assert _dynamic_horizon(_m()) == 7  # default


def test_should_ease_high_injury():
    assert _should_ease(_m(injury_level="high")) is True


def test_should_ease_red_readiness():
    assert _should_ease(_m(injury_level="low", readiness_state="red")) is True


def test_should_ease_tsb_deep_fatigue():
    assert _should_ease(_m(tsb=-30, injury_level="low", readiness_state="green")) is True


def test_should_ease_acwr_danger():
    assert _should_ease(_m(acwr=1.6, injury_level="low", readiness_state="green")) is True


def test_should_ease_healthy():
    assert _should_ease(
        _m(tsb=5, acwr=1.0, injury_level="low", readiness_state="green")
    ) is False


def test_is_severe_single_red_signal():
    assert _is_severe(_m(injury_level="high", readiness_state="green")) is False


def test_is_severe_two_red_signals():
    assert _is_severe(_m(injury_level="high", readiness_state="red")) is True


def test_is_severe_tsb_and_injury():
    assert _is_severe(_m(injury_level="high", tsb=-35)) is True


def test_is_severe_no_signals():
    assert _is_severe(_m(injury_level="low", readiness_state="green", tsb=5)) is False
