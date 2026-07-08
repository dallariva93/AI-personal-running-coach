"""Pure extraction of Garmin's native daily wellness values (phase 0c).

Where :mod:`app.services.ingest_wellness` maps Garmin data onto the subjective
1-10 check-in scale, this module keeps the *native* Garmin numbers (sleep time,
overnight HRV, resting HR, body-battery flow, stress average, training
readiness) so the live metrics Garmin may stop exposing over time
(docs/GARMIN_DATA_PLAN.md A3) are captured verbatim.

Tolerant by design (A11): each Garmin payload shape varies by API version and
device, so an unexpected or missing structure yields ``None`` for that field
rather than raising. One malformed endpoint never invalidates the others.
"""

from __future__ import annotations

from typing import Any

from app.schemas import DailyWellnessSnapshot


def _as_int(value: Any, *, minimum: int | None = None) -> int | None:
    """Coerce a numeric value to int, rejecting bools and out-of-range values."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    if minimum is not None and value < minimum:
        return None
    return int(value)


def _extract_sleep(raw: Any) -> tuple[int | None, int | None]:
    """(sleep_seconds, sleep_score) from ``get_sleep_data``."""
    if not isinstance(raw, dict):
        return None, None
    dto = raw.get("dailySleepDTO")
    if not isinstance(dto, dict):
        return None, None
    seconds = _as_int(dto.get("sleepTimeSeconds"), minimum=1)
    score = None
    scores = dto.get("sleepScores")
    if isinstance(scores, dict):
        overall = scores.get("overall")
        if isinstance(overall, dict):
            score = _as_int(overall.get("value"))
    return seconds, score


def _extract_hrv(raw: Any) -> tuple[float | None, str | None]:
    """(overnight_avg_ms, status) from ``get_hrv_data``.

    Prefers Garmin's own ``hrvSummary.lastNightAvg``; falls back to averaging
    the per-reading ``rmssd`` of ``hrv.lastNight`` when the summary is absent.
    """
    if not isinstance(raw, dict):
        return None, None
    avg: float | None = None
    status: str | None = None
    summary = raw.get("hrvSummary")
    if isinstance(summary, dict):
        v = summary.get("lastNightAvg")
        if not isinstance(v, bool) and isinstance(v, int | float):
            avg = float(v)
        s = summary.get("status")
        if isinstance(s, str):
            status = s
    if avg is None:
        inner = raw.get("hrv") if isinstance(raw.get("hrv"), dict) else raw
        last_night = inner.get("lastNight") if isinstance(inner, dict) else None
        if isinstance(last_night, list):
            vals = [
                x["rmssd"]
                for x in last_night
                if isinstance(x, dict)
                and not isinstance(x.get("rmssd"), bool)
                and isinstance(x.get("rmssd"), int | float)
            ]
            if vals:
                avg = round(sum(vals) / len(vals), 1)
    return avg, status


def _extract_stress(raw: Any) -> int | None:
    """Daily average stress (0-100) from ``get_stress_data``.

    Garmin returns negative sentinels (-1/-2) when no reading exists; those map
    to ``None``.
    """
    if not isinstance(raw, dict):
        return None
    value = raw.get("avgStressLevel")
    if value is None:
        value = raw.get("averageStressLevel")
    return _as_int(value, minimum=0)


def _extract_body_battery(raw: Any) -> tuple[int | None, int | None]:
    """(charged, drained) points from ``get_body_battery``.

    Garmin returns a list of per-day dicts; we read the first one. The
    intraday curve is intentionally not captured here (deferred to a later
    phase, A1): only the day's net charge/drain, which are stable keys.
    """
    if not isinstance(raw, list | dict):
        return None, None
    items = raw if isinstance(raw, list) else [raw]
    day = next((x for x in items if isinstance(x, dict)), None)
    if day is None:
        return None, None
    return _as_int(day.get("charged")), _as_int(day.get("drained"))


def _extract_resting_hr(raw: Any) -> int | None:
    """Resting heart rate (bpm) from ``get_rhr_day``.

    Newer payloads nest it under ``allMetrics.metricsMap`` keyed by
    ``WELLNESS_RESTING_HEART_RATE``; older ones expose a flat
    ``restingHeartRate``. Both are handled.
    """
    if not isinstance(raw, dict):
        return None
    metrics = raw.get("allMetrics")
    if isinstance(metrics, dict):
        mmap = metrics.get("metricsMap")
        if isinstance(mmap, dict):
            series = mmap.get("WELLNESS_RESTING_HEART_RATE")
            if isinstance(series, list):
                for point in series:
                    if isinstance(point, dict):
                        value = _as_int(point.get("value"), minimum=1)
                        if value is not None:
                            return value
    return _as_int(raw.get("restingHeartRate"), minimum=1)


def _extract_training_readiness(raw: Any) -> tuple[int | None, str | None]:
    """(score, level) from ``get_training_readiness``.

    The endpoint returns a list of per-day dicts (occasionally a bare dict);
    we read the first mapping's ``score`` and ``level``.
    """
    if not isinstance(raw, list | dict):
        return None, None
    items = raw if isinstance(raw, list) else [raw]
    day = next((x for x in items if isinstance(x, dict)), None)
    if day is None:
        return None, None
    score = _as_int(day.get("score"))
    level = day.get("level") if isinstance(day.get("level"), str) else None
    return score, level


def build_wellness_snapshot(
    date_str: str,
    *,
    sleep: Any = None,
    hrv: Any = None,
    stress: Any = None,
    body_battery: Any = None,
    resting_hr: Any = None,
    training_readiness: Any = None,
) -> DailyWellnessSnapshot:
    """Assemble a :class:`DailyWellnessSnapshot` from raw Garmin payloads.

    Each argument is the raw response of the matching Garmin endpoint (or
    ``None`` if it failed/was skipped). Pure: no I/O, tolerant to any shape.
    """
    sleep_seconds, sleep_score = _extract_sleep(sleep)
    hrv_avg, hrv_status = _extract_hrv(hrv)
    bb_charged, bb_drained = _extract_body_battery(body_battery)
    readiness_score, readiness_level = _extract_training_readiness(training_readiness)
    return DailyWellnessSnapshot(
        date=date_str,
        sleep_seconds=sleep_seconds,
        sleep_score=sleep_score,
        hrv_last_night_avg=hrv_avg,
        hrv_status=hrv_status,
        resting_hr=_extract_resting_hr(resting_hr),
        body_battery_charged=bb_charged,
        body_battery_drained=bb_drained,
        stress_avg=_extract_stress(stress),
        training_readiness_score=readiness_score,
        training_readiness_level=readiness_level,
    )
