"""Processing layer: derive training-load and form metrics from runs.

Pure functions, no I/O, no AI. Given a list of :class:`RunSummary` it computes
ACWR, weekly load, monotony, the 80/20 ratio, a form-state classification and
the load trend. This is the quantitative input the coaching layer reasons over.
"""

from app.processing.efficiency import aerobic_efficiency, decoupling
from app.processing.injury import injury_risk
from app.processing.load import (
    equivalent_flat_km,
    estimate_rpe,
    internal_load,
    is_truly_easy,
)
from app.processing.metrics import compute_metrics, fitness_fatigue, weekly_buckets
from app.processing.periodization import (
    build_periodization,
    current_phase,
    phase_for,
)
from app.processing.snapshot import build_snapshot

__all__ = [
    "compute_metrics",
    "weekly_buckets",
    "fitness_fatigue",
    "internal_load",
    "estimate_rpe",
    "equivalent_flat_km",
    "is_truly_easy",
    "build_periodization",
    "current_phase",
    "phase_for",
    "injury_risk",
    "aerobic_efficiency",
    "decoupling",
    "build_snapshot",
]
