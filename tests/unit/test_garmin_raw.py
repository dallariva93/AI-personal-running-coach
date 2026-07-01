"""Tests for the raw-archive fetcher with a fake Garmin client."""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.collection.garmin_raw import GarminRawFetcher
from app.storage.object_store import InMemoryObjectStore


class _FakeDownloadFormat:
    """Mimics ``Garmin.ActivityDownloadFormat`` enum entries used by the fetcher."""

    GPX = "GPX_FMT"
    TCX = "TCX_FMT"
    ORIGINAL = "ORIGINAL_FMT"


class FakeGarminClient:
    """Records each call and returns canned payloads."""

    ActivityDownloadFormat = _FakeDownloadFormat

    def __init__(self, payloads: dict[str, Any], downloads: dict[str, bytes]) -> None:
        self.payloads = payloads
        self.downloads = downloads
        self.calls: list[tuple[str, Any]] = []

    def _record(self, name: str, activity_id: Any):
        self.calls.append((name, activity_id))
        return self.payloads.get(name)

    def get_activity(self, activity_id):
        return self._record("get_activity", activity_id)

    def get_activity_details(self, activity_id):
        return self._record("get_activity_details", activity_id)

    def get_activity_splits(self, activity_id):
        return self._record("get_activity_splits", activity_id)

    def get_activity_typed_splits(self, activity_id):
        return self._record("get_activity_typed_splits", activity_id)

    def get_activity_split_summaries(self, activity_id):
        return self._record("get_activity_split_summaries", activity_id)

    def get_activity_weather(self, activity_id):
        return self._record("get_activity_weather", activity_id)

    def get_activity_hr_in_timezones(self, activity_id):
        return self._record("get_activity_hr_in_timezones", activity_id)

    def get_activity_power_in_timezones(self, activity_id):
        return self._record("get_activity_power_in_timezones", activity_id)

    def get_activity_exercise_sets(self, activity_id):
        return self._record("get_activity_exercise_sets", activity_id)

    def get_activity_gear(self, activity_id):
        return self._record("get_activity_gear", activity_id)

    def download_activity(self, activity_id, dl_fmt):
        self.calls.append((f"download:{dl_fmt}", activity_id))
        return self.downloads.get(dl_fmt)


@pytest.fixture(autouse=True)
def _patch_garmin_download_format(monkeypatch):
    """Replace ``garminconnect.Garmin.ActivityDownloadFormat`` so the fetcher
    can look up download formats without requiring a real Garmin instance.

    The fetcher imports ``from garminconnect import Garmin`` and reads
    ``Garmin.ActivityDownloadFormat.<NAME>``. The real library is installed
    in the venv, so we patch only the enum to return our sentinel strings.
    """
    import garminconnect

    monkeypatch.setattr(
        garminconnect.Garmin, "ActivityDownloadFormat", _FakeDownloadFormat, raising=True
    )


def _make_client_with_all_payloads() -> FakeGarminClient:
    payloads = {
        "get_activity": {"id": 1, "activityName": "Run"},
        "get_activity_details": {"metricDescriptors": [], "activityDetailMetrics": []},
        "get_activity_splits": {"splits": []},
        "get_activity_typed_splits": {"typedSplits": []},
        "get_activity_split_summaries": [{"splitType": "RUN"}],
        "get_activity_weather": {"temp": 18},
        "get_activity_hr_in_timezones": [{"zoneNumber": 1, "secsInZone": 60}],
        "get_activity_power_in_timezones": [{"zoneNumber": 1, "secsInZone": 10}],
        "get_activity_exercise_sets": {"exerciseSets": []},
        "get_activity_gear": [{"gearPk": 42}],
    }
    downloads = {
        _FakeDownloadFormat.GPX: b"<gpx></gpx>",
        _FakeDownloadFormat.TCX: b"<tcx></tcx>",
        _FakeDownloadFormat.ORIGINAL: b"PK\x03\x04zipbytes",
    }
    return FakeGarminClient(payloads=payloads, downloads=downloads)


def test_fetch_all_archivesEveryKind_andRecordsBytes():
    client = _make_client_with_all_payloads()
    store = InMemoryObjectStore()

    fetcher = GarminRawFetcher(client=client, store=store, key_prefix="garmin")
    assets = fetcher.fetch_all(activity_id=123, activity_type_key="running")

    kinds = {a.kind for a in assets}
    expected_kinds = {
        "summary",
        "details",
        "splits",
        "typed_splits",
        "split_summaries",
        "weather",
        "hr_in_timezones",
        "power_in_timezones",
        "exercise_sets",
        "gear",
        "gpx",
        "tcx",
        "original_fit_zip",
    }
    assert kinds == expected_kinds

    # Keys are namespaced under the configured prefix and activity id.
    for asset in assets:
        assert asset.s3_key.startswith("garmin/123/")
        assert store.exists(asset.s3_key)
        assert asset.size_bytes == len(store.get_bytes(asset.s3_key))
        assert asset.activity_type_key == "running"


def test_fetch_all_skipsKindsAlreadyArchived():
    client = _make_client_with_all_payloads()
    store = InMemoryObjectStore()
    fetcher = GarminRawFetcher(client=client, store=store, key_prefix="garmin")

    assets = fetcher.fetch_all(
        activity_id=99,
        activity_type_key="cycling",
        already_archived_kinds={"summary", "gpx", "details"},
    )
    kinds = {a.kind for a in assets}
    assert "summary" not in kinds
    assert "gpx" not in kinds
    assert "details" not in kinds
    # And the calls to those endpoints were not made
    assert ("get_activity", "99") not in client.calls
    assert ("get_activity_details", "99") not in client.calls
    assert (f"download:{_FakeDownloadFormat.GPX}", "99") not in client.calls


def test_fetch_all_failingEndpoint_doesNotAbortOthers(monkeypatch):
    client = _make_client_with_all_payloads()

    def boom(_):
        raise RuntimeError("rate limited")

    # Make weather fail; everything else should still archive.
    monkeypatch.setattr(client, "get_activity_weather", boom)
    store = InMemoryObjectStore()
    fetcher = GarminRawFetcher(client=client, store=store, key_prefix="garmin")

    assets = fetcher.fetch_all(activity_id=7, activity_type_key="running")
    kinds = {a.kind for a in assets}
    assert "weather" not in kinds
    assert "summary" in kinds
    assert "gpx" in kinds


def test_fetch_all_jsonPayload_storedAsCompactJson():
    client = _make_client_with_all_payloads()
    store = InMemoryObjectStore()
    fetcher = GarminRawFetcher(client=client, store=store, key_prefix="garmin")

    fetcher.fetch_all(activity_id=42, activity_type_key="running")
    summary_key = "garmin/42/summary.json"
    body = store.get_bytes(summary_key)
    parsed = json.loads(body)
    assert parsed["id"] == 1
    assert parsed["activityName"] == "Run"


def test_fetch_all_missingClientMethod_skipsKind(monkeypatch):
    client = _make_client_with_all_payloads()
    # Simulate an older library: remove the gear method.
    monkeypatch.delattr(type(client), "get_activity_gear", raising=True)

    store = InMemoryObjectStore()
    fetcher = GarminRawFetcher(client=client, store=store, key_prefix="garmin")
    assets = fetcher.fetch_all(activity_id=5, activity_type_key="running")
    kinds = {a.kind for a in assets}
    assert "gear" not in kinds
    # But the rest is still there
    assert "summary" in kinds
