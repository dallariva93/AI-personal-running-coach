"""Unit tests for the deterministic week rebalancer (Fase E)."""

from __future__ import annotations

from app.processing.plan_rebalance import rebalance_week

# 0=Mon .. 6=Sun
_HARD = {"tempo", "intervals"}


def _apply(day_types: dict[int, str], swaps):
    dt = dict(day_types)
    for a, b in swaps:
        dt[a], dt[b] = dt[b], dt[a]
    return dt


def _no_adjacent_hard(dt: dict[int, str]) -> bool:
    return not any(dt.get(d) in _HARD and dt.get(d + 1) in _HARD for d in range(6))


def test_already_spaced_week_is_untouched():
    dt = {0: "rest", 1: "intervals", 2: "easy", 3: "tempo", 4: "rest", 5: "easy", 6: "long"}
    swaps, notes = rebalance_week(dt, locked=set())
    assert swaps == [] and notes == []


def test_adjacent_quality_days_are_separated():
    # intervals (2) next to tempo (3); athlete anchored day 2.
    dt = {0: "rest", 1: "easy", 2: "intervals", 3: "tempo", 4: "rest", 5: "easy", 6: "long"}
    swaps, notes = rebalance_week(dt, locked={2})
    assert swaps and notes
    out = _apply(dt, swaps)
    assert _no_adjacent_hard(out)
    assert out[2] == "intervals"  # anchor preserved


def test_anchor_and_completed_days_never_move():
    dt = {0: "tempo", 1: "intervals", 2: "easy", 3: "rest", 4: "easy", 5: "rest", 6: "long"}
    # Both hard days locked (e.g. one anchored, one completed) → can't fix.
    swaps, notes = rebalance_week(dt, locked={0, 1})
    assert swaps == []  # nothing movable, left for a warning


def test_reshape_preserves_the_session_mix():
    dt = {0: "rest", 1: "easy", 2: "intervals", 3: "tempo", 4: "rest", 5: "easy", 6: "long"}
    swaps, _ = rebalance_week(dt, locked={2})
    out = _apply(dt, swaps)
    assert sorted(out.values()) == sorted(dt.values())  # only days permuted


def test_no_receiver_leaves_conflict():
    # Every non-hard day is locked, so there's nowhere to relocate the tempo.
    dt = {0: "easy", 1: "intervals", 2: "tempo", 3: "easy", 4: "easy", 5: "easy", 6: "easy"}
    swaps, notes = rebalance_week(dt, locked={1, 0, 3, 4, 5, 6})
    assert swaps == []


def test_case_insensitive_types():
    dt = {0: "rest", 1: "easy", 2: "Intervals", 3: "TEMPO", 4: "rest", 5: "easy", 6: "long"}
    swaps, _ = rebalance_week(dt, locked={2})
    assert swaps  # recognised despite casing
