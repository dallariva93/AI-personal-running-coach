"""Athlete snapshot: long-horizon memory for the coach (GAP 22).

The LLM only sees the last ~10-14 runs, so it has no sense of the athlete's
history. This module distils months of training into a compact summary —
recent bests, typical weekly volume, longest run — that fits in the prompt and
gives the coach context it otherwise lacks.

Pure functions, deterministic given a reference date.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from app.schemas import AthleteSnapshot, RunSummary

# Distances (km) we try to find a representative best effort for.
_RACE_DISTANCES = {"5k": 5.0, "10k": 10.0, "half": 21.1, "marathon": 42.2}
_TOLERANCE = 0.08  # ±8% counts as "that distance"


def _parse_date(value: str) -> date | None:
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _fmt_duration(minutes: float) -> str:
    total = int(round(minutes * 60))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _best_for(runs: list[RunSummary], target_km: float) -> str | None:
    """Fastest run close to ``target_km`` (by total duration)."""
    candidates = [
        r
        for r in runs
        if r.distance_km > 0
        and abs(r.distance_km - target_km) <= target_km * _TOLERANCE
        and r.duration_min > 0
    ]
    if not candidates:
        return None
    best = min(candidates, key=lambda r: r.duration_min / r.distance_km)
    return _fmt_duration(best.duration_min)


def build_snapshot(
    runs: list[RunSummary], ref: date | None = None, months: int = 6
) -> AthleteSnapshot:
    """Summarise the last ``months`` of training into an :class:`AthleteSnapshot`."""
    ref = ref or date.today()
    start = ref - timedelta(days=months * 30)
    window = [r for r in runs if (d := _parse_date(r.date)) and start <= d <= ref]

    snapshot = AthleteSnapshot()
    if not window:
        return snapshot

    snapshot.runs_count = len(window)
    snapshot.total_distance_km = round(sum(r.distance_km for r in window), 1)
    weeks = max(1, months * 30 / 7)
    snapshot.avg_weekly_volume_km = round(snapshot.total_distance_km / weeks, 1)
    snapshot.longest_run_km = round(max(r.distance_km for r in window), 1)
    snapshot.best_5k = _best_for(window, _RACE_DISTANCES["5k"])
    snapshot.best_10k = _best_for(window, _RACE_DISTANCES["10k"])
    snapshot.best_half = _best_for(window, _RACE_DISTANCES["half"])
    snapshot.best_marathon = _best_for(window, _RACE_DISTANCES["marathon"])
    return snapshot
