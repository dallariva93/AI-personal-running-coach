"""Unit tests for the pure Strava mapping helpers."""

from __future__ import annotations

import json

from app.collection.strava import build_authorize_url, decode_polyline, synthesize_strava


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


def test_build_authorize_url_contains_params():
    url = build_authorize_url("999", "https://x.dev/api/strava/callback")
    assert url.startswith("https://www.strava.com/oauth/authorize?")
    assert "client_id=999" in url
    assert "activity%3Aread_all" in url  # scope url-encoded
