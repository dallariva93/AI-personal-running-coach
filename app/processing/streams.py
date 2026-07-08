"""Scalar features derived from per-second sample streams (Fase 1).

The raw per-second series (from
:func:`app.collection.synthesize.extract_sample_streams`) are stored as a JSON
blob and never queried in SQL. These pure functions reduce them to a handful of
indexable scalars (GARMIN_DATA_PLAN.md A9):

- **aerobic decoupling** — how much the speed:HR ratio degrades over the run;
- **cardiac drift** — how much average HR rises over the run;
- **speed CV** — coefficient of variation of speed (pacing evenness).

Every function returns ``None`` when its input stream is missing or too short
to be meaningful. No I/O, deterministic.
"""

from __future__ import annotations

from statistics import mean, pstdev
from typing import Any

from app.schemas import StreamFeatures

# Each half of a run must carry at least this many samples for a split-based
# feature (decoupling, drift) to be trustworthy.
_MIN_HALF_SAMPLES = 5
# Samples slower than this (m/s ≈ 0.5) are treated as stopped/paused and left
# out of pacing-quality features so red lights don't masquerade as slow running.
_MIN_MOVING_SPEED = 0.5


def _series(streams: dict[str, Any], name: str) -> list | None:
    value = streams.get(name)
    return value if isinstance(value, list) else None


def _split_index(times: list[float]) -> int | None:
    """Index of the first sample in the second *time* half of the series.

    Time-based (not count-based) so it stays correct even if the series was
    downsampled non-uniformly.
    """
    if len(times) < 2:
        return None
    mid = (times[0] + times[-1]) / 2.0
    for i, t in enumerate(times):
        if t >= mid:
            return i if 0 < i < len(times) else None
    return None


def speed_cv(streams: dict[str, Any]) -> float | None:
    """Coefficient of variation of speed (%) over moving samples."""
    speed = _series(streams, "speed")
    if not speed:
        return None
    moving = [float(s) for s in speed if s is not None and s >= _MIN_MOVING_SPEED]
    if len(moving) < 2:
        return None
    avg = mean(moving)
    if avg <= 0:
        return None
    return round(pstdev(moving) / avg * 100, 1)


def cardiac_drift(streams: dict[str, Any]) -> float | None:
    """Percentage rise of average HR from the first to the second time-half."""
    times = _series(streams, "t")
    hr = _series(streams, "hr")
    if not times or not hr:
        return None
    t_clean: list[float] = []
    hr_clean: list[float] = []
    for t, h in zip(times, hr, strict=False):
        if h is not None:
            t_clean.append(float(t))
            hr_clean.append(float(h))
    split = _split_index(t_clean)
    if split is None:
        return None
    first, second = hr_clean[:split], hr_clean[split:]
    if len(first) < _MIN_HALF_SAMPLES or len(second) < _MIN_HALF_SAMPLES:
        return None
    avg_first = mean(first)
    if avg_first <= 0:
        return None
    return round((mean(second) - avg_first) / avg_first * 100, 1)


def aerobic_decoupling(streams: dict[str, Any]) -> float | None:
    """Percentage drop of the speed:HR ratio from the first to the second half.

    Positive = aerobic efficiency degraded (drift); negative = negative split.
    Uses only moving samples where both speed and HR are present.
    """
    times = _series(streams, "t")
    speed = _series(streams, "speed")
    hr = _series(streams, "hr")
    if not times or not speed or not hr:
        return None
    t_pairs: list[float] = []
    speeds: list[float] = []
    hrs: list[float] = []
    for t, s, h in zip(times, speed, hr, strict=False):
        if s is not None and h is not None and s >= _MIN_MOVING_SPEED and h > 0:
            t_pairs.append(float(t))
            speeds.append(float(s))
            hrs.append(float(h))
    split = _split_index(t_pairs)
    if split is None:
        return None
    if split < _MIN_HALF_SAMPLES or len(t_pairs) - split < _MIN_HALF_SAMPLES:
        return None
    ratio_first = mean(speeds[:split]) / mean(hrs[:split])
    ratio_second = mean(speeds[split:]) / mean(hrs[split:])
    if ratio_first <= 0:
        return None
    return round((ratio_first - ratio_second) / ratio_first * 100, 1)


def compute_stream_features(streams: Any) -> StreamFeatures:
    """Reduce a ``sample_streams`` dict to its indexable scalar features."""
    if not isinstance(streams, dict):
        return StreamFeatures()
    return StreamFeatures(
        decoupling_pct=aerobic_decoupling(streams),
        hr_drift_pct=cardiac_drift(streams),
        speed_cv=speed_cv(streams),
    )
