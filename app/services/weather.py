"""Weather-window optimizer (Roadmap Q6).

Turns a day's hourly forecast into a single actionable suggestion — "corri alle
07:00: 14°C, poca pioggia" — delivered once a day as a low-priority coach
notification. The scoring is a pure function (``best_window``) over normalised
hourly points; the network client (open-meteo, no API key) is thin and
injectable so the whole thing is testable without touching the network.
"""

from __future__ import annotations

import json as _json
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Activity, CoachEvent
from app.logging_config import get_logger
from app.services.event_service import log_event

logger = get_logger("app.services.weather")

# Daylight-ish window we ever suggest running in (local hours, inclusive).
_HOUR_MIN = 6
_HOUR_MAX = 21


@dataclass
class HourForecast:
    """One normalised hourly point (local time)."""

    hour: int
    temp_c: float
    precip_prob: float = 0.0     # %
    wind_kmh: float = 0.0
    apparent_c: float | None = None  # feels-like, for humidity/afa penalty


@dataclass
class WeatherPrefs:
    """Athlete preferences for scoring hours."""

    ideal_low: float = 8.0
    ideal_high: float = 16.0
    habitual_hours: Sequence[int] = field(default_factory=tuple)


@dataclass
class BestWindow:
    """The recommended hour to run, with a human-readable summary."""

    hour: int
    time_label: str    # "07:00"
    temp_c: float
    score: float
    summary: str


def _hour_score(h: HourForecast, prefs: WeatherPrefs) -> float:
    """0-100-ish desirability of running at this hour (higher = better)."""
    score = 100.0
    # Temperature outside the ideal band.
    if h.temp_c < prefs.ideal_low:
        score -= (prefs.ideal_low - h.temp_c) * 4.0
    elif h.temp_c > prefs.ideal_high:
        score -= (h.temp_c - prefs.ideal_high) * 4.0
    # Rain probability dominates: a dry hour should beat a nicer-temp wet one.
    score -= h.precip_prob * 0.8
    # Wind above a comfortable ~20 km/h.
    if h.wind_kmh > 20.0:
        score -= (h.wind_kmh - 20.0) * 1.5
    # Humidity / afa when it's already warm (feels-like above actual).
    if h.apparent_c is not None and h.temp_c > prefs.ideal_high:
        score -= max(0.0, h.apparent_c - h.temp_c) * 2.0
    # Small nudge towards the athlete's habitual hours.
    if h.hour in prefs.habitual_hours:
        score += 8.0
    return score


def best_window(
    hours: Sequence[HourForecast], prefs: WeatherPrefs | None = None
) -> BestWindow | None:
    """Pick the best hour to run from an hourly forecast (pure).

    Considers only the ``06:00``-``21:00`` window; ties break to the earliest
    hour. Returns None when there is nothing to score.
    """
    prefs = prefs or WeatherPrefs()
    candidates = [h for h in hours if _HOUR_MIN <= h.hour <= _HOUR_MAX]
    if not candidates:
        return None
    # max score, earliest hour on ties.
    best = max(candidates, key=lambda h: (_hour_score(h, prefs), -h.hour))
    score = _hour_score(best, prefs)

    bits = [f"{best.temp_c:.0f}°C"]
    if best.precip_prob >= 40:
        bits.append(f"pioggia {best.precip_prob:.0f}%")
    elif best.precip_prob <= 15:
        bits.append("poca pioggia")
    if best.wind_kmh > 20:
        bits.append(f"vento {best.wind_kmh:.0f} km/h")
    label = f"{best.hour:02d}:00"
    summary = f"Corri alle {label}: " + ", ".join(bits)
    return BestWindow(
        hour=best.hour, time_label=label, temp_c=best.temp_c, score=round(score, 1),
        summary=summary,
    )


class WeatherClient:
    """Thin open-meteo client (no API key). Injectable for tests."""

    _URL = "https://api.open-meteo.com/v1/forecast"

    def __init__(self, session: requests.Session | None = None, timeout: int = 10) -> None:
        self._http = session or requests.Session()
        self._timeout = timeout

    def fetch_hourly(self, lat: float, lon: float, day: date) -> list[HourForecast]:
        hourly = (
            "temperature_2m,precipitation_probability,"
            "wind_speed_10m,apparent_temperature"
        )
        params = {
            "latitude": lat,
            "longitude": lon,
            "hourly": hourly,
            "timezone": "auto",
            "start_date": day.isoformat(),
            "end_date": day.isoformat(),
        }
        resp = self._http.get(self._URL, params=params, timeout=self._timeout)
        resp.raise_for_status()
        return parse_open_meteo(resp.json())


