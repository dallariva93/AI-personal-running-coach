"""Health Connect MVP import (Roadmap A2 / Passo 14).

The no-Garmin path: a running session (and sleep/HRV) POSTed from the Android
Health Connect worker must appear as an activity with a derived pace, an
inferred type and a refreshed decision — and wellness must honour the A4 source
precedence. Deterministic, offline.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select

from app.db.models import Activity, DailyCheckinRow
from app.schemas import (
    DailyCheckin,
    HealthConnectImportIn,
    HealthConnectRun,
    HealthConnectWellness,
)
from app.services.checkin import save_checkin
from app.services.health_connect import (
    _derive_pace,
    _run_to_summary,
    import_health_connect,
)

TODAY = date.today().isoformat()


def _run(**kw) -> HealthConnectRun:
    base = dict(health_connect_id="hc-1", date=TODAY, duration_min=50.0, distance_km=10.0)
    base.update(kw)
    return HealthConnectRun(**base)


# ── Pure helpers ─────────────────────────────────────────────────────────────


def test_derive_pace():
    assert _derive_pace(10.0, 50.0) == "5:00/km"
    assert _derive_pace(0.0, 50.0) is None
    assert _derive_pace(10.0, 0.0) is None


def test_run_to_summary_infers_type_and_pace():
    s = _run_to_summary(_run(distance_km=16.0, duration_min=96.0))
    assert s.activity_type == "lungo"  # >=14 km → long run
    assert s.avg_pace == "6:00/km"
    assert s.sport == "run"
    assert s.health_connect_id == "hc-1"


def test_run_to_summary_hr_from_samples():
    s = _run_to_summary(_run(hr_samples=[140, 150, 160]))
    assert s.avg_hr == 150 and s.max_hr == 160


def test_run_to_summary_explicit_hr_wins():
    s = _run_to_summary(_run(avg_hr=145, max_hr=170, hr_samples=[100, 100]))
    assert s.avg_hr == 145 and s.max_hr == 170


# ── Persistence path ─────────────────────────────────────────────────────────


def test_import_creates_activity(session):
    acts, wellness = import_health_connect(
        session, HealthConnectImportIn(runs=[_run()])
    )
    assert wellness == 0 and len(acts) == 1
    row = session.scalar(select(Activity).where(Activity.health_connect_id == "hc-1"))
    assert row is not None and row.avg_pace == "5:00/km" and row.sport == "run"


def test_import_dedupes_on_health_connect_id(session):
    import_health_connect(session, HealthConnectImportIn(runs=[_run(distance_km=10.0)]))
    # Same id, corrected distance → updates the same row, no duplicate.
    import_health_connect(session, HealthConnectImportIn(runs=[_run(distance_km=12.0)]))
    rows = session.scalars(
        select(Activity).where(Activity.health_connect_id == "hc-1")
    ).all()
    assert len(rows) == 1 and rows[0].distance_km == 12.0


def test_import_wellness_source_health_connect(session):
    _, wellness = import_health_connect(
        session,
        HealthConnectImportIn(
            wellness=[HealthConnectWellness(date=TODAY, sleep_h=7.5, hrv_rmssd=58.0)]
        ),
    )
    assert wellness == 1
    row = session.scalar(select(DailyCheckinRow).where(DailyCheckinRow.date == TODAY))
    assert row.source == "health_connect" and row.hrv_rmssd == 58.0


def test_wellness_does_not_overwrite_voice(session):
    # A voice debrief already recorded fatigue today (A4 precedence).
    save_checkin(session, DailyCheckin(date=TODAY, fatigue=8, source="voice"))
    import_health_connect(
        session,
        HealthConnectImportIn(
            wellness=[HealthConnectWellness(date=TODAY, sleep_h=6.0, hrv_rmssd=40.0)]
        ),
    )
    row = session.scalar(select(DailyCheckinRow).where(DailyCheckinRow.date == TODAY))
    assert row.source == "voice" and row.fatigue == 8  # not clobbered
    assert row.hrv_rmssd == 40.0  # but the empty HRV gap was filled


def test_empty_wellness_row_skipped(session):
    _, wellness = import_health_connect(
        session, HealthConnectImportIn(wellness=[HealthConnectWellness(date=TODAY)])
    )
    assert wellness == 0


# ── HTTP endpoint ────────────────────────────────────────────────────────────


def test_endpoint_imports_and_refreshes(client):
    resp = client.post(
        "/api/import/health-connect",
        json={
            "runs": [{
                "health_connect_id": "hc-http-1", "date": TODAY,
                "duration_min": 40.0, "distance_km": 8.0, "name": "Corsa mattutina",
            }],
            "wellness": [{"date": TODAY, "sleep_h": 8.0}],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["imported"] == 1 and body["wellness_days"] == 1
    assert body["activities"][0]["avg_pace"] == "5:00/km"
    assert body["activities"][0]["health_connect_id"] == "hc-http-1"
