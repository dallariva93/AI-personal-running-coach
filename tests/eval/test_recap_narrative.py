"""LLM voice for shareable recaps (Roadmap A6 / Passo 15).

Deterministic tests inject a fake ``call_fn`` so every guard is exercised
without the network — same discipline as ``test_verbalizer.py`` (A1). A
nightly ``eval_llm`` golden hits the real model.
"""

from __future__ import annotations

import os

import pytest

from app.coaching.recap_narrative import build_race_narrative, build_weekly_narrative
from app.processing.recap import RaceRecapFacts, WeeklyRecapFacts


def _weekly(**kw) -> WeeklyRecapFacts:
    base = dict(
        week_start="2026-06-15", week_end="2026-06-21", distance_km=35.0,
        runs_count=4, adherence_pct=90.0, avg_execution_score=82.0,
        best_moment="Il lungo da 18 km",
    )
    base.update(kw)
    return WeeklyRecapFacts(**base)


def _race(**kw) -> RaceRecapFacts:
    base = dict(
        activity_id=1, date="2026-06-21", distance_km=10.0, actual_time="42:00",
        actual_seconds=2520.0, predicted_time="42:30", predicted_seconds=2550.0,
        delta_seconds=-30.0, delta_label="30s più veloce del previsto",
        splits_km=["4:10"] * 10,
    )
    base.update(kw)
    return RaceRecapFacts(**base)


# ── Weekly narrative guards ───────────────────────────────────────────────────


def test_weekly_disabled_returns_template(monkeypatch):
    f = _weekly()
    out = build_weekly_narrative(f)
    assert "35" in out and out  # template, no network


def test_weekly_rewrite_accepted_when_clean():
    f = _weekly()
    clean = "Settimana solida da 35 km: il lungo da 18 km è stato il momento migliore."
    assert build_weekly_narrative(f, call_fn=lambda s, u: clean) == clean


def test_weekly_invented_number_is_rejected():
    f = _weekly()
    out = build_weekly_narrative(f, call_fn=lambda s, u: "Settimana pazzesca da 99 km!")
    assert "99" not in out  # falls back to the template


def test_weekly_number_from_facts_is_allowed():
    f = _weekly()
    out = build_weekly_narrative(f, call_fn=lambda s, u: "35 km in 4 uscite, gran lavoro.")
    assert out == "35 km in 4 uscite, gran lavoro."


def test_weekly_trimmed_to_two_sentences():
    f = _weekly()
    out = build_weekly_narrative(
        f, call_fn=lambda s, u: "Prima frase. Seconda frase. Terza di troppo."
    )
    assert out == "Prima frase. Seconda frase."


def test_weekly_model_error_falls_back():
    f = _weekly()

    def _boom(s, u):
        raise TimeoutError("slow model")

    out = build_weekly_narrative(f, call_fn=_boom)
    assert "35" in out


def test_weekly_empty_answer_falls_back():
    f = _weekly()
    out = build_weekly_narrative(f, call_fn=lambda s, u: "   ")
    assert "35" in out


# ── Race narrative guards ─────────────────────────────────────────────────────


def test_race_rewrite_accepted_when_clean():
    f = _race()
    clean = "10 km in 42:00, 30s più veloce del previsto: fantastico!"
    assert build_race_narrative(f, call_fn=lambda s, u: clean) == clean


def test_race_invented_number_is_rejected():
    f = _race()
    out = build_race_narrative(f, call_fn=lambda s, u: "Un tempo di 99:99, incredibile!")
    assert "99:99" not in out


def test_race_number_from_facts_is_allowed():
    f = _race()
    out = build_race_narrative(f, call_fn=lambda s, u: "Chiuso in 42:00, ottimo lavoro.")
    assert out == "Chiuso in 42:00, ottimo lavoro."


def test_race_model_error_falls_back():
    f = _race()

    def _boom(s, u):
        raise TimeoutError("slow model")

    out = build_race_narrative(f, call_fn=_boom)
    assert "42:00" in out


# ── Nightly golden: real LLM ──────────────────────────────────────────────────

_HAS_KEY = bool(os.environ.get("ANTHROPIC_API_KEY"))


@pytest.mark.eval_llm
@pytest.mark.skipif(not _HAS_KEY, reason="ANTHROPIC_API_KEY not set")
def test_weekly_narrative_golden(monkeypatch):
    monkeypatch.setenv("VERBALIZER_ENABLED", "true")
    from app.config import get_settings

    get_settings.cache_clear()
    out = build_weekly_narrative(_weekly())
    assert out and "99" not in out


@pytest.mark.eval_llm
@pytest.mark.skipif(not _HAS_KEY, reason="ANTHROPIC_API_KEY not set")
def test_race_narrative_golden(monkeypatch):
    monkeypatch.setenv("VERBALIZER_ENABLED", "true")
    from app.config import get_settings

    get_settings.cache_clear()
    out = build_race_narrative(_race())
    assert out
