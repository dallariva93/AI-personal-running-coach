"""Weather lookup for past runs (Open-Meteo).

Garmin leaves ``temperature_c`` empty on most activities, which makes August
read as a loss of form. These tests pin two things: the weather is sampled at
the run's own start point and hour, and a weather outage never costs anything
the app already had.

The network is never touched — the fetch function is injected.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from app.collection.weather import (
    ARCHIVE_URL,
    FORECAST_URL,
    fetch_weather,
    start_coordinates,
)
from app.db.models import Activity
from app.services.weather_backfill import fill_missing_weather

TODAY = date.today()
MILAN = [[45.4642, 9.1900], [45.4650, 9.1910]]


def _hourly_payload(day: str, temps: dict[int, float], humidity: float = 60.0) -> dict:
    """Open-Meteo's flat hourly arrays for one day."""
    times = [f"{day}T{h:02d}:00" for h in range(24)]
    return {
        "hourly": {
            "time": times,
            "temperature_2m": [temps.get(h) for h in range(24)],
            "relative_humidity_2m": [humidity] * 24,
        }
    }


def _recorder(payload: dict):
    """A fetch double that records the calls it received.

    Open-Meteo answers for the date it was asked about, so the double does the
    same: it retimes the canned hourly arrays onto the requested day. A double
    that always replied about one fixed date would make every other run look
    like "no data available".
    """
    calls: list[tuple[str, dict]] = []

    def _fetch(url: str, params: dict):
        calls.append((url, params))
        if not isinstance(payload, dict) or "hourly" not in payload:
            return payload
        hourly = payload["hourly"]
        times = hourly.get("time")
        if not isinstance(times, list) or not times:
            return payload
        asked = params.get("start_date") or str(times[0])[:10]
        return {
            **payload,
            "hourly": {**hourly, "time": [f"{asked}T{h:02d}:00" for h in range(24)]},
        }

    return _fetch, calls


# --------------------------------------------------------------------------
# start position
# --------------------------------------------------------------------------
def test_startCoordinates_takesTheFirstPointOfTheTrack():
    assert start_coordinates(json.dumps(MILAN)) == (45.4642, 9.1900)
    assert start_coordinates(MILAN) == (45.4642, 9.1900)


def test_startCoordinates_rejectsUnusableTracks():
    """A bad GPS fix must not become a confident weather reading."""
    assert start_coordinates(None) is None
    assert start_coordinates("[]") is None
    assert start_coordinates("non-json") is None
    assert start_coordinates([[0.0, 0.0]]) is None          # null island
    assert start_coordinates([[91.0, 9.0]]) is None         # off-planet
    assert start_coordinates([["a", "b"]]) is None


# --------------------------------------------------------------------------
# the lookup itself
# --------------------------------------------------------------------------
def test_fetchWeather_readsTheHourTheRunStarted():
    day = (TODAY - timedelta(days=30)).isoformat()
    fetch, calls = _recorder(_hourly_payload(day, {7: 18.5, 12: 31.2}))

    morning = fetch_weather(45.46, 9.19, day, "07:30", ref=TODAY, fetch=fetch)
    noon = fetch_weather(45.46, 9.19, day, "12:15", ref=TODAY, fetch=fetch)

    assert morning["temperature_c"] == 18.5
    assert noon["temperature_c"] == 31.2
    assert morning["humidity_pct"] == 60


def test_fetchWeather_unknownStartTime_fallsBackToMidday():
    day = (TODAY - timedelta(days=30)).isoformat()
    fetch, _ = _recorder(_hourly_payload(day, {12: 25.0}))

    assert fetch_weather(45.46, 9.19, day, None, ref=TODAY, fetch=fetch)["temperature_c"] == 25.0


def test_fetchWeather_oldRun_usesTheArchiveEndpoint():
    day = (TODAY - timedelta(days=200)).isoformat()
    fetch, calls = _recorder(_hourly_payload(day, {9: 12.0}))

    fetch_weather(45.46, 9.19, day, "09:00", ref=TODAY, fetch=fetch)

    url, params = calls[0]
    assert url == ARCHIVE_URL
    assert params["start_date"] == day and params["end_date"] == day


def test_fetchWeather_recentRun_usesTheForecastEndpoint():
    """The archive reanalysis lags a few days; the recent gap needs past_days."""
    day = (TODAY - timedelta(days=2)).isoformat()
    fetch, calls = _recorder(_hourly_payload(day, {8: 20.0}))

    fetch_weather(45.46, 9.19, day, "08:00", ref=TODAY, fetch=fetch)

    url, params = calls[0]
    assert url == FORECAST_URL
    assert params["past_days"] >= 3


def test_fetchWeather_networkFailure_returnsNoneInsteadOfRaising():
    def _boom(url, params):
        raise RuntimeError("connessione rifiutata")

    day = (TODAY - timedelta(days=10)).isoformat()
    assert fetch_weather(45.46, 9.19, day, "08:00", ref=TODAY, fetch=_boom) is None


def test_fetchWeather_malformedResponses_returnNone():
    day = (TODAY - timedelta(days=10)).isoformat()
    for payload in (None, {}, {"hourly": {}}, {"hourly": {"time": "nope"}}):
        assert fetch_weather(
            45.46, 9.19, day, "08:00", ref=TODAY, fetch=lambda u, p, _r=payload: _r
        ) is None


def test_fetchWeather_hourMissingFromResponse_returnsNone():
    day = (TODAY - timedelta(days=10)).isoformat()
    payload = _hourly_payload(day, {})  # every temperature is null
    payload["hourly"]["relative_humidity_2m"] = [None] * 24
    fetch, _ = _recorder(payload)

    assert fetch_weather(45.46, 9.19, day, "08:00", ref=TODAY, fetch=fetch) is None


