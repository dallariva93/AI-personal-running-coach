"""Unit tests for streak and badge computation (P0-8: rest-day bridging)."""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

from app.processing.gamification import AdherenceDay, compute_adherence_streak, compute_streak


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


# -- Adherence streak (Roadmap Q4: plan honoured, not "ran every day") -------


def _done(d: date) -> AdherenceDay:
    return AdherenceDay(day=d, has_session=True, execution_status="completed_well")


def test_adherence_streak_empty_is_zero():
    assert compute_adherence_streak([]) == (0, 0)


def test_adherence_streak_all_completed():
    today = date.today()
    days = [_done(today - timedelta(days=i)) for i in range(5)]
    current, best = compute_adherence_streak(days)
    assert current == 5
    assert best == 5


def test_adherence_prescribed_rest_does_not_break():
    today = date.today()
    days = [
        _done(today - timedelta(days=2)),
        AdherenceDay(day=today - timedelta(days=1), prescribed_rest=True, ran_hard=False),
        _done(today),
    ]
    current, best = compute_adherence_streak(days)
    assert current == 3


def test_adherence_easy_run_on_rest_day_does_not_break():
    """A rest day with only an easy run is tolerated (per the brief's example)."""
    today = date.today()
    days = [
        AdherenceDay(day=today - timedelta(days=1), prescribed_rest=True, ran_hard=False),
        _done(today),
    ]
    current, _ = compute_adherence_streak(days)
    assert current == 2


def test_adherence_hard_run_on_rest_day_breaks():
    today = date.today()
    days = [
        _done(today - timedelta(days=2)),
        AdherenceDay(day=today - timedelta(days=1), prescribed_rest=True, ran_hard=True),
        _done(today),
    ]
    current, best = compute_adherence_streak(days)
    assert current == 1  # only today survives after the broken rest day
    assert best == 1


def test_adherence_skipped_session_breaks_streak():
    today = date.today()
    days = [
        _done(today - timedelta(days=3)),
        _done(today - timedelta(days=2)),
        AdherenceDay(day=today - timedelta(days=1), has_session=True, execution_status="skipped"),
        _done(today),
    ]
    current, best = compute_adherence_streak(days)
    assert current == 1
    assert best == 2


def test_adherence_unevaluated_session_does_not_break():
    """execution_status=None (not yet scored) gets the benefit of the doubt."""
    today = date.today()
    days = [
        _done(today - timedelta(days=1)),
        AdherenceDay(day=today, has_session=True, execution_status=None),
    ]
    current, _ = compute_adherence_streak(days)
    assert current == 2


def test_adherence_day_with_no_plan_coverage_is_neutral():
    """A day the plan simply didn't cover (not rest, not a session) is bridged:
    it doesn't break the streak, but (unlike rest/completed days) doesn't add
    to its length either — it's simply invisible to the count."""
    today = date.today()
    days = [
        _done(today - timedelta(days=2)),
        AdherenceDay(day=today - timedelta(days=1)),  # no session, no rest flag
        _done(today),
    ]
    current, _ = compute_adherence_streak(days)
    assert current == 2
