"""Hourly forecast for Padova, judged for the athlete's running windows.

Feeds the scheduled "allenamento di oggi e domani" task with weather that is
already dated, hourly and evaluated, so the agent never has to read a weather
web page and guess which hour a figure belongs to.

Two functions with one job each: :func:`fetch_hourly` does the HTTP and
nothing else, :func:`evaluate` is pure and takes ``now`` as a parameter, so
every rule below is testable without a network or a clock.

The one convention that is easy to get wrong: Open-Meteo reports
``precipitation`` (and ``precipitation_probability``) at timestamp ``T`` for the
hour *before* it, ``T-1 → T``. A window 18:00–21:00 is therefore judged on the
timestamps 19:00, 20:00 and 21:00 — rain at 18:00 fell between 17 and 18 and
does not touch the run.

Separate from :mod:`app.collection.weather`, which is the *historical* weather
attached to runs already done.
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from app.logging_config import get_logger

logger = get_logger("app.collection.run_windows")

# ── configuration ────────────────────────────────────────────────────────────

LOCATION = "Padova"
LAT, LON = 45.4064, 11.8768
TZ = "Europe/Rome"
WINDOWS = {
    "evening": (18, 21),  # tutti i giorni
    "morning_weekday": (8, 10),  # lun–sab
    "morning_sunday": (7, 9),  # domenica
}
DRY_MAX_MM = 0.1  # sotto questa soglia l'ora è asciutta
DRY_MAX_PROB = 30  # % massima per dire "asciutta"
WET_MIN_PROB = 60  # % da cui si dice "pioggia" anche con 0 mm
STRONG_GUST_KMH = 40

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
HOURLY_VARS = (
    "temperature_2m,precipitation,precipitation_probability,"
    "wind_speed_10m,wind_gusts_10m,weather_code"
)
TIMEOUT_S = 10.0
RETRIES = 1
MAX_SPAN_DAYS = 4  # inclusive: oggi + i 3 giorni successivi

# Hours shown in the day's `hourly` list and scanned for `dry_slots`: only the
# part of the day anyone runs in, to keep the payload small.
_DAY_FIRST_HOUR, _DAY_LAST_HOUR = 6, 22

_WEEKDAYS_IT = ("lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica")


class RunWindowsError(Exception):
    """The forecast could not be fetched or read."""


# ── HTTP ─────────────────────────────────────────────────────────────────────


def _default_get(url: str, params: dict[str, Any], timeout: float) -> Any:
    import requests

    response = requests.get(url, params=params, timeout=timeout)
    if response.status_code >= 400:
        # Open-Meteo explains a 400 in the body ({"reason": ...}); keep it.
        try:
            reason = response.json().get("reason")
        except ValueError:
            reason = None
        raise RunWindowsError(f"HTTP {response.status_code}" + (f": {reason}" if reason else ""))
    try:
        return response.json()
    except ValueError as exc:
        raise RunWindowsError("risposta non in JSON") from exc


def _short(exc: Exception) -> str:
    """A network failure in a few words.

    ``requests`` puts the full URL and the whole exception chain in its
    messages; the agent only needs to know the forecast is unavailable and
    roughly why.
    """
    name = exc.__class__.__name__.lower()
    if "timeout" in name:
        return f"timeout dopo {TIMEOUT_S:g} s"
    if "connection" in name or "proxy" in name:
        return "Open-Meteo non raggiungibile"
    return exc.__class__.__name__


def fetch_hourly(date_from: str, date_to: str, *, get: Any = None) -> dict:
    """The raw hourly forecast for Padova, local time. HTTP only, no judgement.

    One retry on failure, then :class:`RunWindowsError`.
    """
    get = get or _default_get
    params = {
        "latitude": LAT,
        "longitude": LON,
        "hourly": HOURLY_VARS,
        "timezone": TZ,
        "start_date": date_from,
        "end_date": date_to,
    }
    last: Exception | None = None
    for attempt in range(RETRIES + 1):
        try:
            payload = get(FORECAST_URL, params, TIMEOUT_S)
        except RunWindowsError as exc:
            last = exc
        except Exception as exc:  # noqa: BLE001 - network errors of any library
            last = RunWindowsError(_short(exc))
        else:
            if not isinstance(payload, dict):
                raise RunWindowsError("risposta inattesa da Open-Meteo")
            return payload
        logger.warning("Open-Meteo tentativo %d fallito: %s", attempt + 1, last)
    raise last or RunWindowsError("Open-Meteo non raggiungibile")


# ── evaluation (pure) ────────────────────────────────────────────────────────


def _hours_by_day(raw: dict) -> dict[date, dict[int, dict[str, Any]]]:
    hourly = raw.get("hourly") if isinstance(raw, dict) else None
    if not isinstance(hourly, dict) or not isinstance(hourly.get("time"), list):
        raise RunWindowsError("dati orari mancanti nella risposta")
    times = hourly["time"]

    def column(name: str) -> list:
        values = hourly.get(name)
        if values is None:
            return [None] * len(times)
        if not isinstance(values, list) or len(values) != len(times):
            raise RunWindowsError(f"colonna {name} incoerente con gli orari")
        return values

    mm, prob = column("precipitation"), column("precipitation_probability")
    temp, gust = column("temperature_2m"), column("wind_gusts_10m")

    days: dict[date, dict[int, dict[str, Any]]] = {}
    for i, stamp in enumerate(times):
        try:
            moment = datetime.fromisoformat(str(stamp))
        except ValueError as exc:
            raise RunWindowsError(f"orario non valido: {stamp}") from exc
        days.setdefault(moment.date(), {})[moment.hour] = {
            "mm": mm[i],
            "prob": prob[i],
            "temp": temp[i],
            "gust": gust[i],
        }
    return days


def _is_dry(mm: Any, prob: Any) -> bool:
    """One hour, or a window's maxima: dry only when both figures say so.

    A missing figure is not evidence of a dry hour.
    """
    return mm is not None and prob is not None and mm < DRY_MAX_MM and prob < DRY_MAX_PROB


def _status(max_mm: Any, max_prob: Any) -> str:
    if _is_dry(max_mm, max_prob):
        return "dry"
    if (max_mm is not None and max_mm >= DRY_MAX_MM) or (
        max_prob is not None and max_prob >= WET_MIN_PROB
    ):
        return "wet"
    return "uncertain"


def _max(values: list[Any]) -> Any:
    present = [v for v in values if v is not None]
    return max(present) if present else None


def _window(
    day: date, hours: dict[int, dict[str, Any]], span: tuple[int, int], now: datetime
) -> dict[str, Any]:
    start, end = span
    # Precipitation at timestamp h is the hour before it: the window
    # (start, end] is covered by the timestamps start+1 .. end.
    rows = [hours[h] for h in range(start + 1, end + 1) if h in hours]
    max_mm = _max([r["mm"] for r in rows])
    max_prob = _max([r["prob"] for r in rows])
    max_gust = _max([r["gust"] for r in rows])
    ends_at = datetime.combine(day, time(end), tzinfo=now.tzinfo)
    return {
        "from": f"{start:02d}:00",
        "to": f"{end:02d}:00",
        "status": _status(max_mm, max_prob),
        "max_mm": max_mm,
        "max_prob": max_prob,
        "max_gust_kmh": round(max_gust) if max_gust is not None else None,
        "strong_wind": max_gust is not None and max_gust >= STRONG_GUST_KMH,
        "passed": now >= ends_at,
    }


def _dry_slots(hours: dict[int, dict[str, Any]]) -> list[str]:
    """Runs of consecutive dry hours between 06:00 and 22:00.

    Timestamp h covers h-1 → h, so the hours inside 06:00–22:00 are the
    timestamps 07..22, and a run of dry timestamps a..b is the slot (a-1)–b.
    """
    slots: list[str] = []
    run_start: int | None = None
    for h in range(_DAY_FIRST_HOUR + 1, _DAY_LAST_HOUR + 2):
        row = hours.get(h) if h <= _DAY_LAST_HOUR else None
        dry = row is not None and _is_dry(row["mm"], row["prob"])
        if dry and run_start is None:
            run_start = h
        elif not dry and run_start is not None:
            slots.append(f"{run_start - 1:02d}:00-{h - 1:02d}:00")
            run_start = None
    return slots


def evaluate(raw: dict, now: datetime) -> dict:
    """Judge every day in ``raw`` for the running windows. Pure: no I/O.

    ``now`` decides which windows have already passed; a naive datetime is read
    as Europe/Rome. Malformed input returns ``{"error": ...}`` rather than
    raising, like the tool that calls it.
    """
    tz = ZoneInfo(TZ)
    now = now.replace(tzinfo=tz) if now.tzinfo is None else now.astimezone(tz)
    try:
        by_day = _hours_by_day(raw)
    except RunWindowsError as exc:
        return {"error": str(exc)}

    days: list[dict[str, Any]] = []
    for day in sorted(by_day):
        hours = by_day[day]
        evening = _window(day, hours, WINDOWS["evening"], now)
        morning_span = WINDOWS["morning_sunday" if day.weekday() == 6 else "morning_weekday"]
        morning = _window(day, hours, morning_span, now)

        # Preference order: the evening on weekdays, the morning on Sunday.
        order = ("morning", "evening") if day.weekday() == 6 else ("evening", "morning")
        windows = {"evening": evening, "morning": morning}
        best = next(
            (
                name
                for name in order
                if not windows[name]["passed"] and windows[name]["status"] == "dry"
            ),
            "none",
        )

        temps = [r["temp"] for r in hours.values() if r["temp"] is not None]
        days.append(
            {
                "date": day.isoformat(),
                "weekday": _WEEKDAYS_IT[day.weekday()],
                "evening": evening,
                "morning": morning,
                "best": best,
                "dry_slots": _dry_slots(hours),
                "temp_min": round(min(temps), 1) if temps else None,
                "temp_max": round(max(temps), 1) if temps else None,
                "hourly": [
                    {
                        "time": f"{h:02d}:00",
                        "mm": hours[h]["mm"],
                        "prob": hours[h]["prob"],
                        "temp": hours[h]["temp"],
                        "gust": round(hours[h]["gust"]) if hours[h]["gust"] is not None else None,
                    }
                    for h in range(_DAY_FIRST_HOUR, _DAY_LAST_HOUR + 1)
                    if h in hours
                ],
            }
        )

    return {
        "location": LOCATION,
        "source": "open-meteo",
        "fetched_at": now.isoformat(timespec="seconds"),
        "days": days,
    }


def run_windows(date_from: str, date_to: str, *, now: datetime | None = None,
                get: Any = None) -> dict:
    """Validate, fetch and evaluate. Never raises: errors become ``{"error"}``.

    So the agent writes "meteo non verificabile" instead of failing the task.
    """
    try:
        start, end = date.fromisoformat(date_from), date.fromisoformat(date_to)
    except (TypeError, ValueError):
        return {"error": "date non valide: usa YYYY-MM-DD"}
    if end < start:
        return {"error": "date_to precede date_from"}
    if (end - start).days + 1 > MAX_SPAN_DAYS:
        return {"error": f"intervallo troppo lungo: al massimo {MAX_SPAN_DAYS} giorni"}

    try:
        raw = fetch_hourly(start.isoformat(), end.isoformat(), get=get)
    except RunWindowsError as exc:
        return {"error": f"meteo non disponibile: {exc}"}
    except Exception as exc:  # noqa: BLE001 - the tool must never raise
        return {"error": f"meteo non disponibile: {exc}"}
    return evaluate(raw, now or datetime.now(ZoneInfo(TZ)))
