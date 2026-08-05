"""Unit: recognising a treadmill run.

A treadmill session reaches the app as an ordinary run — Garmin's typeKey is
``treadmill_running``/``indoor_running`` and Strava keeps sport_type "Run" with
``trainer: true``, so both pass the "is this running?" filter. It *should*
count as running load; what must not happen is the rest of the pipeline
treating it like a road run, because it has no GPS, its pace depends on the
belt's calibration and its zero elevation means "no data", not "flat".
"""

from __future__ import annotations

import pytest

from app.collection.sources import _is_running
from app.collection.synthesize import is_indoor_activity


def _garmin(type_key: str) -> dict:
    return {"activityType": {"typeKey": type_key}}


@pytest.mark.parametrize(
    "type_key",
    ["treadmill_running", "indoor_running", "virtual_run", "TREADMILL_RUNNING"],
)
def test_garminIndoorTypes_areDetected(type_key):
    assert is_indoor_activity(_garmin(type_key)) is True


@pytest.mark.parametrize("type_key", ["running", "trail_running", "street_running"])
def test_garminOutdoorTypes_areNotIndoor(type_key):
    assert is_indoor_activity(_garmin(type_key)) is False


@pytest.mark.parametrize("type_key", ["treadmill_running", "indoor_running", "running"])
def test_indoorRunsStillCountAsRunning(type_key):
    """Running on a belt is still running load — it must not be filtered out."""
    assert _is_running(_garmin(type_key)) is True


def test_stravaTrainerFlag_isDetected():
    """Strava keeps sport_type "Run" and flags the treadmill separately."""
    assert is_indoor_activity({"sport_type": "Run", "trainer": True}) is True
    assert is_indoor_activity({"sport_type": "Run", "trainer": 1}) is True
    assert is_indoor_activity({"sport_type": "Run", "trainer": False}) is False
    assert is_indoor_activity({"sport_type": "Run"}) is False


def test_malformedPayloads_defaultToOutdoor():
    """Unknown shape means "no evidence of indoor", never a guess."""
    assert is_indoor_activity({}) is False
    assert is_indoor_activity({"activityType": None}) is False
    assert is_indoor_activity({"activityType": "running"}) is False