def test_fetchWeather_futureRun_isRefused():
    tomorrow = (TODAY + timedelta(days=1)).isoformat()
    fetch, calls = _recorder(_hourly_payload(tomorrow, {8: 20.0}))

    assert fetch_weather(45.46, 9.19, tomorrow, "08:00", ref=TODAY, fetch=fetch) is None
    assert calls == []  # not even attempted


# --------------------------------------------------------------------------
# applying it to stored runs
# --------------------------------------------------------------------------
def _run(session, days_ago: int, *, polyline=MILAN, temp=None, start="08:00") -> Activity:
    row = Activity(
        garmin_activity_id=f"g-{days_ago}",
        date=(TODAY - timedelta(days=days_ago)).isoformat(),
        start_time=start, sport="run", activity_type="easy",
        distance_km=10.0, duration_min=55.0, temperature_c=temp,
        route_polyline=json.dumps(polyline) if polyline else None,
    )
    session.add(row)
    session.flush()
    return row


def test_fillMissingWeather_fillsTheGaps(session):
    _run(session, 30)
    _run(session, 40)
    day = (TODAY - timedelta(days=30)).isoformat()
    fetch, _ = _recorder(_hourly_payload(day, {8: 28.4}))

    result = fill_missing_weather(session, throttle_s=0, ref=TODAY, fetch=fetch)

    assert result.filled == 2
    assert all(a.temperature_c == 28.4 for a in session.query(Activity).all())


def test_fillMissingWeather_neverOverwritesTheWatchsOwnReading(session):
    """A real measurement beats a reanalysis grid — always."""
    _run(session, 30, temp=19.0)
    day = (TODAY - timedelta(days=30)).isoformat()
    fetch, _ = _recorder(_hourly_payload(day, {8: 28.4}))

    fill_missing_weather(session, throttle_s=0, ref=TODAY, fetch=fetch)

    assert session.query(Activity).one().temperature_c == 19.0


def test_fillMissingWeather_usesEachRunsOwnStartPoint(session):
    """Weather is sampled where the run began, not at some global location."""
    _run(session, 30, polyline=[[45.4642, 9.1900]])
    _run(session, 31, polyline=[[41.9028, 12.4964]])  # Rome
    day = (TODAY - timedelta(days=30)).isoformat()
    fetch, calls = _recorder(_hourly_payload(day, {8: 25.0}))

    fill_missing_weather(session, throttle_s=0, ref=TODAY, fetch=fetch)

    latitudes = {round(params["latitude"], 2) for _, params in calls}
    assert latitudes == {45.46, 41.90}


def test_fillMissingWeather_noGpsAndNoHome_isCountedNotCrashed(session):
    _run(session, 30, polyline=None)
    fetch, calls = _recorder({})

    result = fill_missing_weather(
        session, throttle_s=0, ref=TODAY, fetch=fetch, use_fallback_location=False
    )

    assert result.no_location == 1
    assert result.filled == 0
    assert calls == []


def test_fillMissingWeather_noGps_fallsBackToAnotherRunsLocation(session):
    """A treadmill run still happened somewhere — usually where you live."""
    _run(session, 5, polyline=MILAN, temp=20.0)   # provides the location
    _run(session, 30, polyline=None)              # the one to fill
    day = (TODAY - timedelta(days=30)).isoformat()
    fetch, calls = _recorder(_hourly_payload(day, {8: 26.0}))

    result = fill_missing_weather(session, throttle_s=0, ref=TODAY, fetch=fetch)

    assert result.filled == 1
    assert calls
    assert round(calls[0][1]["latitude"], 2) == 45.46


def test_fillMissingWeather_isIdempotent(session):
    _run(session, 30)
    day = (TODAY - timedelta(days=30)).isoformat()
    fetch, calls = _recorder(_hourly_payload(day, {8: 28.4}))
    fill_missing_weather(session, throttle_s=0, ref=TODAY, fetch=fetch)

    calls.clear()
    again = fill_missing_weather(session, throttle_s=0, ref=TODAY, fetch=fetch)

    assert again.considered == 0
    assert calls == []  # nothing left to ask about


def test_fillMissingWeather_outage_leavesDataUntouched(session):
    _run(session, 30)

    def _boom(url, params):
        raise RuntimeError("open-meteo giù")

    result = fill_missing_weather(session, throttle_s=0, ref=TODAY, fetch=_boom)

    assert result.filled == 0
    assert result.no_data == 1
    assert session.query(Activity).one().temperature_c is None


def test_fillMissingWeather_respectsTheBatchLimit(session):
    for i in range(5):
        _run(session, 30 + i)
    day = (TODAY - timedelta(days=30)).isoformat()
    fetch, calls = _recorder(_hourly_payload(day, {8: 22.0}))

    result = fill_missing_weather(session, limit=2, throttle_s=0, ref=TODAY, fetch=fetch)

    assert result.considered == 2
    assert len(calls) == 2


def test_fillMissingWeather_emptyDatabase_reportsNothing(session):
    result = fill_missing_weather(session, throttle_s=0, ref=TODAY, fetch=lambda u, p: {})

    assert result.considered == 0
    assert result.filled == 0


@pytest.mark.parametrize("start_time,expected", [("06:45", 6), ("19:00", 19), ("00:10", 0)])
def test_fillMissingWeather_samplesTheHourOfTheRun(session, start_time, expected):
    _run(session, 30, start=start_time)
    day = (TODAY - timedelta(days=30)).isoformat()
    temps = {h: float(h) for h in range(24)}
    fetch, _ = _recorder(_hourly_payload(day, temps))

    fill_missing_weather(session, throttle_s=0, ref=TODAY, fetch=fetch)

    assert session.query(Activity).one().temperature_c == float(expected)
