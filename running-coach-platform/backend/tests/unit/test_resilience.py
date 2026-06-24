"""Unit tests for resilience: retry logic and AI→offline fallback."""

from __future__ import annotations

import pytest

from app.coaching.coach import AICoach
from app.config import Settings
from app.exceptions import CoachingError
from app.schemas import RunSummary, TrainingMetrics
from app.utils import retry_call


def test_retry_call_succeeds_after_failures():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ValueError("boom")
        return "ok"

    assert retry_call(flaky, retries=3, base_delay=0) == "ok"
    assert calls["n"] == 3


def test_retry_call_reraises_after_exhaustion():
    def always_fail():
        raise RuntimeError("nope")

    with pytest.raises(RuntimeError):
        retry_call(always_fail, retries=2, base_delay=0)


def _settings(**kw) -> Settings:
    base = dict(anthropic_api_key="test-key", ai_max_retries=1, ai_timeout_seconds=1)
    base.update(kw)
    return Settings(**base)


def _patch_failing_client(coach: AICoach):
    class _Boom:
        class messages:  # noqa: N801
            @staticmethod
            def create(**_kw):
                raise RuntimeError("API down")

    coach._client = _Boom()
    return coach


def test_ai_coach_falls_back_to_offline_on_failure():
    coach = AICoach(_settings(ai_fallback_offline=True))
    _patch_failing_client(coach)
    run = RunSummary(date="2026-06-20", activity_type="easy", distance_km=8, duration_min=45)
    metrics = TrainingMetrics(form_state="balanced", form_explanation="ok")
    result = coach.analyze_run(run, [], metrics)
    assert "fallback" in result.model
    assert result.analysis  # offline coach produced content


def test_ai_coach_raises_when_fallback_disabled():
    coach = AICoach(_settings(ai_fallback_offline=False))
    _patch_failing_client(coach)
    run = RunSummary(date="2026-06-20", activity_type="easy", distance_km=8, duration_min=45)
    with pytest.raises(CoachingError):
        coach.analyze_run(run, [], TrainingMetrics(form_state="balanced", form_explanation="ok"))


def test_ai_coach_weekly_fallback():
    coach = AICoach(_settings(ai_fallback_offline=True))
    _patch_failing_client(coach)
    metrics = TrainingMetrics(form_state="balanced", form_explanation="ok", chronic_load_km=40)
    result = coach.plan_week([], metrics, [])
    assert "fallback" in result.model
    assert result.scope == "weekly"
