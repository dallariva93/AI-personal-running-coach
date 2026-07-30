"""Historical weather for a run, from Open-Meteo.

Garmin only records temperature when the watch has a sensor for it (or when
Garmin Connect happened to attach weather), so the field arrives empty for most
activities. That matters: at 32 °C the same perceived effort comes out 10-15
seconds per kilometre slower, and without the temperature a coach reads heat as
a loss of form.

Open-Meteo needs no API key and no account, which keeps the zero-cost
constraint intact. Two endpoints cover the whole timeline:

* the **archive** reanalysis, authoritative but lagging a few days;
* the **forecast** endpoint with ``past_days``, which covers the recent gap.

Everything here is best-effort by design: weather is a nice-to-have signal, so
a timeout, a rate limit or an outage must leave the activity untouched rather
than fail an ingest.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from app.logging_config import get_logger

logger = get_logger("app.collection.weather")

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# The archive reanalysis trails real time; inside this window the forecast
# endpoint's `past_days` is the one that actually has the hours.
_ARCHIVE_LAG_DAYS = 6
_FORECAST_MAX_PAST_DAYS = 92
TIMEOUT_S = 10.0

_HOURLY = "temperature_2m,relative_humidity_2m"


def start_coordinates(route_polyline: Any) -> tuple[float, float] | None:
    """Where the run began, from the stored ``[[lat, lon], ...]`` track.

    The first point is the start line — which is what the weather should be
    sampled at, not the middle of a route that may cross a valley. The column
    holds JSON text, so a string is accepted as well as an already-parsed list.
    """
    if isinstance(route_polyline, str):
        try:
            route_polyline = json.loads(route_polyline)
        except (ValueError, TypeError):
            return None
    if not isinstance(route_polyline, list) or not route_polyline:
        return None
    first = route_polyline[0]
    if not isinstance(first, (list, tuple)) or len(first) < 2:
        return None
    try:
        lat, lon = float(first[0]), float(first[1])
    except (TypeError, ValueError):
        return None
    # Reject the null island and anything off-planet: a bad fix must not be
    # turned into a confident weather reading.
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        return None
    if lat == 0.0 and lon == 0.0:
        return None
    return lat, lon


def _hour_index(start_time: str | None) -> int:
    """Hour of day the run started; noon when unknown (least-wrong default)."""
    if not start_time:
        return 12
    try:
        return max(0, min(23, int(str(start_time).split(":")[0])))
    except (ValueError, IndexError):
        return 12


def _pick_hour(payload: dict, day: str, hour: int) -> dict[str, float] | None:
    """Read the run's hour out of Open-Meteo's flat hourly arrays."""
    hourly = payload.get("hourly") if isinstance(payload, dict) else None
    if not isinstance(hourly, dict):
        return None
    times = hourly.get("time")
    if not isinstance(times, list):
        return None
    wanted = f"{day}T{hour:02d}:00"
    try:
        index = times.index(wanted)
    except ValueError:
        return None

    out: dict[str, float] = {}
    temps = hourly.get("temperature_2m")
    if isinstance(temps, list) and index < len(temps) and temps[index] is not None:
        out["temperature_c"] = round(float(temps[index]), 1)
    humidity = hourly.get("relative_humidity_2m")
    if isinstance(humidity, list) and index < len(humidity) and humidity[index] is not None:
        out["humidity_pct"] = round(float(humidity[index]))
    return out or None


def _default_fetch(url: str, params: dict[str, Any]) -> dict | None:
    """Same HTTP library as the forecast client in ``app/services/weather.py``."""
    import requests

    response = requests.get(url, params=params, timeout=TIMEOUT_S)
    response.raise_for_status()
    return response.json()


def fetch_weather(
    lat: float,
    lon: float,
    day: str,
    start_time: str | None = None,
    *,
    ref: date | None = None,
    fetch: Any = None,
) -> dict[str, float] | None:
    """Temperature and humidity at the run's start, or ``None``.

    ``fetch`` is injectable so the tests never touch the network. Returns a
    dict with ``temperature_c`` and/or ``humidity_pct``.
    """
    fetch = fetch or _default_fetch
    try:
        run_day = date.fromisoformat(day)
    except (TypeError, ValueError):
        return None
    ref = ref or date.today()
    if run_day > ref:
        return None  # no weather for a run that has not happened
    age_days = (ref - run_day).days
    if age_days > 365 * 20:
        return None

    hour = _hour_index(start_time)
    base = {
        "latitude": round(lat, 4),
        "longitude": round(lon, 4),
        "hourly": _HOURLY,
        "timezone": "auto",
    }
    if age_days <= _ARCHIVE_LAG_DAYS:
        url = FORECAST_URL
        params = {**base, "past_days": min(max(age_days + 1, 1), _FORECAST_MAX_PAST_DAYS),
                  "forecast_days": 1}
    else:
        url = ARCHIVE_URL
        params = {**base, "start_date": day, "end_date": day}

    try:
        payload = fetch(url, params)
    except Exception as exc:  # noqa: BLE001 - a missing nice-to-have is not an error
        logger.warning("Open-Meteo non raggiungibile per %s: %s", day, exc)
        return None
    if not isinstance(payload, dict):
        return None
    return _pick_hour(payload, day, hour)
