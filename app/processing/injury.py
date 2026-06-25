"""Composite injury-risk model (GAP 14).

The old code inferred risk almost entirely from ACWR (plus monotony). The
literature is clear that overuse risk is multi-factorial, so this module blends
several independent signals into a single 0-100 score with the factors that
fired, so the advice is explainable:

- acute:chronic workload ratio (ACWR) spikes,
- training monotony (too little variation),
- week-on-week volume jumps,
- consecutive days without rest,
- hard sessions stacked too close together,
- sharp drops in the easy-volume share (too much intensity),
- elevation spikes versus the recent norm.

Pure functions, deterministic given a reference date.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from app.processing.tuning import injury_cutoffs
from app.schemas import AthleteProfile, InjuryRisk, RunSummary, TrainingMetrics

_HARD_TYPES = {"tempo", "intervalli", "gara"}


def _parse_date(value: str) -> date | None:
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _consecutive_training_days(runs: list[RunSummary], ref: date) -> int:
    """How many days in a row up to ``ref`` had at least one run."""
    days = {d for r in runs if (d := _parse_date(r.date)) and d <= ref}
    streak = 0
    cursor = ref
    while cursor in days:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def _hard_sessions_close(runs: list[RunSummary], ref: date, window: int = 14) -> int:
    """Count pairs of hard sessions run within 48h of each other recently."""
    hard_days = sorted(
        d
        for r in runs
        if r.activity_type in _HARD_TYPES and (d := _parse_date(r.date)) and (ref - d).days < window
    )
    close = 0
    for earlier, later in zip(hard_days, hard_days[1:], strict=False):
        if 0 < (later - earlier).days <= 2:
            close += 1
    return close


def _km_between(runs: list[RunSummary], start: date, end: date) -> float:
    return sum(r.distance_km for r in runs if (d := _parse_date(r.date)) and start <= d <= end)


def injury_risk(
    runs: list[RunSummary],
    metrics: TrainingMetrics,
    ref: date | None = None,
    profile: AthleteProfile | None = None,
) -> InjuryRisk:
    """Blend independent overuse signals into a 0-100 score.

    The moderate/high cutoffs scale with the athlete's risk tolerance, so a
    risk-aggressive runner is flagged only on clearly elevated combinations.
    """
    ref = ref or date.today()
    score = 0.0
    factors: list[str] = []

    acwr = metrics.acwr
    if acwr is not None:
        if acwr > 1.5:
            score += 30
            factors.append(f"ACWR molto alto ({acwr:.2f})")
        elif acwr > 1.3:
            score += 15
            factors.append(f"ACWR sopra la fascia ottimale ({acwr:.2f})")

    if metrics.monotony is not None and metrics.monotony > 2.0:
        score += 15
        factors.append(f"monotonia alta ({metrics.monotony:.1f})")

    this_week = _km_between(runs, ref - timedelta(days=6), ref)
    prev_week = _km_between(runs, ref - timedelta(days=13), ref - timedelta(days=7))
    if prev_week > 0:
        jump = (this_week - prev_week) / prev_week
        if jump > 0.30:
            score += 20
            factors.append(f"volume settimanale +{jump*100:.0f}%")
        elif jump > 0.10:
            score += 10
            factors.append(f"volume settimanale +{jump*100:.0f}%")

    streak = _consecutive_training_days(runs, ref)
    if streak >= 9:
        score += 20
        factors.append(f"{streak} giorni consecutivi senza riposo")
    elif streak >= 6:
        score += 10
        factors.append(f"{streak} giorni consecutivi senza riposo")

    close = _hard_sessions_close(runs, ref)
    if close:
        score += min(20, 10 * close)
        factors.append(f"{close} sedute intense troppo ravvicinate")

    if metrics.easy_ratio is not None and metrics.easy_ratio < 0.6:
        score += 10
        factors.append(f"poco volume facile ({metrics.easy_ratio*100:.0f}%)")

    score = round(min(100.0, score), 0)
    moderate_at, high_at = injury_cutoffs(profile)
    if score >= high_at:
        level = "high"
    elif score >= moderate_at:
        level = "moderate"
    else:
        level = "low"
    return InjuryRisk(score=score, level=level, factors=factors)
