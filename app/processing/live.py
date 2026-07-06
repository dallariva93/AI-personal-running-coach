"""Server-side synthesis for phone-recorded live runs (G1, milestone M1).

The phone uploads a compact recording: cumulative ``(t seconds, d km)`` samples
(plus optional heart rate) and manual laps. The server derives what the rest of
the pipeline expects from a Garmin run — per-km splits, average pace, HR
aggregates — so a live run is a first-class :class:`RunSummary` downstream.

Pure functions: no I/O, deterministic.
"""

from __future__ import annotations

from app.schemas import LiveLap, LiveSample


def _fmt_mmss(seconds: float) -> str:
    total = int(round(seconds))
    m, s = divmod(total, 60)
    return f"{m}:{s:02d}"


def derive_avg_pace(distance_km: float, duration_min: float) -> str | None:
    """Average pace "M:SS/km" from totals, or None when either is missing."""
    if distance_km <= 0 or duration_min <= 0:
        return None
    return _fmt_mmss(duration_min * 60.0 / distance_km) + "/km"


def _series(samples: list[LiveSample], laps: list[LiveLap]) -> list[tuple[float, float]]:
    """The best cumulative (t, d) series available: samples, else the laps.

    A manual lap is itself a cumulative (t, d) point, so on a recording without
    a sampled series (very old app version, or trimmed payload) the laps still
    give a coarse but honest basis for split interpolation.
    """
    pts = [(s.t, s.d) for s in samples] if len(samples) >= 2 else [(lap.t, lap.d) for lap in laps]
    pts = [(t, d) for t, d in pts if t >= 0 and d >= 0]
    pts.sort()
    # Drop non-monotonic distance points (GPS jitter the client didn't filter).
    cleaned: list[tuple[float, float]] = []
    for t, d in pts:
        if cleaned and d < cleaned[-1][1]:
            continue
        cleaned.append((t, d))
    return cleaned


def _time_at_km(series: list[tuple[float, float]], km: float) -> float | None:
    """Linear interpolation of the elapsed time at cumulative distance ``km``."""
    for (t0, d0), (t1, d1) in zip(series, series[1:], strict=False):
        if d0 <= km <= d1:
            if d1 == d0:
                return t0
            frac = (km - d0) / (d1 - d0)
            return t0 + frac * (t1 - t0)
    return None


def derive_splits(
    samples: list[LiveSample],
    laps: list[LiveLap],
    distance_km: float,
) -> list[str] | None:
    """Per-km split paces ("M:SS" per km) interpolated on the recording.

    Returns None when there is no usable series or the run is under 1 km —
    the caller then falls back to the average pace only.
    """
    series = _series(samples, laps)
    if len(series) < 2 or distance_km < 1.0:
        return None

    splits: list[str] = []
    prev_t = _time_at_km(series, 0.0) or series[0][0]
    for km in range(1, int(distance_km) + 1):
        t = _time_at_km(series, float(km))
        if t is None:
            break
        splits.append(_fmt_mmss(t - prev_t))
        prev_t = t
    return splits or None


def derive_hr(samples: list[LiveSample]) -> tuple[int | None, int | None]:
    """(avg, max) bpm from the sampled series, or (None, None)."""
    values = [s.hr for s in samples if s.hr and s.hr > 0]
    if not values:
        return None, None
    return round(sum(values) / len(values)), max(values)
