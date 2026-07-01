"""Unit tests for the Workout Execution Score engine (Roadmap #9)."""

from __future__ import annotations

from app.processing import score_execution
from app.schemas import PlanSessionOut, RunSummary


def _sess(session_type: str, km: float | None = None, dur: float | None = None, pace=None):
    return PlanSessionOut(
        id=1,
        day_of_week=0,
        session_type=session_type,
        title=f"{session_type}",
        target_distance_km=km,
        target_pace=pace,
        target_duration_min=dur,
        completed=False,
    )


def _run(activity_type: str, km: float = 0.0, dur: float = 0.0, pace=None, rpe=None):
    return RunSummary(
        date="2026-06-22",
        activity_type=activity_type,
        distance_km=km,
        duration_min=dur,
        avg_pace=pace,
        rpe=rpe,
    )


def test_skipped_when_no_activity():
    r = score_execution(_sess("easy", km=8.0), None, "2026-06-22")
    assert r.execution_status == "skipped"
    assert r.execution_score == 0.0


def test_completed_well_on_match():
    r = score_execution(_sess("easy", km=8.0), _run("easy", km=8.0, dur=48.0), "2026-06-22")
    assert r.execution_status == "completed_well"
    assert r.execution_score >= 75


def test_too_short():
    r = score_execution(_sess("long", km=20.0), _run("lungo", km=10.0), "2026-06-22")
    assert r.execution_status == "too_short"
    assert r.execution_score < 60


def test_turned_easy_when_quality_run_easy():
    r = score_execution(_sess("intervals", km=10.0), _run("easy", km=10.0), "2026-06-22")
    assert r.execution_status == "turned_easy"


def test_too_hard_on_easy_day():
    r = score_execution(_sess("easy", km=8.0), _run("intervalli", km=8.0), "2026-06-22")
    assert r.execution_status == "too_hard"


def test_volume_excess():
    r = score_execution(_sess("easy", km=6.0), _run("easy", km=12.0), "2026-06-22")
    assert r.execution_status == "volume_excess"


def test_rpe_flags_hard_easy_day():
    r = score_execution(
        _sess("easy", km=8.0), _run("easy", km=8.0, rpe=9), "2026-06-22"
    )
    assert any("RPE" in e for e in r.evidence)


def test_evidence_present():
    r = score_execution(_sess("tempo", km=10.0), _run("tempo", km=10.0), "2026-06-22")
    assert r.evidence
    assert r.plan_session_id == 1
