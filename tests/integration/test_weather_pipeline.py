"""Weather-window suggestion pipeline (Passo 6 / Q6) — no network in tests."""

from __future__ import annotations

import json
from datetime import date

from app.db.models import Activity, CoachEvent
from app.services.weather import HourForecast, maybe_suggest_weather_window

REF = date(2026, 6, 24)


class _FakeClient:
    """Stand-in WeatherClient: records calls, never touches the network."""

    def __init__(self, hours: list[HourForecast]):
        self.hours = hours
        self.calls = 0

    def fetch_hourly(self, lat, lon, day):  # noqa: ANN001
        self.calls += 1
        return self.hours


def _gps_run(session, d: str = "2026-06-23") -> None:
    session.add(
        Activity(
            date=d, sport="run", activity_type="easy", distance_km=8.0,
            route_polyline=json.dumps([[45.07, 7.69], [45.08, 7.70]]),
        )
    )
    session.flush()


def _cool_morning() -> list[HourForecast]:
    return [HourForecast(hour=h, temp_c=12 + h, precip_prob=0) for h in range(6, 22)]


def test_weather_event_created_once_and_is_notifiable(session):
    _gps_run(session)
    client = _FakeClient(_cool_morning())

    ev = maybe_suggest_weather_window(session, "easy", ref=REF, client=client)
    assert ev is not None
    assert ev.event_type == "weather"
    assert ev.notifiable is True and ev.priority == "low"
    assert ev.dedupe_key == "weather:2026-06-24"
    assert "Corri alle" in ev.detail
    assert client.calls == 1


def test_weather_event_deduped_same_day_no_second_fetch(session):
    _gps_run(session)
    client = _FakeClient(_cool_morning())

    first = maybe_suggest_weather_window(session, "easy", ref=REF, client=client)
    second = maybe_suggest_weather_window(session, "easy", ref=REF, client=client)
    assert first is not None
    assert second is None            # deduped
    assert client.calls == 1         # and no second network call
    events = session.query(CoachEvent).filter_by(event_type="weather").all()
    assert len(events) == 1


def test_weather_skipped_on_rest_day(session):
    _gps_run(session)
    client = _FakeClient(_cool_morning())
    assert maybe_suggest_weather_window(session, "rest", ref=REF, client=client) is None
    assert client.calls == 0


def test_weather_skipped_without_location(session):
    # No GPS run and no home lat/lon configured → cannot resolve location.
    client = _FakeClient(_cool_morning())
    assert maybe_suggest_weather_window(session, "easy", ref=REF, client=client) is None
    assert client.calls == 0


def test_weather_disabled_by_default_does_no_network(session):
    """Without an injected client and weather_enabled=False (default), the
    pipeline is a no-op — the general suite never hits the network."""
    _gps_run(session)
    assert maybe_suggest_weather_window(session, "easy", ref=REF) is None
