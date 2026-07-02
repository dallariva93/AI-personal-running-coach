"""Integration tests: home-screen auto-sync/auto-analysis (Passo 2 / Q2).

POST /api/ingest must (a) skip a redundant Garmin fetch when called again
within 10 minutes, logging "skipped, recent", and (b) auto-run the
single-run analysis when the sync brought >=1 new activity, so the latest
run always has a report without a manual "Analizza" tap.
"""

from __future__ import annotations

import app.api.routes as routes
import app.services.sync_state as sync_state


def test_second_ingest_within_window_is_skipped(client, monkeypatch, caplog):
    calls = {"n": 0}
    real_ingest_runs = routes.ingest_runs

    def _counting_ingest_runs(*args, **kwargs):
        calls["n"] += 1
        return real_ingest_runs(*args, **kwargs)

    monkeypatch.setattr(routes, "ingest_runs", _counting_ingest_runs)

    resp1 = client.post("/api/ingest")
    assert resp1.status_code == 200
    assert calls["n"] == 1

    with caplog.at_level("INFO", logger="app.api"):
        resp2 = client.post("/api/ingest")
    assert resp2.status_code == 200
    assert calls["n"] == 1  # second call skipped the real fetch
    assert any("skipped, recent" in r.message for r in caplog.records)
    # Still returns the known activities, not an empty list.
    assert len(resp2.json()) == len(resp1.json())


def test_ingest_auto_generates_report_without_manual_analyze(client):
    resp = client.post("/api/ingest")
    assert resp.status_code == 200
    assert len(resp.json()) > 0

    reports = client.get("/api/reports").json()
    assert len(reports) >= 1
    assert reports[0]["scope"] == "single"


def test_second_ingest_with_no_new_activity_does_not_duplicate_reports(
    client, monkeypatch
):
    """Bypass the recency guard (simulating >10min later) with the same demo
    data: no new activity arrives, so no extra report should be generated.
    """
    client.post("/api/ingest")
    reports_after_first = client.get("/api/reports").json()

    monkeypatch.setattr(sync_state, "should_skip_ingest", lambda *a, **k: False)
    resp = client.post("/api/ingest")
    assert resp.status_code == 200
    reports_after_second = client.get("/api/reports").json()
    assert len(reports_after_second) == len(reports_after_first)
