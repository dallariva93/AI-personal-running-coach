"""Race prediction & threshold evolution — the "elite coach" layer (Fase 4).

Two capabilities the final vision asks for:

- **Race predictor** — from the athlete's best recent efforts (the snapshot),
  extrapolate a finish time for the goal distance with Riegel's endurance model,
  nudged by the current aerobic-efficiency trend, and turn the gap to the target
  into a hit **probability**. This powers statements like
  *"marathon in 3h15' with ~82% probability"*.
- **Threshold evolution** — estimate the lactate-threshold (LT2) pace and
  critical speed from recent hard efforts, so zones and paces track fitness
  instead of being set once (GAP 7, made dynamic).

Pure functions, deterministic given a reference date.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta

from app.schemas import (
    AthletePhysiology,
    AthleteSnapshot,
    Goal,
    RacePrediction,
    RunSummary,
)

# Canonical race distances (km).
_GOAL_DISTANCE = {"5k": 5.0, "10k": 10.0, "half": 21.0975, "marathon": 42.195}
# Riegel fatigue exponent: time scales with distance^1.06.
_RIEGEL_EXP = 1.06
_HARD_TYPES = {"tempo", "gara", "intervalli"}


def _parse_date(value: str) -> date | None:
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def time_to_seconds(value: str | None) -> float | None:
    """Parse ``HH:MM:SS`` / ``MM:SS`` / ``M:SS`` into seconds."""
    if not value:
        return None
    parts = value.split(":")
    try:
        nums = [float(p) for p in parts]
    except ValueError:
        return None
    if len(nums) == 3:
        return nums[0] * 3600 + nums[1] * 60 + nums[2]
    if len(nums) == 2:
        return nums[0] * 60 + nums[1]
    if len(nums) == 1:
        return nums[0]
    return None


def seconds_to_time(seconds: float | None) -> str | None:
    """Format seconds into ``H:MM:SS`` (or ``M:SS`` under an hour)."""
    if seconds is None:
        return None
    total = int(round(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _best_efforts(snapshot: AthleteSnapshot) -> list[tuple[float, float]]:
    """Return ``(distance_km, seconds)`` pairs from the snapshot bests."""
    pairs = []
    for dist, value in (
        (5.0, snapshot.best_5k),
        (10.0, snapshot.best_10k),
        (21.0975, snapshot.best_half),
        (42.195, snapshot.best_marathon),
    ):
        secs = time_to_seconds(value)
        if secs:
            pairs.append((dist, secs))
    return pairs


def predict_race_time(
    goal: Goal | None,
    snapshot: AthleteSnapshot,
    efficiency_trend: str | None = None,
) -> RacePrediction | None:
    """Predict the goal-race finish time and the probability of the target."""
    if goal is None:
        return None
    target_dist = _GOAL_DISTANCE.get(goal.goal_type)
    if target_dist is None:
        return None

    efforts = _best_efforts(snapshot)
    if not efforts:
        return RacePrediction(
            goal_type=goal.goal_type, distance_km=target_dist,
            target_time=goal.target_time,
            target_seconds=time_to_seconds(goal.target_time),
            confidence="low", basis="dati insufficienti",
        )

    # Use the effort whose distance is closest (in log space) to the target.
    ref_dist, ref_secs = min(
        efforts, key=lambda e: abs(math.log(e[0]) - math.log(target_dist))
    )
    predicted = ref_secs * (target_dist / ref_dist) ** _RIEGEL_EXP

    # Nudge by the efficiency trend (improving → a touch faster, etc.).
    if efficiency_trend == "improving":
        predicted *= 0.98
    elif efficiency_trend == "declining":
        predicted *= 1.02

    # Confidence from how far we extrapolate.
    ratio = max(target_dist, ref_dist) / min(target_dist, ref_dist)
    if ratio <= 1.5:
        confidence = "high"
    elif ratio <= 3.0:
        confidence = "medium"
    else:
        confidence = "low"

    target_secs = time_to_seconds(goal.target_time)
    probability = None
    if target_secs:
        # Logistic on the relative gap; spread widens with lower confidence.
        spread = target_secs * {"high": 0.025, "medium": 0.04, "low": 0.06}[confidence]
        probability = round(1.0 / (1.0 + math.exp(-(target_secs - predicted) / spread)), 2)

    return RacePrediction(
        goal_type=goal.goal_type,
        distance_km=target_dist,
        predicted_time=seconds_to_time(predicted),
        predicted_seconds=round(predicted, 0),
        target_time=goal.target_time,
        target_seconds=target_secs,
        probability=probability,
        basis=f"miglior {ref_dist:g} km in {seconds_to_time(ref_secs)}",
        confidence=confidence,
    )


def nearest_goal_type(distance_km: float) -> str:
    """Map an arbitrary race distance to the nearest canonical ``goal_type``
    (5k/10k/half/marathon), by the same log-space ratio :func:`predict_race_time`
    uses to pick a reference effort (Roadmap A6: race recap for any race
    distance, not just the athlete's declared goal)."""
    return min(
        _GOAL_DISTANCE,
        key=lambda k: abs(math.log(distance_km) - math.log(_GOAL_DISTANCE[k])),
    )


def estimate_thresholds(
    runs: list[RunSummary], ref: date | None = None, window_days: int = 60
) -> AthletePhysiology | None:
    """Estimate LT2 pace & critical speed from recent hard efforts (GAP 7)."""
    ref = ref or date.today()
    start = ref - timedelta(days=window_days)
    paces: list[float] = []  # seconds per km on sustained hard efforts
    for r in runs:
        d = _parse_date(r.date)
        if (
            d and start <= d <= ref
            and r.activity_type in _HARD_TYPES
            and r.distance_km >= 4.0
            and r.duration_min > 0
        ):
            paces.append(r.duration_min * 60 / r.distance_km)
    if not paces:
        return None

    # LT2 ≈ the fastest sustained hard pace; critical speed a touch faster.
    lt2 = min(paces)
    cs = lt2 * 0.97
    return AthletePhysiology(
        lt2_pace=seconds_to_time(lt2),
        critical_speed=seconds_to_time(cs),
    )
