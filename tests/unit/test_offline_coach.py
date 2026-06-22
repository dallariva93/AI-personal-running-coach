"""Unit tests for the offline (rule-based) coach and section parsing."""

from __future__ import annotations

from app.coaching.coach import OfflineCoach, _split_sections, get_coach
from app.schemas import RunSummary, TrainingMetrics


def test_split_sections():
    text = "## Analisi\nVa bene.\n## Prossimo allenamento\n8 km easy."
    analysis, nxt = _split_sections(text)
    assert analysis == "Va bene."
    assert nxt == "8 km easy."


def test_get_coach_offline_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from app.config import get_settings

    get_settings.cache_clear()
    coach = get_coach()
    assert isinstance(coach, OfflineCoach)
    get_settings.cache_clear()


def test_offline_recovery_after_hard_run():
    coach = OfflineCoach()
    run = RunSummary(date="2026-06-20", activity_type="intervalli", distance_km=10, duration_min=55)
    metrics = TrainingMetrics(form_state="balanced", form_explanation="ok")
    result = coach.analyze_run(run, [], metrics)
    assert result.scope == "single"
    assert result.model == "offline-rules"
    assert "ecupero" in result.next_workout or "asy" in result.next_workout


def test_offline_backs_off_when_fatigued():
    coach = OfflineCoach()
    run = RunSummary(date="2026-06-20", activity_type="easy", distance_km=8, duration_min=45)
    metrics = TrainingMetrics(form_state="fatigued", form_explanation="ACWR alto", acwr=1.7)
    result = coach.analyze_run(run, [], metrics)
    assert "ecupero" in result.next_workout.lower() or "riposo" in result.next_workout.lower()


def test_offline_weekly_plan_has_sessions():
    coach = OfflineCoach()
    metrics = TrainingMetrics(
        form_state="balanced", form_explanation="ok", chronic_load_km=40, acute_load_km=42
    )
    result = coach.plan_week([], metrics, [])
    assert result.scope == "weekly"
    assert result.next_workout.count("-") >= 4  # multiple session bullet points
