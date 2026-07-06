"""Live GPS run ingest (G1 milestone M1 / Passo 18).

The phone's offline queue POSTs a finished recording to /api/activities/live;
the server synthesizes splits/pace/HR and reuses upsert_activity. The critical
property is idempotency on ``live_id``: the queue retries after any network
hiccup and must never duplicate the run.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select

from app.db.models import Activity
from app.processing.live import derive_avg_pace, derive_hr, derive_splits
from app.schemas import LiveLap, LiveRunIn, LiveSample
from app.services.live_import import import_live_run

TODAY = date.today().isoformat()


def _samples_constant(pace_s_per_km: float, km: float, step_s: float = 30.0):
    """Cumulative samples at constant pace."""
    out, t = [], 0.0
    total_s = pace_s_per_km * km
    while t <= total_s:
        out.append(LiveSample(t=t, d=t / pace_s_per_km))
        t += step_s
    return out


# ── Pure synthesis ───────────────────────────────────────────────────────────


def test_splits_constant_pace():
    samples = _samples_constant(300.0, 3.0)  # 5:00/km for 3 km
    assert derive_splits(samples, [], 3.0) == ["5:00", "5:00", "5:00"]


def test_splits_negative_split_interpolated():
    # km 1 at 300s, km 2 at 240s: piecewise-linear samples at the km marks.
    samples = [LiveSample(t=0, d=0), LiveSample(t=300, d=1.0), LiveSample(t=540, d=2.0)]
    assert derive_splits(samples, [], 2.0) == ["5:00", "4:00"]


def test_splits_fall_back_to_laps_without_samples():
    laps = [LiveLap(t=0, d=0), LiveLap(t=290, d=1.0), LiveLap(t=590, d=2.0)]
    assert derive_splits([], laps, 2.0) == ["4:50", "5:00"]


def test_splits_none_for_short_or_empty():
    assert derive_splits([], [], 5.0) is None
    assert derive_splits(_samples_constant(300.0, 0.8), [], 0.8) is None


def test_splits_ignore_gps_jitter_backwards_points():
    samples = [LiveSample(t=0, d=0), LiveSample(t=150, d=0.6),
               LiveSample(t=160, d=0.5),  # jitter: distance went backwards
               LiveSample(t=300, d=1.0), LiveSample(t=600, d=2.0)]
    assert derive_splits(samples, [], 2.0) == ["5:00", "5:00"]


def test_avg_pace_and_hr():
    assert derive_avg_pace(10.0, 50.0) == "5:00/km"
    assert derive_avg_pace(0.0, 50.0) is None
    avg, mx = derive_hr([LiveSample(t=0, d=0, hr=140), LiveSample(t=30, d=0.1, hr=160)])
    assert (avg, mx) == (150, 160)
    assert derive_hr([LiveSample(t=0, d=0)]) == (None, None)


# ── Service: persistence + idempotency ───────────────────────────────────────


def _payload(**kw) -> LiveRunIn:
    base = dict(
        live_id="run-abc-123", date=TODAY, start_time="07:15",
        duration_min=25.0, distance_km=5.0,
        samples=_samples_constant(300.0, 5.0),
        route_polyline="encoded~poly",
        name="Corsa live",
    )
    base.update(kw)
    return LiveRunIn(**base)


def test_import_creates_activity_with_synthesis(session):
    a = import_live_run(session, _payload())
    assert a.live_id == "run-abc-123" and a.sport == "run"
    assert a.avg_pace == "5:00/km"
    assert a.splits_km == ["5:00"] * 5
    assert a.route_polyline == "encoded~poly"
    assert a.start_time == "07:15"


def test_import_is_idempotent_on_live_id(session):
    import_live_run(session, _payload(distance_km=5.0, duration_min=25.0))
    # The queue retries the same upload with a corrected payload.
    import_live_run(session, _payload(distance_km=5.2, duration_min=26.0))
    rows = session.scalars(
        select(Activity).where(Activity.live_id == "run-abc-123")
    ).all()
    assert len(rows) == 1 and rows[0].distance_km == 5.2


def test_import_long_run_inferred(session):
    a = import_live_run(session, _payload(
        live_id="long-1", distance_km=16.0, duration_min=96.0,
        samples=[], laps=[],
    ))
    assert a.activity_type == "lungo"
    assert a.splits_km is None  # no series → no invented splits
    assert a.avg_pace == "6:00/km"


# ── Endpoint: retry-safe + pipeline ──────────────────────────────────────────


def test_endpoint_created_and_retry_does_not_duplicate(client):
    body = {
        "live_id": "queue-1", "date": TODAY, "start_time": "18:00",
        "duration_min": 30.0, "distance_km": 6.0,
        "samples": [{"t": i * 60, "d": i * 0.2} for i in range(31)],
        "laps": [], "route_polyline": None, "name": None,
    }
    r1 = client.post("/api/activities/live", json=body)
    assert r1.status_code == 201, r1.text
    r2 = client.post("/api/activities/live", json=body)  # WorkManager retry
    assert r2.status_code == 201
    assert r2.json()["id"] == r1.json()["id"]  # same row, no duplicate

    acts = client.get("/api/activities").json()
    assert sum(1 for a in acts if a.get("live_id") == "queue-1") == 1


def test_endpoint_refreshes_decision(client):
    body = {
        "live_id": "queue-2", "date": TODAY,
        "duration_min": 25.0, "distance_km": 5.0,
        "samples": [], "laps": [],
    }
    assert client.post("/api/activities/live", json=body).status_code == 201
    decision = client.get("/api/coach/today").json()
    assert decision["date"] == TODAY  # pipeline ran and persisted a decision
