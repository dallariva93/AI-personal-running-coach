"""Processing layer: derive training-load and form metrics from runs.

Pure functions, no I/O, no AI. Given a list of :class:`RunSummary` it computes
ACWR, weekly load, monotony, the 80/20 ratio, a form-state classification and
the load trend. This is the quantitative input the coaching layer reasons over.
"""

from app.processing.adaptive import adapt_plan
from app.processing.decision import decide_today
from app.processing.efficiency import aerobic_efficiency, decoupling
from app.processing.execution import score_execution
from app.processing.gamification import compute_badges, compute_streak
from app.processing.injury import injury_risk
from app.processing.load import (
    equivalent_flat_km,
    estimate_rpe,
    intensity_class,
    internal_load,
    is_truly_easy,
)
from app.processing.metrics import compute_metrics, fitness_fatigue, weekly_buckets
from app.processing.performance import (
    estimate_thresholds,
    predict_race_time,
    seconds_to_time,
    time_to_seconds,
)
from app.processing.periodization import (
    build_periodization,
    current_phase,
    phase_for,
)
from app.processing.records import compute_personal_records
from app.processing.snapshot import build_snapshot
from app.processing.trail import is_trail, trail_metrics

__all__ = [
    "compute_metrics",
    "weekly_buckets",
    "fitness_fatigue",
    "internal_load",
    "estimate_rpe",
    "equivalent_flat_km",
    "is_truly_easy",
    "intensity_class",
    "build_periodization",
    "current_phase",
    "phase_for",
    "injury_risk",
    "aerobic_efficiency",
    "decoupling",
    "build_snapshot",
    "predict_race_time",
    "estimate_thresholds",
    "seconds_to_time",
    "time_to_seconds",
    "adapt_plan",
    "decide_today",
    "score_execution",
    "trail_metrics",
    "is_trail",
    "compute_personal_records",
    "compute_streak",
    "compute_badges",
]
