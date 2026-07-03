"""Digital Twin v0 — three athlete constants that become learned variables (A5).

The plan and the decision engine ship with population-default constants: a 10%
weekly ramp cap, a 2-day recovery, ~1.5 s/km/°C heat penalty. This module turns
each into a *personal* estimate from the athlete's own history, with a
``confidence`` (sample count) and a ``learning`` flag — below threshold the
population default is kept, so a thin history never produces a reckless number.

Pure functions only (CLAUDE.md): inputs are already-derived plain data, no I/O.
The DB-reading orchestrator lives in :mod:`app.services.athlete_model_service`.

Named ``digital_twin`` rather than ``athlete_model`` because that module name is
already taken by an unrelated physiology estimator (LT1/LT2/durability).
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from app.schemas import AthleteModel, AthleteModelEstimate

# ── Population defaults & bounds ──────────────────────────────────────────────
RAMP_DEFAULT_PCT = 10.0
RAMP_MIN_PCT, RAMP_MAX_PCT = 5.0, 15.0
RAMP_MIN_SAMPLES = 8  # week-pairs of history before we trust a personal ramp

RECOVERY_DEFAULT_DAYS = 2.0
RECOVERY_MIN_DAYS, RECOVERY_MAX_DAYS = 1.0, 7.0
RECOVERY_MIN_SAMPLES = 3  # recovery episodes

HEAT_DEFAULT_S_PER_C = 1.5
HEAT_MIN, HEAT_MAX = 0.0, 6.0
HEAT_HOT_THRESHOLD_C = 15.0
HEAT_MIN_HOT_SAMPLES = 10


@dataclass
class WeekObservation:
    """One training week: its load and whether a bad outcome followed it.

    ``bad_after`` is True when, in the 7 days after this week's load landed, the
    athlete hit any of: injury risk high, an execution collapse, or a red
    readiness day. Such a week's increase was *not* safely absorbed.
    """

    load: float
    bad_after: bool


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def estimate_ramp_tolerance(weeks: list[WeekObservation]) -> AthleteModelEstimate:
    """Max week-over-week % load increase the athlete absorbed without a bad
    outcome. Clamped to [5%, 15%]; default 10% below :data:`RAMP_MIN_SAMPLES`
    week-pairs of history.
    """
    valid_pairs = [(a, b) for a, b in zip(weeks, weeks[1:], strict=False) if a.load > 0]
    absorbed: list[float] = []
    for prev, cur in valid_pairs:
        if cur.load <= prev.load:
            continue
        pct = (cur.load - prev.load) / prev.load * 100.0
        if not cur.bad_after:
            absorbed.append(pct)

    confidence = len(valid_pairs)
    if confidence < RAMP_MIN_SAMPLES or not absorbed:
        return AthleteModelEstimate(
            value=RAMP_DEFAULT_PCT, confidence=confidence, learning=True
        )
    value = _clamp(round(max(absorbed), 1), RAMP_MIN_PCT, RAMP_MAX_PCT)
    return AthleteModelEstimate(value=value, confidence=confidence, learning=False)


def estimate_recovery_halflife(recovery_days: list[float]) -> AthleteModelEstimate:
    """Median days to bounce back (execution >=80 or readiness green) after a
    hard/too-hard effort or race. Clamped to [1, 7]; default 2 below
    :data:`RECOVERY_MIN_SAMPLES` episodes.
    """
    samples = [d for d in recovery_days if d >= 0]
    confidence = len(samples)
    if confidence < RECOVERY_MIN_SAMPLES:
        return AthleteModelEstimate(
            value=RECOVERY_DEFAULT_DAYS, confidence=confidence, learning=True
        )
    value = _clamp(
        float(round(statistics.median(samples))), RECOVERY_MIN_DAYS, RECOVERY_MAX_DAYS
    )
    return AthleteModelEstimate(value=value, confidence=confidence, learning=False)


def estimate_heat_sensitivity(
    points: list[tuple[float, float]],
) -> AthleteModelEstimate:
    """Slope of grade-adjusted easy pace (s/km) vs temperature (°C).

    ``points`` are ``(temperature_c, gap_sec_per_km)`` from easy runs. Confidence
    is the count of *hot* runs (>15°C); below :data:`HEAT_MIN_HOT_SAMPLES` the
    literature default (~1.5 s/km/°C) is kept. Slope clamped to [0, 6].
    """
    pts = [(t, g) for t, g in points if t is not None and g is not None]
    hot = [p for p in pts if p[0] > HEAT_HOT_THRESHOLD_C]
    confidence = len(hot)
    if confidence < HEAT_MIN_HOT_SAMPLES or len(pts) < 2:
        return AthleteModelEstimate(
            value=HEAT_DEFAULT_S_PER_C, confidence=confidence, learning=True
        )

    xs = [t for t, _ in pts]
    ys = [g for _, g in pts]
    mean_x = statistics.mean(xs)
    mean_y = statistics.mean(ys)
    denom = sum((x - mean_x) ** 2 for x in xs)
    if denom == 0:
        return AthleteModelEstimate(
            value=HEAT_DEFAULT_S_PER_C, confidence=confidence, learning=True
        )
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=False)) / denom
    value = _clamp(round(slope, 2), HEAT_MIN, HEAT_MAX)
    return AthleteModelEstimate(value=value, confidence=confidence, learning=False)


def build_athlete_model(
    weeks: list[WeekObservation],
    recovery_days: list[float],
    heat_points: list[tuple[float, float]],
    computed_at: str | None = None,
) -> AthleteModel:
    """Assemble the full :class:`AthleteModel` from derived history (pure)."""
    return AthleteModel(
        ramp_tolerance_pct=estimate_ramp_tolerance(weeks),
        recovery_halflife_days=estimate_recovery_halflife(recovery_days),
        heat_sensitivity_s_per_c=estimate_heat_sensitivity(heat_points),
        computed_at=computed_at,
    )
