"""Unit tests for the collection/synthesize layer."""

from __future__ import annotations

from app.collection.synthesize import _format_pace, _infer_type, synthesize


def test_format_pace_basic():
    # 5 km in 1500 s -> 5:00/km
    assert _format_pace(5000, 1500) == "5:00/km"


def test_format_pace_rounding_carry():
    # pace that rounds up to a full minute should carry correctly
    assert _format_pace(1000, 359.6) == "6:00/km"


def test_format_pace_zero_returns_none():
    assert _format_pace(0, 100) is None
    assert _format_pace(100, 0) is None


def test_infer_type_from_name():
    assert _infer_type({"activityName": "Tempo run"}) == "tempo"
    assert _infer_type({"activityName": "Long run"}) == "lungo"
    assert _infer_type({"activityName": "6x800 intervals"}) == "intervalli"
    assert _infer_type({"activityName": "Morning jog"}) == "easy"


def test_synthesize_maps_core_fields(raw_activities):
    activity = next(a for a in raw_activities if a["activityId"] == 9003)
    run = synthesize(activity)
    assert run.garmin_activity_id == "9003"
    assert run.date == "2026-06-03"
    assert run.activity_type == "tempo"
    assert run.distance_km == 10.0
    assert run.duration_min == 48.0
    assert run.avg_pace == "4:48/km"
    assert run.avg_hr == 162
    assert run.max_hr == 178


def test_synthesize_hr_zones_converted_to_minutes(raw_activities):
    activity = next(a for a in raw_activities if a["activityId"] == 9001)
    run = synthesize(activity)
    assert run.hr_zones is not None
    # zone2 was 1700 seconds -> ~28.3 minutes
    assert run.hr_zones["z2"] == 28.3
