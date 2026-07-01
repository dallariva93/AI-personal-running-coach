"""Unit tests for streak and badge computation (P0-8: rest-day bridging)."""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

from app.processing.gamification import compute_streak


def _act(d: str) -> SimpleNamespace:
    return SimpleNamespace(date=d, distance_km=5.0, activity_type="easy")


def test_streak_no_activities():
    assert compute_streak([]) == (0, 0)


def test_streak_consecutive_days():
    today = date.today()
    acts = [_act((today - timedelta(days=i)).isoformat()) for i in range(3)]
    current, best = compute_streak(acts)
    assert current == 3
    assert best >= 3


def test_streak_broken_by_gap():
    today = date.today()
    acts = [
        _act(today.isoformat()),
        _act((today - timedelta(days=1)).isoformat()),
        _act((today - timedelta(days=3)).isoformat()),
    ]
    current, best = compute_streak(acts)
    assert current == 2


def test_streak_bridged_by_rest_day():
    """P0-8: a planned rest day between two run days should not break the streak."""
    today = date.today()
    rest_day = today - timedelta(days=1)
    acts = [
        _act(today.isoformat()),
        _act((today - timedelta(days=2)).isoformat()),
    ]
    rest_dates = {rest_day}
    current, best = compute_streak(acts, rest_dates=rest_dates)
    assert current == 2


def test_streak_not_bridged_by_non_rest_gap():
    """A gap that is NOT a rest day still breaks the streak."""
    today = date.today()
    acts = [
        _act(today.isoformat()),
        _act((today - timedelta(days=3)).isoformat()),
    ]
    current, best = compute_streak(acts, rest_dates=set())
    assert current == 1


def test_streak_bridged_by_multiple_rest_days():
    """Two consecutive rest days between runs are bridged."""
    today = date.today()
    rest1 = today - timedelta(days=1)
    rest2 = today - timedelta(days=2)
    acts = [
        _act(today.isoformat()),
        _act((today - timedelta(days=3)).isoformat()),
    ]
    rest_dates = {rest1, rest2}
    current, best = compute_streak(acts, rest_dates=rest_dates)
    assert current == 2


def test_best_streak_bridged():
    """Best-ever streak also benefits from rest-day bridging."""
    today = date.today()
    rest_days = {
        today - timedelta(days=2),
        today - timedelta(days=3),
        today - timedelta(days=5),
        today - timedelta(days=6),
    }
    acts = [
        _act(today.isoformat()),
        _act((today - timedelta(days=1)).isoformat()),
        _act((today - timedelta(days=4)).isoformat()),
        _act((today - timedelta(days=7)).isoformat()),
    ]
    rest_dates = rest_days
    current, best = compute_streak(acts, rest_dates=rest_dates)
    assert best >= 4


def test_streak_not_live_if_old():
    """Streak is 0 if last run was more than 1 day ago."""
    today = date.today()
    acts = [_act((today - timedelta(days=3)).isoformat())]
    current, best = compute_streak(acts)
    assert current == 0
