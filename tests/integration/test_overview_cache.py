"""Cache for the hot read endpoints (FINAL_ROADMAP §5-bis, Passo 4 / Q5)."""

from __future__ import annotations

import app.api.mobile as mobile
import app.services.cache as cache


def _spy_compute_metrics(monkeypatch):
    """Wrap app.api.mobile.compute_metrics with a call counter."""
    calls = {"n": 0}
    real = mobile.compute_metrics

    def _counting(*args, **kwargs):
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(mobile, "compute_metrics", _counting)
    return calls


def test_second_overview_call_is_served_from_cache(client, monkeypatch):
    calls = _spy_compute_metrics(monkeypatch)
    client.post("/api/ingest")

    first = client.get("/api/mobile/overview")
    assert first.status_code == 200
    after_first = calls["n"]
    assert after_first >= 1  # a real compute happened

    second = client.get("/api/mobile/overview")
    assert second.status_code == 200
    assert calls["n"] == after_first  # no recompute: served from cache
    assert second.json() == first.json()


def test_cache_regenerates_after_a_write(client, monkeypatch):
    client.post("/api/ingest")
    client.get("/api/mobile/overview")  # warm the cache

    calls = _spy_compute_metrics(monkeypatch)
    # A write (check-in) must move the version so the next overview recomputes.
    client.post("/api/checkin", json={"date": "2026-06-24", "fatigue": 3, "sleep_h": 8})
    client.get("/api/mobile/overview")
    assert calls["n"] >= 1


def test_cache_version_changes_on_flush(session):
    before = cache.current_version()
    from app.db.models import Activity

    session.add(Activity(date="2026-06-24", sport="run", activity_type="easy", distance_km=5.0))
    session.flush()
    assert cache.current_version() != before


def test_reads_do_not_bump_the_version(client):
    client.post("/api/ingest")
    v1 = cache.current_version()
    client.get("/api/mobile/overview")
    client.get("/api/mobile/overview")
    assert cache.current_version() == v1  # pure reads never invalidate


def test_heatmap_is_cached(client, monkeypatch):
    client.post("/api/ingest")

    calls = {"n": 0}
    import app.api.routes as routes
    real = routes._build_heatmap

    def _counting(*args, **kwargs):
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(routes, "_build_heatmap", _counting)

    client.get("/api/activities/heatmap")
    client.get("/api/activities/heatmap")
    assert calls["n"] == 1  # second call served from cache
