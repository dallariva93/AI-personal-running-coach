"""Pre-plan chat: negotiation prompt + fixed-session constraints (plan chat fix)."""

from __future__ import annotations

import json

from app.coaching import prompts
from app.coaching.coach import AICoach
from app.schemas import PlanGenerateRequest


def test_plan_chat_prompt_has_negotiation_and_categories():
    p = prompts.PLAN_CHAT_SYSTEM_PROMPT
    # The four constraint categories are spelled out.
    assert "FATTI ESTERNI" in p
    assert "PREFERENZE" in p
    assert "SCELTE DISCREZIONALI" in p
    assert "OBIETTIVI IN CONFLITTO" in p
    # Safety rules gate the closure, and the heavy-week explicit confirmation exists.
    assert "REGOLE DI SICUREZZA" in p
    assert "conferma esplicita" in p
    # Token-efficient batching directive (superseded by the confirmation budget).
    assert "Accorpa TUTTO" in p
    # Sentinels + the new structured context fields the fix introduces.
    assert "§CTX§" in p and "§/CTX§" in p and "§READY§" in p
    assert "fixed_sessions" in p
    assert "constraints" in p
    assert "overrides" in p


def test_plan_chat_prompt_batches_confirmations_and_contracts_week():
    p = prompts.PLAN_CHAT_SYSTEM_PROMPT
    # Hard confirmation budget: at most two confirmation messages, batched.
    assert "BUDGET DI CONFERME" in p
    assert "MASSIMO" in p and "DUE" in p
    assert "CHIUDI SUBITO" in p
    # The agreed week is a contract mirrored into the context verbatim.
    assert "week_structure" in p
    assert "GIORNO PER GIORNO" in p
    assert '"rest"' in p  # rest days are explicit in the 7-day structure


def test_multiweek_prompt_honors_fixed_sessions():
    p = prompts.MULTIWEEK_PLAN_SYSTEM_PROMPT
    assert "VINCOLI DELL'ATLETA" in p
    assert "fixed_sessions" in p
    assert "NON spostarle" in p or "non spostarle" in p.lower()
    # The agreed week is a per-week contract for the generator too.
    assert "week_structure" in p
    assert "CONTRATTO" in p


def test_build_message_injects_fixed_sessions_as_hard_constraints():
    ctx = json.dumps(
        {
            "weekly_km": 45,
            "threshold_pace": "4:30/km",
            "fixed_sessions": [
                {"day": "mar", "type": "intervals", "note": "run club"},
                {"day": "gio", "type": "race", "pace": "4:30/km", "note": "Summer Run Padova"},
                {"day": "dom", "type": "long", "note": "14-18 km"},
            ],
            "constraints": ["max 1h a sessione"],
        }
    )
    req = PlanGenerateRequest(
        goal_type="half",
        goal_date="2026-09-20",
        level="intermediate",
        runner_context=ctx,
    )
    msg = prompts.build_multiweek_plan_message(req, profile=None, metrics=None)
    assert "PRIORITÀ MASSIMA" in msg
    assert "fixed_sessions" in msg
    assert "NON spostarle" in msg
    # The athlete's actual commitments travel into the generation payload.
    assert "run club" in msg
    assert "Summer Run Padova" in msg


def test_build_message_without_context_has_no_constraint_block():
    req = PlanGenerateRequest(goal_type="10k", goal_date="2026-09-20")
    msg = prompts.build_multiweek_plan_message(req, profile=None, metrics=None)
    assert "PRIORITÀ MASSIMA" not in msg


