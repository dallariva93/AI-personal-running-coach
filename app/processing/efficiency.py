"""Aerobic efficiency & progress metrics (GAP 11/12/13).

Load and fatigue tell you how *hard* you are training; they say nothing about
whether you are getting *fitter*. This module measures progress and aerobic
quality:

- **Aerobic Efficiency Index** — seconds of pace per heart-beat on easy runs
  (pace_sec_per_km / avg_hr). Lower is better. Tracking its trend over weeks
  reveals improvement (faster at the same HR) independent of training load.
- **Cardiac drift / decoupling** — within a single run, how much the
  pace-to-HR ratio degrades from the first half to the second half. Needs
  intra-run splits; returns None when unavailable.

Pure functions, no I/O.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from app.schemas import RunSummary

EASY_TYPES = {"easy", "recupero", "lungo"}


def _parse_date(value: str) -> date | None:
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def pace_to_seconds(pace: str | None) -> float | None:
    """Parse a ``M:SS`` or ``M:SS/km`` pace string into seconds per km."""
    if not pace:
        return None
    core = pace.split("/")[0].strip()
    parts = core.split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    except ValueError:
        return None
    return None


def _efficiency_of(run: RunSummary) -> float | None:
    """Seconds of pace per heart-beat for one run (lower = more efficient)."""
    pace_s = pace_to_seconds(run.avg_pace)
    if pace_s is None or not run.avg_hr:
        return None
    return pace_s / run.avg_hr


def aerobic_efficiency(
    runs: list[RunSummary], ref: date | None = None, window_days: int = 42
) -> tuple[float | None, str]:
    """Return ``(current_index, trend)`` for easy-run aerobic efficiency.

    Compares the recent half of the window to the older half. A meaningful drop
    in pace-per-beat means the athlete is improving.
    """
    ref = ref or date.today()
    start = ref - timedelta(days=window_days)
    samples: list[tuple[date, float]] = []
    for r in runs:
        d = _parse_date(r.date)
        if d and start <= d <= ref and r.activity_type in EASY_TYPES:
            eff = _efficiency_of(r)
            if eff is not None:
                samples.append((d, eff))
    if not samples:
        return None, "unknown"

    samples.sort()
    current = round(samples[-1][1], 4)
    if len(samples) < 4:
        return current, "unknown"

    mid = ref - timedelta(days=window_days // 2)
    older = [e for d, e in samples if d < mid]
    recent = [e for d, e in samples if d >= mid]
    if not older or not recent:
        return current, "unknown"

    older_avg = sum(older) / len(older)
    recent_avg = sum(recent) / len(recent)
    change = (recent_avg - older_avg) / older_avg
    if change < -0.03:
        trend = "improving"  # faster at the same HR
    elif change > 0.03:
        trend = "declining"
    else:
        trend = "stable"
    return current, trend


def decoupling(run: RunSummary) -> float | None:
    """Pace:HR decoupling (%) between the first and second half of a run.

    Requires ``splits_km`` formatted as ``"pace|hr"`` per km (e.g. ``"5:10|150"``)
    or ``"pace"`` alone. Returns the percentage degradation, or None if the
    intra-run data isn't rich enough.
    """
    splits = run.splits_km or []
    parsed: list[tuple[float, float | None]] = []
    for s in splits:
        if not isinstance(s, str):
            continue
        pace_part, _, hr_part = s.partition("|")
        pace_s = pace_to_seconds(pace_part)
        if pace_s is None:
            continue
        hr = float(hr_part) if hr_part.strip().isdigit() else None
        parsed.append((pace_s, hr))
    if len(parsed) < 4:
        return None

    half = len(parsed) // 2
    first, second = parsed[:half], parsed[half:]

    def ratio(chunk: list[tuple[float, float | None]]) -> float | None:
        hrs = [hr for _, hr in chunk if hr]
        if len(hrs) < len(chunk):
            return None
        speeds = [1.0 / p for p, _ in chunk]  # speed ∝ 1/pace
        avg_speed = sum(speeds) / len(speeds)
        avg_hr = sum(hrs) / len(hrs)
        return avg_speed / avg_hr

    r1, r2 = ratio(first), ratio(second)
    if r1 is None or r2 is None or r1 == 0:
        return None
    # Positive = efficiency dropped in the second half (drift).
    return round((r1 - r2) / r1 * 100, 1)
