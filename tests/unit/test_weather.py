"""Weather-window optimizer (FINAL_ROADMAP §5-bis, Passo 6 / Q6)."""

from __future__ import annotations

from app.collection.synthesize import extract_start_time
from app.services.weather import (
    HourForecast,
    WeatherPrefs,
    best_window,
    parse_open_meteo,
)


# ── start_time extraction (prerequisite) ─────────────────────────────────────
def test_extract_start_time_garmin_and_strava():
    assert extract_start_time("2026-06-24 07:05:00") == "07:05"
    assert extract_start_time("2026-06-24T18:40:12Z") == "18:40"


def test_extract_start_time_rejects_bad_input():
    assert extract_start_time("2026-06-24") is None
    assert extract_start_time("") is None
    assert extract_start_time(None) is None
    assert extract_start_time("2026-06-24 99:99:00") is None


# ── best_window scoring ──────────────────────────────────────────────────────
def _heat_day() -> list[HourForecast]:
    # Coolest early, hottest mid-afternoon — a canicola profile.
    temps = {6: 22, 7: 24, 9: 28, 12: 33, 15: 35, 18: 30, 21: 25}
    return [HourForecast(hour=h, temp_c=t, precip_prob=0) for h, t in temps.items()]


def test_heatwave_picks_early_morning():
    win = best_window(_heat_day())
    assert win is not None
    assert win.hour <= 7  # coolest window is the early morning
    assert "°C" in win.summary


def test_rain_bands_pick_the_dry_gap():
    # Uniform ideal temp; rain 06-09 and 17-20, a dry gap 10-16.
    hours = []
    for h in range(6, 22):
        wet = h <= 9 or h >= 17
        hours.append(HourForecast(hour=h, temp_c=14, precip_prob=90 if wet else 5))
    win = best_window(hours)
    assert win is not None
    assert 10 <= win.hour <= 16  # the dry buco


def test_habitual_hours_break_a_tie():
    # Two equally-good hours; the habitual one wins.
    hours = [
        HourForecast(hour=7, temp_c=12, precip_prob=0),
        HourForecast(hour=18, temp_c=12, precip_prob=0),
    ]
    win = best_window(hours, WeatherPrefs(habitual_hours=(18,)))
    assert win is not None and win.hour == 18


def test_best_window_empty_returns_none():
    assert best_window([]) is None
    # Only night hours (outside 06-21) → nothing to suggest.
    assert best_window([HourForecast(hour=3, temp_c=12)]) is None


# ── parse_open_meteo ─────────────────────────────────────────────────────────
def test_parse_open_meteo_normalises_hours():
    payload = {
        "hourly": {
            "time": ["2026-06-24T06:00", "2026-06-24T07:00"],
            "temperature_2m": [18.0, 19.5],
            "precipitation_probability": [10, 5],
            "wind_speed_10m": [8, 9],
            "apparent_temperature": [17.0, 18.0],
        }
    }
    pts = parse_open_meteo(payload)
    assert [p.hour for p in pts] == [6, 7]
    assert pts[0].temp_c == 18.0 and pts[1].precip_prob == 5.0
