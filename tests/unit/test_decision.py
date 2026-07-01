"""Unit tests for the Coach Decision Engine (Roadmap #7)."""

from __future__ import annotations

from datetime import date

from app.processing import decide_today
from app.schemas import DailyCheckin, PlanSessionOut, TrainingMetrics

REF = date(2026, 6, 22)


def _session(session_type: str, **kw) -> PlanSessionOut:
    return PlanSessionOut(
        id=kw.get("id", 1),
        day_of_week=REF.weekday(),
        session_type=session_type,
        title=kw.get("title", f"Sessione {session_type}"),
        description=kw.get("description"),
        target_distance_km=kw.get("target_distance_km"),
        target_pace=kw.get("target_pace"),
        target_duration_min=kw.get("target_duration_min"),
        completed=False,
    )


def _checkin() -> DailyCheckin:
    return DailyCheckin(date=REF.isoformat(), sleep_h=8.0, fatigue=2, hrv_rmssd=60.0)


def test_no_plan_healthy_defaults_to_easy():
    m = TrainingMetrics(tsb=0.0, acwr=1.0, injury_level="low", readiness_state="green")
    d = decide_today(m, None, None, _checkin(), ref=REF)
    assert d.decision == "easy"
    assert d.headline
    assert d.signals  # engine always explains itself


def test_very_fresh_no_plan_suggests_quality():
    m = TrainingMetrics(tsb=20.0, acwr=0.9, injury_level="low", readiness_state="green")
    d = decide_today(m, None, None, _checkin(), ref=REF)
    assert d.decision == "quality"
    assert d.session_type == "tempo"


def test_high_injury_forces_rest():
    m = TrainingMetrics(tsb=-5.0, acwr=1.2, injury_level="high")
    d = decide_today(m, None, None, None, ref=REF)
    assert d.decision == "rest"
    assert any("infortun" in f.lower() for f in d.safety_flags)


def test_hard_session_downgraded_when_readiness_red():
    m = TrainingMetrics(tsb=-10.0, acwr=1.3, injury_level="low", readiness_state="red")
    d = decide_today(m, None, _session("intervals", title="8x400"), None, ref=REF)
    assert d.decision == "modify"
    assert d.session_type == "easy"  # downgraded
    assert d.safety_flags


def test_planned_session_followed_when_healthy():
    m = TrainingMetrics(tsb=2.0, acwr=1.0, injury_level="low", readiness_state="green")
    sess = _session("tempo", title="Medio 8 km", target_distance_km=8.0)
    d = decide_today(m, None, sess, _checkin(), ref=REF)
    assert d.decision == "quality"
    assert d.plan_session_id == sess.id
    assert d.target_distance_km == 8.0


def test_rest_day_is_respected():
    m = TrainingMetrics(tsb=5.0, acwr=1.0, injury_level="low")
    d = decide_today(m, None, _session("rest", title="Riposo"), _checkin(), ref=REF)
    assert d.decision == "rest"


def test_confidence_drops_with_missing_data():
    m = TrainingMetrics(tsb=0.0, acwr=1.0, injury_level="low")
    # No checkin, no HRV, no plan → 3 missing signals → low confidence.
    d = decide_today(m, None, None, None, ref=REF)
    assert d.confidence == "low"
    assert len(d.missing_data) >= 3


def test_high_acwr_raises_safety_flag():
    m = TrainingMetrics(tsb=-5.0, acwr=1.7, injury_level="low", readiness_state="green")
    d = decide_today(m, None, None, _checkin(), ref=REF)
    assert any("ACWR" in f for f in d.safety_flags)
