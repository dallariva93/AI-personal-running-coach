"""Unit tests for the pure Strava mapping helpers."""

from __future__ import annotations

import json

from app.collection.strava import (
    build_authorize_url,
    decode_polyline,
    synthesize_cross_training_strava,
    synthesize_strava,
)


def test_decode_polyline_google_reference_vector():
    # The canonical example from Google's polyline algorithm docs.
    pts = decode_polyline("_p~iF~ps|U_ulLnnqC_mqNvxq`@")
    assert pts == [[38.5, -120.2], [40.7, -120.95], [43.252, -126.453]]


def test_decode_polyline_empty():
    assert decode_polyline("") == []


def test_synthesize_strava_core_fields():
    activity = {
        "id": 123456,
        "name": "Morning Run",
        "type": "Run",
        "sport_type": "Run",
        "distance": 10000.0,  # 10 km
        "moving_time": 3000,  # 50 min → 5:00/km
        "elapsed_time": 3100,
        "start_date_local": "2026-06-22T07:30:00Z",
        "average_heartrate": 150.4,
        "max_heartrate": 172.0,
        "total_elevation_gain": 80.0,
        "average_cadence": 85.0,  # per-leg → 170 spm
        "perceived_exertion": 6,
        "map": {"summary_polyline": "_p~iF~ps|U_ulLnnqC_mqNvxq`@"},
        "splits_metric": [
            {"distance": 1000.0, "moving_time": 300},
            {"distance": 1000.0, "moving_time": 295},
        ],
        "description": "Felt good",
    }
    run = synthesize_strava(activity)

    assert run.strava_activity_id == "123456"
    assert run.date == "2026-06-22"
    assert run.distance_km == 10.0
    assert run.duration_min == 50.0
    assert run.avg_pace == "5:00/km"
    assert run.avg_hr == 150
    assert run.max_hr == 172
    assert run.avg_cadence == 170  # doubled from per-leg cadence
    assert run.rpe == 6
    assert run.elevation_gain_m == 80.0
    assert run.notes == "Felt good"
    assert run.splits_km == ["5:00/km", "4:55/km"]

    coords = json.loads(run.route_polyline)
    assert coords[0] == [38.5, -120.2]
    assert len(coords) == 3
    # 10 km, flat, no name hint → easy.
    assert run.activity_type == "easy"


def test_synthesize_strava_classifies_long_run_by_workout_type():
    run = synthesize_strava(
        {"id": 1, "type": "Run", "distance": 8000.0, "moving_time": 2400, "workout_type": 2}
    )
    assert run.activity_type == "lungo"


def test_synthesize_strava_classifies_trail_by_sport_type():
    run = synthesize_strava(
        {"id": 2, "sport_type": "TrailRun", "distance": 9000.0, "moving_time": 3600}
    )
    assert run.activity_type == "trail"


def test_synthesize_strava_handles_missing_optional_fields():
    run = synthesize_strava({"id": 3, "type": "Run", "distance": 5000.0, "moving_time": 1500})
    assert run.strava_activity_id == "3"
    assert run.avg_hr is None
    assert run.avg_cadence is None
    assert run.rpe is None
    assert run.route_polyline is None
    assert run.splits_km is None


def test_synthesize_strava_classifies_race_and_intervals_by_workout_type():
    race = synthesize_strava(
        {"id": 10, "type": "Run", "distance": 21000.0, "moving_time": 5400, "workout_type": 1}
    )
    assert race.activity_type == "gara"
    intervals = synthesize_strava(
        {"id": 11, "type": "Run", "distance": 8000.0, "moving_time": 2400, "workout_type": 3}
    )
    assert intervals.activity_type == "intervalli"


def test_synthesize_cross_training_strava_bike_with_polyline():
    summary = synthesize_cross_training_strava(
        {
            "id": 88,
            "type": "Ride",
            "distance": 30000.0,
            "moving_time": 3600,
            "start_date_local": "2026-06-21T09:00:00Z",
            "total_elevation_gain": 350.0,
            "map": {"summary_polyline": "_p~iF~ps|U_ulLnnqC_mqNvxq`@"},
        },
        "bike",
    )
    assert summary.sport == "bike"
    assert summary.distance_km == 30.0
    assert summary.elevation_gain_m == 350.0
    assert summary.avg_pace is None  # bike → no pace
    coords = json.loads(summary.route_polyline)
    assert len(coords) == 3


def test_build_authorize_url_contains_params():
    url = build_authorize_url("999", "https://x.dev/api/strava/callback", state="xyz")
    assert url.startswith("https://www.strava.com/oauth/authorize?")
    assert "client_id=999" in url
    assert "activity%3Aread_all" in url  # scope url-encoded
    assert "state=xyz" in url


# ── StravaClient REST surface (fake HTTP) ────────────────────────────────────


class _FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeHTTP:
    def __init__(self, payload):
        self._payload = payload
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append(("POST", url))
        return _FakeResponse(self._payload)

    def get(self, url, **kwargs):
        self.calls.append(("GET", url))
        return _FakeResponse(self._payload)

    def delete(self, url, **kwargs):
        self.calls.append(("DELETE", url))
        return _FakeResponse({})


def test_strava_client_token_and_activity_calls():
    from app.collection.strava import StravaClient
    from app.config import get_settings

    http = _FakeHTTP({"access_token": "a", "refresh_token": "r", "expires_at": 123})
    client = StravaClient(get_settings(), session=http)

    tokens = client.exchange_code("code123")
    assert tokens["access_token"] == "a"
    assert client.refresh_token("r")["refresh_token"] == "r"

    http_act = _FakeHTTP({"id": 1, "type": "Run"})
    client2 = StravaClient(get_settings(), session=http_act)
    assert client2.get_activity("tok", 1)["id"] == 1

    http_list = _FakeHTTP([{"id": 1}, {"id": 2}])
    client3 = StravaClient(get_settings(), session=http_list)
    assert len(client3.list_activities("tok")) == 2


def test_strava_client_subscription_calls():
    from app.collection.strava import StravaClient
    from app.config import get_settings

    http = _FakeHTTP([{"id": 7}])
    client = StravaClient(get_settings(), session=http)
    assert client.view_subscriptions() == [{"id": 7}]

    http_create = _FakeHTTP({"id": 8})
    client2 = StravaClient(get_settings(), session=http_create)
    assert client2.create_subscription("https://cb", "verify")["id"] == 8

    # delete returns None and issues a DELETE.
    assert client.delete_subscription(7) is None
    assert any(c[0] == "DELETE" for c in http.calls)
