"""Trail-running metrics (GAP 20).

Road metrics (pace, distance) under-describe trail efforts: a hilly run is
defined as much by climb as by kilometres. This module derives the trail-
specific signals — vertical speed, climb density, time on feet and a
grade-adjusted equivalent distance — and flags when a run is really a trail run.

Pure functions, no I/O.
"""

from __future__ import annotations

from app.processing.load import equivalent_flat_km
from app.schemas import RunSummary, TrailMetrics

# A run with more than this much climb per km counts as "trail/hilly".
_TRAIL_CLIMB_PER_KM = 25.0


def is_trail(run: RunSummary) -> bool:
    """True when climb density marks the run as trail/hilly."""
    if not run.elevation_gain_m or run.distance_km <= 0:
        return False
    return run.elevation_gain_m / run.distance_km >= _TRAIL_CLIMB_PER_KM


def trail_metrics(run: RunSummary) -> TrailMetrics | None:
    """Compute trail metrics for a run, or None when there's no climb data."""
    if not run.elevation_gain_m or run.duration_min <= 0:
        return None
    hours = run.duration_min / 60.0
    vert_speed = round(run.elevation_gain_m / hours, 0) if hours > 0 else None
    climb_per_km = (
        round(run.elevation_gain_m / run.distance_km, 1) if run.distance_km > 0 else None
    )
    return TrailMetrics(
        elevation_gain_m=run.elevation_gain_m,
        elevation_loss_m=run.elevation_loss_m,
        vertical_speed_m_per_h=vert_speed,
        climb_per_km=climb_per_km,
        time_on_feet_min=round(run.duration_min, 0),
        equivalent_flat_km=equivalent_flat_km(run),
        is_trail=is_trail(run),
    )
