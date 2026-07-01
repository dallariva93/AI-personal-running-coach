"""Tests for raw activity archival (object store + Garmin raw fetcher)."""

from __future__ import annotations

import json

from app.collection.garmin_raw import GarminRawFetcher
from app.storage import checksum, get_object_store


def test_object_store_disabled_without_config(monkeypatch):
    """No S3 env -> get_object_store returns None and never imports boto3."""
    for var in (
        "S3_ENDPOINT_URL",
        "AWS_ENDPOINT_URL_S3",
        "S3_BUCKET",
        "BUCKET_NAME",
        "S3_ACCESS_KEY_ID",
        "AWS_ACCESS_KEY_ID",
        "S3_SECRET_ACCESS_KEY",
        "AWS_SECRET_ACCESS_KEY",
    ):
        monkeypatch.setenv(var, "")
    from app.config import get_settings

    get_settings.cache_clear()
    assert get_object_store() is None


class _FakeStore:
    """In-memory stand-in for ObjectStore."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put_bytes(self, key: str, data: bytes, content_type: str = "") -> None:
        self.objects[key] = data

    def get_bytes(self, key: str) -> bytes:
        return self.objects[key]

    def exists(self, key: str) -> bool:
        return key in self.objects

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)


class _FakeClient:
    """Minimal Garmin client exposing a couple of JSON endpoints."""

    def get_activity(self, activity_id):
        return {"activityId": activity_id, "summary": True}

    def get_activity_details(self, activity_id):
        return {"metricDescriptors": [], "activityId": activity_id}


def test_fetch_all_archives_available_kinds():
    store = _FakeStore()
    fetcher = GarminRawFetcher(client=_FakeClient(), store=store)

    assets = fetcher.fetch_all(activity_id="42", activity_type_key="running")

    kinds = {a.kind for a in assets}
    # Only the two endpoints the fake client implements are archived; the rest
    # are skipped gracefully (no attribute / no download method).
    assert kinds == {"summary", "details"}
    for asset in assets:
        assert asset.activity_id == "42"
        assert asset.activity_type_key == "running"
        assert asset.s3_key in store.objects
        assert asset.sha256 == checksum(store.objects[asset.s3_key])
    # Stored payloads are valid JSON.
    summary = next(a for a in assets if a.kind == "summary")
    assert json.loads(store.objects[summary.s3_key])["activityId"] == "42"


def test_fetch_all_skips_already_archived():
    store = _FakeStore()
    fetcher = GarminRawFetcher(client=_FakeClient(), store=store)

    assets = fetcher.fetch_all(
        activity_id="42", already_archived_kinds={"summary", "details"}
    )
    assert assets == []
    assert store.objects == {}
