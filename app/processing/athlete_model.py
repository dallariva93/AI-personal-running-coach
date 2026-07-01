"""AthleteModel v1: physiological thresholds estimated from historical runs.

Replaces the static profile form with a living model that learns from how the
athlete actually trains. The estimates feed into the decision engine (intensity
prescription), the execution score (target zone validation) and the adaptive
plan (individualised volume factors).

Pure functions: given a list of RunSummary objects and optional existing
thresholds, returns updated AthletePhysiology fields.
"""

from __future__ import annotations

import statistics
from datetime import date, timedelta

from app.schemas import AthletePhysiology, RunSummary

_HARD_TYPES = {"tempo", "threshold", "soglia", "intervals", "intervalli", "vo2max"}
_EASY_TYPES = {"easy", "recovery", "recupero"}
_LONG_MIN_KM = 15.0
_MIN_SESSIONS = 4


def _parse_date(value: str) -> date | None:
    from datetime import datetime
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _pace_sec(pace: str | None) -> float | None:
    if not pace:
        return None
    core = pace.split("/")[0]
    parts = core.split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
    except (ValueError, TypeError):
        return None
    return None


def estimate_lt2_pace(runs: list[RunSummary], ref: date | None = None) -> str | None:
    """Estimate lactate threshold pace from quality sessions.

    Uses the median pace of recent tempo/threshold runs (not intervals, which
    are faster than LT2). Returns None if insufficient data.
    """
    ref = ref or date.today()
    cutoff = ref - timedelta(days=90)
    tempo_paces: list[float] = []
    for r in runs:
        d = _parse_date(r.date)
        if d is None or d < cutoff:
            continue
        at = (r.activity_type or "").lower()
        if at in {"tempo", "threshold", "soglia"} and r.distance_km >= 3.0:
            p = _pace_sec(r.avg_pace)
            if p is not None:
                tempo_paces.append(p)
    if len(tempo_paces) < 2:
        return None
    median_pace = statistics.median(tempo_paces)
    return _sec_to_pace(median_pace)


def estimate_lt1_pace(runs: list[RunSummary], lt2_sec: float | None = None) -> str | None:
    """Estimate aerobic threshold pace (LT1).

    If LT2 is known, LT1 is approximately 15% slower (standard physiological
    relationship). Otherwise, uses the median pace of easy runs as a proxy.
    """
    if lt2_sec is not None:
        lt1_sec = lt2_sec * 1.15
        return _sec_to_pace(lt1_sec)
    easy_paces: list[float] = []
    for r in runs:
        at = (r.activity_type or "").lower()
        if at in _EASY_TYPES and r.distance_km >= 3.0:
            p = _pace_sec(r.avg_pace)
            if p is not None:
                easy_paces.append(p)
    if len(easy_paces) < 3:
        return None
    return _sec_to_pace(statistics.median(easy_paces))


def estimate_durability(runs: list[RunSummary]) -> float | None:
    """Estimate pace degradation per 10 km in long runs (sec/km per 10 km).

    Compares the first 5 km pace versus the last 5 km pace in long runs
    (>15 km) that have split data. Lower values indicate better durability.
    Returns None if no long runs with splits are available.
    """
    degradations: list[float] = []
    for r in runs:
        if r.distance_km < _LONG_MIN_KM or not r.splits_km:
            continue
        splits = r.splits_km
        if len(splits) < 10:
            continue
        first_paces = [_pace_sec(s) for s in splits[:5]]
        last_paces = [_pace_sec(s) for s in splits[-5:]]
        first_valid = [p for p in first_paces if p is not None]
        last_valid = [p for p in last_paces if p is not None]
        if len(first_valid) < 3 or len(last_valid) < 3:
            continue
        first_avg = statistics.mean(first_valid)
        last_avg = statistics.mean(last_valid)
        if first_avg <= 0:
            continue
        delta_per_10k = (last_avg - first_avg) / (r.distance_km / 10.0)
        if delta_per_10k >= 0:
            degradations.append(delta_per_10k)
    if len(degradations) < 2:
        return None
    return round(statistics.median(degradations), 1)


def estimate_speed_reserve(
    runs: list[RunSummary], lt2_sec: float | None
) -> float | None:
    """Estimate speed reserve: difference between LT2 pace and best 5K pace.

    Uses the fastest 5K split pace available, or the fastest pace of any
    run >= 4 km. Returns the gap in sec/km (always positive: 5K pace < LT2).
    """
    best_5k_sec: float | None = None
    for r in runs:
        if r.distance_km < 4.0:
            continue
        p = _pace_sec(r.fastest_split_5k) or _pace_sec(r.avg_pace)
        if p is not None:
            if best_5k_sec is None or p < best_5k_sec:
                best_5k_sec = p
    if best_5k_sec is None or lt2_sec is None:
        return None
    reserve = lt2_sec - best_5k_sec
    return round(max(0.0, reserve), 1)


def update_athlete_model(
    runs: list[RunSummary],
    existing: AthletePhysiology | None = None,
    ref: date | None = None,
) -> AthletePhysiology:
    """Compute or refresh the physiological model from run history.

    Preserves manually-set values (e.g. from a lab test) when present; only
    fills or updates fields that are None or that can be improved from data.
    """
    ref = ref or date.today()
    model = AthletePhysiology(
        lt1_pace=existing.lt1_pace if existing else None,
        lt2_pace=existing.lt2_pace if existing else None,
        critical_speed=existing.critical_speed if existing else None,
        resting_hr=existing.resting_hr if existing else None,
        lactate_threshold_hr=existing.lactate_threshold_hr if existing else None,
        durability_index=existing.durability_index if existing else None,
        speed_reserve_sec=existing.speed_reserve_sec if existing else None,
    )

    if len(runs) < _MIN_SESSIONS:
        return model

    lt2_str = estimate_lt2_pace(runs, ref=ref) if model.lt2_pace is None else model.lt2_pace
    lt2_sec = _pace_sec(lt2_str) if lt2_str else _pace_sec(model.lt2_pace)

    if model.lt2_pace is None and lt2_str:
        model.lt2_pace = lt2_str

    if model.lt1_pace is None:
        lt1_str = estimate_lt1_pace(runs, lt2_sec=lt2_sec)
        if lt1_str:
            model.lt1_pace = lt1_str

    if model.durability_index is None:
        dur = estimate_durability(runs)
        if dur is not None:
            model.durability_index = dur

    if model.speed_reserve_sec is None:
        sr = estimate_speed_reserve(runs, lt2_sec)
        if sr is not None:
            model.speed_reserve_sec = sr

    return model


def _sec_to_pace(sec: float) -> str:
    """Convert seconds/km to ``M:SS`` pace string."""
    m = int(sec // 60)
    s = int(round(sec % 60))
    if s == 60:
        m += 1
        s = 0
    return f"{m}:{s:02d}/km"
