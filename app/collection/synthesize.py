"""Turn a raw Garmin activity dict into a compact :class:`RunSummary`.

Garmin returns a large, second-by-second-capable payload. For the LLM (and for
storage) we keep only what is informative and cheap in tokens. All field access
is defensive because the unofficial API changes shape over time.
"""

from __future__ import annotations

from typing import Any

from app.schemas import RunSummary

# Map common Garmin run subtypes / names to our coarse activity taxonomy.
_TYPE_HINTS = {
    "tempo": "tempo",
    "threshold": "tempo",
    "interval": "intervalli",
    "repeat": "intervalli",
    "speed": "intervalli",
    "long": "lungo",
    "lungo": "lungo",
    "recovery": "recupero",
    "recupero": "recupero",
    "race": "gara",
    "gara": "gara",
    "easy": "easy",
}


def _num(value: Any) -> float | None:
    """Best-effort float parse (Garmin fields are inconsistently typed)."""
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _format_pace(distance_m: float, duration_s: float) -> str | None:
    """Return average pace as ``M:SS/km`` from distance (m) and duration (s)."""
    if not distance_m or not duration_s:
        return None
    pace_s_per_km = duration_s / (distance_m / 1000.0)
    minutes = int(pace_s_per_km // 60)
    seconds = int(round(pace_s_per_km % 60))
    if seconds == 60:
        minutes += 1
        seconds = 0
    return f"{minutes}:{seconds:02d}/km"


def _infer_type(activity: dict[str, Any]) -> str:
    """Best-effort classification of the workout type from Garmin metadata."""
    haystack = " ".join(
        str(activity.get(k, "")).lower()
        for k in ("activityName", "activityType", "trainingEffectLabel")
    )
    type_field = activity.get("activityType")
    if isinstance(type_field, dict):
        haystack += " " + str(type_field.get("typeKey", "")).lower()
    for hint, label in _TYPE_HINTS.items():
        if hint in haystack:
            return label
    return "easy"


def _extract_hr_zones(activity: dict[str, Any]) -> dict[str, float] | None:
    """Pull per-zone time (minutes) if Garmin provided it."""
    zones = activity.get("hrTimeInZones") or activity.get("timeInZones")
    if not isinstance(zones, dict):
        return None
    out: dict[str, float] = {}
    for key, value in zones.items():
        try:
            out[str(key).lower().replace("zone", "z")] = round(float(value) / 60.0, 1)
        except (TypeError, ValueError):
            continue
    return out or None


def synthesize(activity: dict[str, Any]) -> RunSummary:
    """Map a raw Garmin activity dict onto the compact schema."""
    distance_m = float(activity.get("distance") or 0.0)
    duration_s = float(activity.get("duration") or activity.get("movingDuration") or 0.0)

    return RunSummary(
        garmin_activity_id=(
            str(activity["activityId"]) if activity.get("activityId") is not None else None
        ),
        date=str(activity.get("startTimeLocal", ""))[:10],
        activity_type=_infer_type(activity),
        duration_min=round(duration_s / 60.0, 1),
        distance_km=round(distance_m / 1000.0, 2),
        avg_pace=_format_pace(distance_m, duration_s),
        avg_hr=int(activity["averageHR"]) if activity.get("averageHR") else None,
        max_hr=int(activity["maxHR"]) if activity.get("maxHR") else None,
        elevation_gain_m=(
            round(float(activity["elevationGain"]), 0) if activity.get("elevationGain") else None
        ),
        avg_cadence=(
            int(activity["averageRunningCadenceInStepsPerMinute"])
            if activity.get("averageRunningCadenceInStepsPerMinute")
            else None
        ),
        hr_zones=_extract_hr_zones(activity),
        splits_km=None,
        rpe=None,
        notes=None,
        temperature_c=_num(activity.get("temperature") or activity.get("avgTemperature")),
        humidity_pct=_num(activity.get("humidity")),
        elevation_loss_m=(
            round(float(activity["elevationLoss"]), 0) if activity.get("elevationLoss") else None
        ),
    )
