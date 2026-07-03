"""LLM voice for the daily note (Roadmap A1 / Passo 11).

Deterministic tests inject a fake ``call_fn`` so every guard is exercised
without the network. A nightly ``eval_llm`` golden hits the real model and
asserts the acceptance property: 14 simulated days → 14 distinct notes.
"""

from __future__ import annotations

import os
from datetime import date, timedelta

import pytest

from app.coaching.verbalizer import verbalize_decision
from app.schemas import CoachDecision


def _decision(note: str = "Corri piano oggi.", **kw) -> CoachDecision:
    base = dict(
        date="2026-06-24",
        decision="easy",
        headline="Facile 8 km",
        prescription="8 km facili a 5:30/km",
        rationale="Recupero dopo la qualita di ieri.",
        daily_note=note,
        confidence="medium",
    )
    base.update(kw)
    return CoachDecision(**base)


def test_disabled_returns_template(monkeypatch):
    # No call_fn and verbalizer disabled (test default) → template, no network.
    d = _decision("Nota template.")
    assert verbalize_decision(d, []) == "Nota template."


def test_rewrite_accepted_when_clean():
    d = _decision("Corri piano oggi.")
    clean = "Gambe leggere, testa serena: goditi il facile."
    assert verbalize_decision(d, [], call_fn=lambda s, u: clean) == clean


def test_invented_number_is_rejected():
    d = _decision("Corri piano oggi.")  # allowed numbers: 8, 5:30, 5, 30, 2026-06-24...
    out = verbalize_decision(d, [], call_fn=lambda s, u: "Spingi forte per 42 km oggi.")
    assert out == "Corri piano oggi."  # 42 not in the decision → fall back


def test_number_from_decision_is_allowed():
    d = _decision("Corri piano oggi.")
    out = verbalize_decision(d, [], call_fn=lambda s, u: "Solo 8 km, senza fretta.")
    assert out == "Solo 8 km, senza fretta."  # 8 is in the prescription


def test_repetition_is_rejected():
    d = _decision("Corri piano oggi.")
    recent = ["Gambe leggere oggi."]
    out = verbalize_decision(d, recent, call_fn=lambda s, u: "gambe   leggere OGGI")
    assert out == "Corri piano oggi."  # normalised match → fall back


def test_trimmed_to_two_sentences():
    d = _decision("Corri piano oggi.")
    out = verbalize_decision(
        d, [], call_fn=lambda s, u: "Prima frase. Seconda frase. Terza di troppo."
    )
    assert out == "Prima frase. Seconda frase."


def test_model_error_falls_back():
    d = _decision("Nota sicura.")

    def _boom(s, u):
        raise TimeoutError("slow model")

    assert verbalize_decision(d, [], call_fn=_boom) == "Nota sicura."


def test_empty_answer_falls_back():
    d = _decision("Nota sicura.")
    assert verbalize_decision(d, [], call_fn=lambda s, u: "   ") == "Nota sicura."


# ── Nightly golden: real LLM, 14 distinct notes ──────────────────────────────

pytestmark_llm = pytest.mark.eval_llm
_HAS_KEY = bool(os.environ.get("ANTHROPIC_API_KEY"))


@pytest.mark.eval_llm
@pytest.mark.skipif(not _HAS_KEY, reason="ANTHROPIC_API_KEY not set")
def test_fourteen_days_all_distinct(monkeypatch):
    """14 days → 14 distinct notes (acceptance). Feeds each day's note back as
    'recent' so the model must keep varying."""
    monkeypatch.setenv("VERBALIZER_ENABLED", "true")
    from app.config import get_settings

    get_settings.cache_clear()

    notes: list[str] = []
    for i in range(14):
        d = _decision(
            note="Corri facile, costruisci il fondo.",
            date=(date(2026, 6, 1) + timedelta(days=i)).isoformat(),
        )
        notes.append(verbalize_decision(d, notes[-14:]))
    assert len(set(notes)) == 14, f"repeated notes: {notes}"
