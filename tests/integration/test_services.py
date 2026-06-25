"""Integration tests for the orchestration service layer."""

from __future__ import annotations

from datetime import date

from app.coaching.coach import OfflineCoach
from app.db.models import Activity, CoachingReport
from app.services import ingest_runs, list_activities, run_single_analysis, run_weekly_plan

REF = date(2026, 6, 22)


def test_ingest_persists_only_runs(session, demo_source):
    saved = ingest_runs(session, limit=20, source=demo_source)
    session.commit()
    # fixture has 10 activities, one is cycling -> 9 runs
    assert len(saved) == 9
    assert all(isinstance(a, Activity) for a in saved)
    assert all(a.activity_type != "cycling" for a in saved)


def test_ingest_is_idempotent(session, demo_source):
    ingest_runs(session, limit=20, source=demo_source)
    session.commit()
    ingest_runs(session, limit=20, source=demo_source)
    session.commit()
    assert len(list_activities(session, limit=100)) == 9


def test_single_analysis_creates_report(session, demo_source):
    ingest_runs(session, limit=20, source=demo_source)
    session.commit()
    report = run_single_analysis(session, coach=OfflineCoach(), ref=REF)
    session.commit()
    assert isinstance(report, CoachingReport)
    assert report.scope == "single"
    assert report.analysis
    assert report.next_workout
    assert report.metrics["form_state"] in {
        "fresh", "balanced", "fatigued", "detraining", "unknown"
    }


def test_weekly_plan_creates_report(session, demo_source):
    ingest_runs(session, limit=20, source=demo_source)
    session.commit()
    report = run_weekly_plan(session, coach=OfflineCoach(), ref=REF)
    session.commit()
    assert report.scope == "weekly"
    assert report.metrics["acute_load_km"] >= 0


def test_analysis_without_data_raises(session, demo_source):
    import pytest

    with pytest.raises(ValueError):
        run_single_analysis(session, coach=OfflineCoach(), ref=REF, source=demo_source)
