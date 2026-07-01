"""Integration of sync_raw_assets with the DB dedup logic."""

from __future__ import annotations

from typing import Any

import pytest

from app.config import get_settings
from app.db.models import RawActivityAsset
from app.services.ingest import sync_raw_assets
from app.storage.object_store import InMemoryObjectStore


class _FakeDownloadFormat:
    GPX = "GPX_FMT"
    TCX = "TCX_FMT"
    ORIGINAL = "ORIGINAL_FMT"


class FakeGarminClient:
    ActivityDownloadFormat = _FakeDownloadFormat

    def __init__(self) -> None:
        self.downloads = {
            _FakeDownloadFormat.GPX: b"<gpx/>",
            _FakeDownloadFormat.TCX: b"<tcx/>",
            _FakeDownloadFormat.ORIGINAL: b"FITZIP",
        }

    def _payload(self, name: str) -> dict[str, Any]:
        return {"endpoint": name}

    def get_activity(self, _):
        return self._payload("get_activity")

    def get_activity_details(self, _):
        return self._payload("get_activity_details")

    def get_activity_splits(self, _):
        return self._payload("get_activity_splits")

    def get_activity_typed_splits(self, _):
        return self._payload("get_activity_typed_splits")

    def get_activity_split_summaries(self, _):
        return self._payload("get_activity_split_summaries")

    def get_activity_weather(self, _):
        return self._payload("get_activity_weather")

    def get_activity_hr_in_timezones(self, _):
        return self._payload("get_activity_hr_in_timezones")

    def get_activity_power_in_timezones(self, _):
        return self._payload("get_activity_power_in_timezones")

    def get_activity_exercise_sets(self, _):
        return self._payload("get_activity_exercise_sets")

    def get_activity_gear(self, _):
        return self._payload("get_activity_gear")

    def download_activity(self, _, dl_fmt):
        return self.downloads.get(dl_fmt)


class FakeGarminSource:
    """Stands in for ``GarminSource`` in unit tests."""

    def __init__(self, activities: list[dict[str, Any]]) -> None:
        self._activities = activities
        self._client = FakeGarminClient()

    def get_recent_activities(self, limit: int) -> list[dict[str, Any]]:
        return self._activities[:limit]

    def get_client(self) -> Any:
        return self._client


@pytest.fixture(autouse=True)
def _patch_garmin_download_format(monkeypatch):
    import garminconnect

    monkeypatch.setattr(
        garminconnect.Garmin, "ActivityDownloadFormat", _FakeDownloadFormat, raising=True
    )


@pytest.fixture
def fake_source() -> FakeGarminSource:
    return FakeGarminSource(
        activities=[
            {"activityId": 111, "activityType": {"typeKey": "running"}},
            {"activityId": 222, "activityType": {"typeKey": "cycling"}},
        ]
    )


def _count_rows(session) -> int:
    return session.query(RawActivityAsset).count()


def test_sync_raw_assets_storesRowsAndBlobs_forAllActivityTypes(session, fake_source):
    store = InMemoryObjectStore()
    rows = sync_raw_assets(session, fake_source, limit=10, store=store)
    session.commit()

    # 13 kinds per activity * 2 activities (running + cycling).
    assert len(rows) == 26
    assert _count_rows(session) == 26
    # Every recorded row points at an object that actually exists.
    for row in rows:
        assert store.exists(row.s3_key)
    # Cycling activity is archived too (not just running).
    activity_keys = {r.garmin_activity_id for r in rows}
    assert activity_keys == {"111", "222"}
    type_keys = {r.activity_type_key for r in rows}
    assert type_keys == {"running", "cycling"}


def test_sync_raw_assets_isIdempotent_onSecondRun(session, fake_source):
    store = InMemoryObjectStore()
    sync_raw_assets(session, fake_source, limit=10, store=store)
    session.commit()
    first = _count_rows(session)

    rows2 = sync_raw_assets(session, fake_source, limit=10, store=store)
    session.commit()
    assert rows2 == []
    assert _count_rows(session) == first


def test_sync_raw_assets_noStore_returnsEmpty(session, fake_source, monkeypatch):
    # Make sure factory returns None when S3 is not configured.
    monkeypatch.setenv("S3_ENDPOINT_URL", "")
    monkeypatch.setenv("S3_BUCKET", "")
    get_settings.cache_clear()
    try:
        rows = sync_raw_assets(session, fake_source, limit=10, store=None)
    finally:
        get_settings.cache_clear()
    assert rows == []
    assert _count_rows(session) == 0