def parse_open_meteo(payload: dict) -> list[HourForecast]:
    """Normalise an open-meteo ``forecast`` response into hourly points (pure)."""
    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []
    temps = hourly.get("temperature_2m") or []
    precip = hourly.get("precipitation_probability") or []
    wind = hourly.get("wind_speed_10m") or []
    apparent = hourly.get("apparent_temperature") or []
    out: list[HourForecast] = []
    for i, t in enumerate(times):
        # t like "2026-06-24T07:00"
        try:
            hour = int(str(t)[11:13])
            temp = float(temps[i])
        except (ValueError, IndexError, TypeError):
            continue
        out.append(
            HourForecast(
                hour=hour,
                temp_c=temp,
                precip_prob=float(precip[i]) if i < len(precip) and precip[i] is not None else 0.0,
                wind_kmh=float(wind[i]) if i < len(wind) and wind[i] is not None else 0.0,
                apparent_c=(
                    float(apparent[i]) if i < len(apparent) and apparent[i] is not None else None
                ),
            )
        )
    return out


def _resolve_location(db: Session) -> tuple[float, float] | None:
    """Home lat/lon: explicit settings first, else the last GPS run's start."""
    s = get_settings()
    if s.home_lat is not None and s.home_lon is not None:
        return (s.home_lat, s.home_lon)
    row = db.scalar(
        select(Activity)
        .where(Activity.sport == "run", Activity.route_polyline.isnot(None))
        .order_by(Activity.date.desc())
        .limit(1)
    )
    if row is None or not row.route_polyline:
        return None
    try:
        pts = _json.loads(row.route_polyline)
        lat, lon = float(pts[0][0]), float(pts[0][1])
        return (lat, lon)
    except (ValueError, IndexError, TypeError, KeyError):
        return None


def _habitual_hours(db: Session, limit: int = 40) -> tuple[int, ...]:
    """The 1-2 most common start hours across recent runs (empty until data)."""
    rows = db.scalars(
        select(Activity.start_time)
        .where(Activity.sport == "run", Activity.start_time.isnot(None))
        .order_by(Activity.date.desc())
        .limit(limit)
    ).all()
    counts: dict[int, int] = {}
    for hhmm in rows:
        try:
            counts[int(str(hhmm)[:2])] = counts.get(int(str(hhmm)[:2]), 0) + 1
        except (ValueError, TypeError):
            continue
    if not counts:
        return ()
    top = sorted(counts, key=lambda h: counts[h], reverse=True)[:2]
    return tuple(top)


def maybe_suggest_weather_window(
    db: Session,
    decision_type: str,
    ref: date | None = None,
    client: WeatherClient | None = None,
) -> CoachEvent | None:
    """Create at most one weather-window suggestion per day (Q6).

    Best-effort and side-effect-light: skips on a rest day, skips if today's
    suggestion already exists (no network call then), and swallows any network
    error. Disabled unless ``weather_enabled`` — except when a ``client`` is
    injected (tests), which bypasses the gate and never touches the network.
    """
    ref = ref or date.today()
    if decision_type == "rest":
        return None
    if client is None and not get_settings().weather_enabled:
        return None

    dedupe = f"weather:{ref.isoformat()}"
    if db.scalar(select(CoachEvent).where(CoachEvent.dedupe_key == dedupe)) is not None:
        return None  # already suggested today — never re-fetch

    location = _resolve_location(db)
    if location is None:
        return None

    client = client or WeatherClient()
    try:
        hours = client.fetch_hourly(location[0], location[1], ref)
    except Exception as exc:  # noqa: BLE001 - weather is best-effort
        logger.info("Weather fetch skipped: %s", exc)
        return None

    window = best_window(hours, WeatherPrefs(habitual_hours=_habitual_hours(db)))
    if window is None:
        return None

    return log_event(
        db,
        date_str=ref.isoformat(),
        event_type="weather",
        title=f"Finestra meteo: {window.time_label}",
        detail=window.summary,
        notifiable=True,
        priority="low",
        dedupe_key=dedupe,
    )
