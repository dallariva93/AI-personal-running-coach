"""Feature 24 — pure sport-mapping and synthesis for bike/swim/strength."""

from __future__ import annotations

from app.collection.sources import GarminSource
from app.collection.strava import strava_sport, synthesize_cross_training_strava
from app.collection.synthesize import (
    garmin_sport,
    synthesize_cross_training,
)


def test_garmin_sport_mapping():
    assert garmin_sport({"activityType": {"typeKey": "road_biking"}}) == "bike"
    assert garmin_sport({"activityType": {"typeKey": "lap_swimming"}}) == "swim"
    assert garmin_sport({"activityType": {"typeKey": "strength_training"}}) == "strength"
    # Running and unsupported types are not cross-training.
    assert garmin_sport({"activityType": {"typeKey": "running"}}) is None
    assert garmin_sport({"activityType": {"typeKey": "kayaking"}}) is None
    # typeKey can arrive as a bare string; missing type → None.
    assert garmin_sport({"activityType": "indoor_cycling"}) == "bike"
    assert garmin_sport({}) is None


def test_synthesize_cross_training_swim_keeps_pace():
    summary = synthesize_cross_training(
        {
            "activityId": 5,
            "startTimeLocal": "2026-06-20 07:30:00",
            "activityType": {"typeKey": "lap_swimming"},
            "distance": 2000.0,
            "duration": 2400.0,
        },
        "swim",
    )
    assert summary.sport == "swim"
    assert summary.avg_pace is not None


def test_ingest_cross_training_no_op_when_source_lacks_support(session):
    class _RunsOnlySource:
        def get_recent_runs(self, limit=10, skip_gps_for=None):
            return []

    from app.services import ingest_cross_training

    assert ingest_cross_training(session, source=_RunsOnlySource()) == []


def test_synthesize_cross_training_bike():
    summary = synthesize_cross_training(
        {
            "activityId": 1,
            "activityName": "Giro",
            "startTimeLocal": "2026-06-28 08:00:00",
            "activityType": {"typeKey": "road_biking"},
            "distance": 42000.0,
            "duration": 5400.0,
            "averageHR": 130,
            "elevationGain": 400.0,
        },
        "bike",
    )
    assert summary.sport == "bike"
    assert summary.activity_type == "bike"
    assert summary.distance_km == 42.0
    assert summary.avg_hr == 130
    assert summary.avg_pace is None  # pace not meaningful for cycling


def test_synthesize_cross_training_strength_has_no_distance():
    summary = synthesize_cross_training(
        {
            "activityId": 2,
            "startTimeLocal": "2026-06-25 18:00:00",
            "activityType": {"typeKey": "strength_training"},
            "distance": 0.0,
            "duration": 3000.0,
        },
        "strength",
    )
    assert summary.sport == "strength"
    assert summary.distance_km == 0.0
    assert summary.duration_min == 50.0


def test_strava_sport_mapping():
    assert strava_sport({"type": "Run"}) == "run"
    assert strava_sport({"sport_type": "TrailRun"}) == "run"
    assert strava_sport({"type": "Ride"}) == "bike"
    assert strava_sport({"sport_type": "MountainBikeRide"}) == "bike"
    assert strava_sport({"type": "Swim"}) == "swim"
    assert strava_sport({"type": "WeightTraining"}) == "strength"
    assert strava_sport({"type": "AlpineSki"}) is None


def test_synthesize_cross_training_strava_swim():
    summary = synthesize_cross_training_strava(
        {
            "id": 77,
            "type": "Swim",
            "distance": 1500.0,
            "moving_time": 1800,
            "start_date_local": "2026-06-20T07:30:00Z",
            "average_heartrate": 134.0,
        },
        "swim",
    )
    assert summary.sport == "swim"
    assert summary.strava_activity_id == "77"
    assert summary.distance_km == 1.5
    assert summary.avg_pace is not None  # swim keeps pace


def test_garmin_source_get_recent_cross_training_filters(monkeypatch):
    source = GarminSource()
    raw = [
        {"activityId": 1, "activityType": {"typeKey": "running"}, "distance": 5000.0},
        {
            "activityId": 2,
            "activityType": {"typeKey": "road_biking"},
            "distance": 30000.0,
            "duration": 3600.0,
        },
        {
            "activityId": 3,
            "activityType": {"typeKey": "lap_swimming"},
            "distance": 2000.0,
            "duration": 2400.0,
        },
    ]
    monkeypatch.setattr(source, "get_recent_activities", lambda limit: raw)
    out = source.get_recent_cross_training(limit=10)
    sports = {s.sport for s in out}
    assert sports == {"bike", "swim"}  # running excluded
