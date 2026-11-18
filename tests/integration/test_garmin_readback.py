"""Integration: reading back what is actually on Garmin.

Diagnostics, not features — but they exist for a reason worth keeping. Garmin's
workout list is a *window*: it answers with the most recently updated items, so
a request with a small limit shows only what was just created and makes
everything older look absent. That is exactly the wrong impression to leave
behind while trying to find out what the service really stores.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


class PagedGarmin:
    """A Garmin whose workout list only ever answers one window at a time."""

    def __init__(self, total: int) -> None:
        self.all = [
            {
                "workoutId": 1000 + i,
                "workoutName": f"Allenamento {i}",
                "sportType": {"sportTypeKey": "running"},
                "updateDate": "2026-08-01",
            }
            for i in range(total)
        ]
        self.calls: list[tuple[int, int]] = []

    def get_workouts(self, start: int, limit: int):
        self.calls.append((start, limit))
        return self.all[start : start + limit]


@pytest.fixture
def authed(db_env, monkeypatch):
    from app.config import get_settings
    from app.main import app

    monkeypatch.setenv("API_TOKEN", "test-api-token")
    get_settings.cache_clear()
    with TestClient(app) as client:
        yield client, {"Authorization": "Bearer test-api-token"}
    get_settings.cache_clear()


def _patch(monkeypatch, client_obj):
    import app.services.garmin_export as ge

    monkeypatch.setattr(ge, "_garmin_client", lambda: client_obj)


def test_workouts_requireTheToken(authed):
    client, _ = authed

    assert client.get("/api/garmin/workouts").status_code == 401


def test_workouts_pageThroughEverything(authed, monkeypatch):
    """250 saved workouts must not come back as the newest 10."""
    client, headers = authed
    fake = PagedGarmin(total=250)
    _patch(monkeypatch, fake)

    body = client.get("/api/garmin/workouts", headers=headers).json()

    assert body["returned"] == 250
    assert body["complete"] is True
    assert len(fake.calls) > 1  # it really paged


def test_workouts_stopAtAShortPage_insteadOfLooping(authed, monkeypatch):
    """An API that answers [] forever past the end must not spin."""
    client, headers = authed
    fake = PagedGarmin(total=30)
    _patch(monkeypatch, fake)

    body = client.get("/api/garmin/workouts", headers=headers).json()

    assert body["returned"] == 30
    assert len(fake.calls) <= 2


def test_workouts_respectAnExplicitLimit(authed, monkeypatch):
    client, headers = authed
    _patch(monkeypatch, PagedGarmin(total=250))

    body = client.get("/api/garmin/workouts?limit=20", headers=headers).json()

    assert body["returned"] == 20


def test_workouts_partialResultSaysItIsPartial(authed, monkeypatch):
    """Half an answer is useful; half an answer that looks whole is not."""
    client, headers = authed

    class Flaky(PagedGarmin):
        def get_workouts(self, start, limit):
            if start > 0:
                raise RuntimeError("Garmin 500")
            return super().get_workouts(start, limit)

    _patch(monkeypatch, Flaky(total=250))

    body = client.get("/api/garmin/workouts", headers=headers).json()

    assert body["returned"] == 100
    assert body["complete"] is False
    assert body["error"]


def test_workouts_totalFailureIs502(authed, monkeypatch):
    client, headers = authed

    class Dead:
        def get_workouts(self, start, limit):
            raise RuntimeError("Garmin down")

    _patch(monkeypatch, Dead())

    assert client.get("/api/garmin/workouts", headers=headers).status_code == 502


def test_scheduled_rejectsABadMonth(authed, monkeypatch):
    client, headers = authed
    _patch(monkeypatch, PagedGarmin(total=1))

    resp = client.get("/api/garmin/scheduled?year=2026&month=13", headers=headers)

    assert resp.status_code == 400
