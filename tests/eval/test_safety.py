"""Deterministic coach safety scenarios (Roadmap A9 / Passo 9).

Fifty synthetic scenarios (5 athletes x 5 readiness patterns x 2 phases) run the
real coaching pipeline day by day and assert the safety invariants hold. A
meta-test deliberately breaks the engine and proves the harness catches it — so
these are real guardrails, not a coverage ritual.
"""

from __future__ import annotations

import itertools
from datetime import date

import pytest

from tests.eval.athletes import ATHLETES
from tests.eval.simulator import (
    all_violations,
    check_taper_quality_preserved,
    run_simulation,
)

# A Monday, so plan weekdays (0=Mon..6=Sun) map cleanly onto calendar dates.
START = date(2026, 1, 5)

READINESS_PATTERNS = ["green", "amber", "red", "volatile", "declining"]
PHASES = [False, True]  # False = build, True = taper

SCENARIOS = [
    pytest.param(
        athlete,
        pattern,
        taper,
        id=f"{athlete.key}-{pattern}-{'taper' if taper else 'build'}",
    )
    for athlete, pattern, taper in itertools.product(ATHLETES, READINESS_PATTERNS, PHASES)
]


def test_scenario_matrix_is_fifty():
    """The brief requires 50 deterministic scenarios."""
    assert len(SCENARIOS) == 50


@pytest.mark.parametrize("athlete,pattern,taper", SCENARIOS)
def test_safety_invariants(session, athlete, pattern, taper):
    """Every scenario must satisfy all applicable safety invariants."""
    result = run_simulation(
        session, athlete, readiness_pattern=pattern, taper=taper, start=START
    )
    violations = all_violations(session, result)
    assert not violations, "Safety violations:\n" + "\n".join(violations)


def test_broken_engine_is_caught(session, monkeypatch):
    """Breaking a real safety guard must fail the harness.

    This is the brief's litmus test: gut a safety rule and an invariant check
    has to light up. We neutralise the adaptive engine's taper detection
    (``_is_taper``) — the guard that keeps a reduced quality stimulus during the
    taper — so a red taper day now wrongly downgrades quality to easy, and
    assert :func:`check_taper_quality_preserved` reports the violation.
    """
    import app.services.adaptive_plan as adaptive

    monkeypatch.setattr(adaptive, "_is_taper", lambda *a, **k: False)

    athlete = ATHLETES[0]  # beginner_stable: low load, never severe
    result = run_simulation(
        session, athlete, readiness_pattern="red", taper=True, start=START
    )
    assert not result.any_severe, "scenario unexpectedly severe; test premise invalid"
    assert check_taper_quality_preserved(session, result), (
        "Harness failed to catch a deliberately broken engine (taper quality cancelled)"
    )
