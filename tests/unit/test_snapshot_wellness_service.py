"""Tests for the daily-wellness snapshot service (phase 0c)."""

from __future__ import annotations

from typing import Any

from app.db.models import DailyWellnessRow
from app.services.snapshot_wellness import snapshot_daily_wellness


class FakeWellnessClient:
    """Returns the same canned payloads for every requested date."""

    def __init__(
        self,
        *,
        sleep: Any = None,
        hrv: Any = None,
        stress: Any = None,
        body_battery: Any = None,
        resting_hr: Any = None,
        readiness: Any = None,
    ) -> None:
        self._sleep = sleep
        self._hrv = hrv
        self._stress = stress
        self._bb = body_battery
        self._rhr = resting_hr
        self._readiness = readiness

    def get_sleep_data(self, _cdate: str) -> Any:
        return self._sleep

    def get_hrv_data(self, _cdate: str) -> Any:
        return self._hrv

    def get_stress_data(self, _cdate: str) -> Any:
        return self._stress

    def get_body_battery(self, _start: str, _end: str | None = None) -> Any:
        return self._bb

    def get_rhr_day(self, _cdate: str) -> Any:
        return self._rhr

    def get_training_readiness(self, _cdate: str) -> Any:
        return self._readiness


def _full_client() -> FakeWellnessClient:
    return FakeWellnessClient(
        sleep={"dailySleepDTO": {"sleepTimeSeconds": 27000}},
        hrv={"hrvSummary": {"lastNightAvg": 65, "status": "BALANCED"}},
        stress={"avgStressLevel": 30},
        body_battery=[{"charged": 40, "drained": 55}],
        resting_hr={"restingHeartRate": 49},
        readiness=[{"score": 70, "level": "READY"}],
    )


def _count(session) -> int:
    return session.query(DailyWellnessRow).count()


def test_snapshot_writesNativeRow_forToday(session):
    written = snapshot_daily_wellness(session, days=1, client=_full_client())
    session.commit()

    assert written == 1
    assert _count(session) == 1
    row = session.query(DailyWellnessRow).one()
    assert row.sleep_seconds == 27000
    assert row.hrv_last_night_avg == 65.0
    assert row.hrv_status == "BALANCED"
    assert row.stress_avg == 30
    assert row.body_battery_charged == 40
    assert row.resting_hr == 49
    assert row.training_readiness_score == 70
    assert row.source == "garmin"


def test_snapshot_isIdempotent_noDuplicateRows(session):
    client = _full_client()
    snapshot_daily_wellness(session, days=3, client=client)
    session.commit()
    first_count = _count(session)
    assert first_count == 3  # today + two prior days

    # Second run: past days are skipped, today is always refreshed — but the
    # unique date constraint means no new rows appear.
    written2 = snapshot_daily_wellness(session, days=3, client=client)
    session.commit()
    assert written2 == 1  # only today re-fetched
    assert _count(session) == first_count


def test_snapshot_skipsDaysWithNoData(session):
    empty_client = FakeWellnessClient()  # every endpoint returns None
    written = snapshot_daily_wellness(session, days=3, client=empty_client)
    session.commit()

    assert written == 0
    assert _count(session) == 0


def test_snapshot_upsertFillsGaps_neverErasesPriorValues(session):
    sleep_only = FakeWellnessClient(
        sleep={"dailySleepDTO": {"sleepTimeSeconds": 25200}}
    )
    snapshot_daily_wellness(session, days=1, client=sleep_only)
    session.commit()

    # A later refresh brings HRV but no sleep: sleep must survive, HRV is added.
    hrv_only = FakeWellnessClient(hrv={"hrvSummary": {"lastNightAvg": 58}})
    snapshot_daily_wellness(session, days=1, client=hrv_only)
    session.commit()

    row = session.query(DailyWellnessRow).one()
    assert row.sleep_seconds == 25200
    assert row.hrv_last_night_avg == 58.0


def test_endpoint_dailyWellness_demoMode_returnsZero(client):
    """Garmin disabled in tests: the endpoint is wired and skips gracefully."""
    resp = client.post("/api/ingest/daily-wellness")
    assert resp.status_code == 200
    assert resp.json() == {"days_written": 0}