def test_chat_for_plan_parses_richer_context(monkeypatch):
    """The §CTX§ block now carries fixed_sessions/constraints and still parses."""
    ctx_obj = {
        "weekly_km": 45,
        "threshold_pace": "4:30/km",
        "easy_pace": "5:40/km",
        "fixed_sessions": [{"day": "mar", "type": "intervals", "note": "run club"}],
        "constraints": ["il lunedì non corro"],
        "overrides": [],
        "notes": "",
    }
    raw = (
        "Perfetto, ecco il riepilogo: martedì ripetute col gruppo, domenica lungo.\n"
        "§CTX§\n" + json.dumps(ctx_obj) + "\n§/CTX§\n§READY§"
    )
    coach = AICoach()
    monkeypatch.setattr(coach, "_call_chat", lambda system, messages: raw)

    message, is_complete, runner_context = coach.chat_for_plan(
        [{"role": "user", "content": "faccio ripetute il martedì col gruppo"}]
    )
    assert is_complete is True
    # Sentinels stripped from the visible message.
    assert "§CTX§" not in message and "§READY§" not in message
    assert "riepilogo" in message.lower()
    # The structured context survives and carries the fixed sessions.
    parsed = json.loads(runner_context)
    assert parsed["fixed_sessions"][0]["day"] == "mar"
    assert parsed["constraints"] == ["il lunedì non corro"]


def test_chat_for_plan_intermediate_turn_not_complete(monkeypatch):
    """A normal negotiation turn (no §READY§) does not unlock generation."""
    raw = "Ho un dubbio: 3 giorni di ripetute sono troppi. Ne terrei 2, va bene?"
    coach = AICoach()
    monkeypatch.setattr(coach, "_call_chat", lambda system, messages: raw)

    message, is_complete, runner_context = coach.chat_for_plan(
        [{"role": "user", "content": "voglio ripetute lun mar mer"}]
    )
    assert is_complete is False
    assert runner_context is None
    assert message == raw


def test_chat_for_plan_context_in_code_fence_still_parses(monkeypatch):
    """The model wrapping the §CTX§ JSON in a ```json fence must not break it."""
    ctx_obj = {"weekly_km": 40, "threshold_pace": "4:40/km"}
    raw = (
        "Ecco la settimana tipo: lun riposo, mar ripetute, dom lungo.\n"
        "§CTX§\n```json\n" + json.dumps(ctx_obj) + "\n```\n§/CTX§\n§READY§"
    )
    coach = AICoach()
    monkeypatch.setattr(coach, "_call_chat", lambda system, messages: raw)

    message, is_complete, runner_context = coach.chat_for_plan(
        [{"role": "user", "content": "40 km a settimana"}]
    )
    assert is_complete is True
    assert "```" not in message and "§CTX§" not in message
    assert json.loads(runner_context)["weekly_km"] == 40


def test_chat_for_plan_context_without_ready_marker_still_completes(monkeypatch):
    """A parseable §CTX§ block completes even if the model forgets §READY§."""
    ctx_obj = {"weekly_km": 35}
    raw = (
        "Riepilogo finale, settimana tipo giorno per giorno...\n"
        "§CTX§\n" + json.dumps(ctx_obj) + "\n§/CTX§"
    )
    coach = AICoach()
    monkeypatch.setattr(coach, "_call_chat", lambda system, messages: raw)

    _message, is_complete, runner_context = coach.chat_for_plan(
        [{"role": "user", "content": "35 km"}]
    )
    assert is_complete is True
    assert json.loads(runner_context)["weekly_km"] == 35


def test_chat_for_plan_ready_with_broken_context_still_completes(monkeypatch):
    """§READY§ with an unparseable §CTX§ block completes with no context.

    This is the reported dead-end: the athlete saw the settimana tipo but no
    plan. Completion must stand so the app can fall back to the generate dialog
    instead of hiding the "Genera il piano" button forever.
    """
    raw = (
        "Ecco la tua settimana tipo: lun riposo, mar tempo, dom lungo.\n"
        "§CTX§\n{weekly_km: 45, oops not valid json,}\n§/CTX§\n§READY§"
    )
    coach = AICoach()
    monkeypatch.setattr(coach, "_call_chat", lambda system, messages: raw)

    message, is_complete, runner_context = coach.chat_for_plan(
        [{"role": "user", "content": "45 km"}]
    )
    assert is_complete is True
    assert runner_context is None
    # The visible summary survives, sentinels stripped.
    assert "settimana tipo" in message
    assert "§CTX§" not in message and "§READY§" not in message
