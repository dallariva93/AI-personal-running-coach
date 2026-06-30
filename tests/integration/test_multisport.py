"""Feature 24 — multi-sport (bike/swim/strength) ingest and isolation."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from app.collection.sources import DemoSource
from app.db.models import Activity
from app.services import ingest_cross_training, ingest_runs, list_cross_training
from app.services.ingest import _all_summaries

FIXTURES = Path(__file__).parent.parent / "fixtures"
DEMO_CROSS = Path(__file__).parent.parent.parent / "data" / "demo_cross_training.json"


def _cross_source() -> DemoSource:
    """Demo source whose runs come from the test fixture and cross-training
    from the bundled demo file."""
    return DemoSource(FIXTURES / "garmin_activities.json", DEMO_CROSS)


def test_ingest_cross_training_persists_bike_swim_strength(session):
    source = _cross_source()
    saved = ingest_cross_training(session, source=source)
    sports = {a.sport for a in saved}
    assert sports == {"bike", "swim", "strength"}
    # Strength has no distance; bike/swim do.
    strength = next(a for a in saved if a.sport == "strength")
    assert strength.distance_km == 0.0
    bike = next(a for a in saved if a.sport == "bike")
    assert bike.distance_km > 0


def test_cross_training_excluded_from_running_pipeline(session):
    source = _cross_source()
    ingest_runs(session, source=source)
    ingest_cross_training(session, source=source)
    session.flush()

    # The running summaries must contain zero cross-training rows.
    summaries = _all_summaries(session)
    assert summaries  # there are runs
    assert all(s.sport == "run" for s in summaries)

    # But the rows do live in the table.
    all_rows = session.scalars(select(Activity)).all()
    assert any(a.sport == "bike" for a in all_rows)


def test_list_cross_training_returns_only_cross_training(session):
    source = _cross_source()
    ingest_runs(session, source=source)
    ingest_cross_training(session, source=source)
    session.flush()

    rows = list_cross_training(session)
    assert rows
    assert all(a.sport != "run" for a in rows)


def test_cross_training_endpoints(client):
    # Manual Garmin sync (demo mode → demo cross-training data).
    resp = client.post("/api/ingest/cross-training")
    assert resp.status_code == 200
    saved = resp.json()
    assert {a["sport"] for a in saved} == {"bike", "swim", "strength"}

    # Listing returns them and excludes runs.
    listed = client.get("/api/activities/cross-training").json()
    assert all(a["sport"] != "run" for a in listed)

    # The running activities list must NOT include cross-training.
    runs = client.get("/api/activities").json()
    assert all(a["sport"] == "run" for a in runs)
