"""Unified chat + episodic memory (Roadmap A8 / Passo 17).

One coach that knows everything: the general chat's system prompt carries the
coach's own recent decisions/diary/executions and the episodic memory; the
pre-plan negotiation runs through the same chat surface (mode=plan_negotiation)
with the §CTX§/§READY§ flow untouched. All deterministic: fake coaches are
injected, no network.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

from app.coaching.prompts import build_chat_system
from app.db.models import (
    ChatSession,
    CoachDecisionRow,
    CoachMemory,
    TrainingPlan,
    TrainingPlanSession,
    TrainingPlanWeek,
)
from app.services import chat_service
from app.services.chat_service import send_message
from app.services.coach_memory import list_memory_facts, maybe_update_memory
from app.services.event_service import log_event

TODAY = date.today()


# ── build_chat_system enrichment (pure) ──────────────────────────────────────


def test_system_prompt_includes_coach_context_sections():
    system = build_chat_system(
        None, None, [],
        recent_decisions=[{"date": "2026-07-01", "decision": "rest", "headline": "Riposo"}],
        recent_events=[{"date": "2026-07-01", "event_type": "decision", "title": "Riposo"}],
        recent_executions=[{"date": "2026-06-30", "title": "Tempo 8km",
                            "score": 85.0, "status": "done"}],
        memory_facts=["Corre di solito la mattina presto"],
    )
    assert "[TUE DECISIONI RECENTI]" in system and "2026-07-01: rest — Riposo" in system
    assert "[TUO DIARIO RECENTE]" in system
    assert "[ESECUZIONI RECENTI DEL PIANO]" in system and "execution 85/100" in system
    assert "[MEMORIA SULL'ATLETA]" in system and "mattina presto" in system


def test_system_prompt_sections_absent_without_data():
    system = build_chat_system(None, None, [])
    assert "[TUE DECISIONI RECENTI]" not in system
    assert "[MEMORIA SULL'ATLETA]" not in system


# ── General chat cites a recent decision (acceptance, fixture-driven) ────────


class _CitingCoach:
    """Fake coach that answers by quoting the decision found in its own prompt."""

    def chat_message(self, messages, system):
        for line in system.splitlines():
            if line.strip().startswith("2026-") and "—" in line:
                return f"Te l'ho detto io: {line.strip()}", "fake-model", "simple"
        return "Non trovo decisioni nel mio contesto.", "fake-model", "simple"

    def chat_for_plan(self, messages):  # pragma: no cover - not used here
        raise AssertionError("general mode must not call chat_for_plan")


def test_general_chat_cites_recent_decision(session, monkeypatch):
    session.add(CoachDecisionRow(
        date=(TODAY - timedelta(days=1)).isoformat(), decision="rest",
        headline="Riposo pianificato", prescription="Riposa.",
        rationale="Recupero.", confidence="high",
    ))
    session.flush()
    monkeypatch.setattr(chat_service, "get_coach", lambda: _CitingCoach())

    resp = send_message(session, "Perché ieri mi hai detto di riposare?",
                        None, None, None)
    assert (TODAY - timedelta(days=1)).isoformat() in resp.reply
    assert "rest" in resp.reply
    assert resp.mode == "general" and resp.plan_ready is False


def test_general_chat_sees_diary_and_executions(session, monkeypatch):
    log_event(session, date_str=TODAY.isoformat(), event_type="plan_adapted",
              title="Volume ridotto", detail="-20%")
    plan = TrainingPlan(goal_type="10k", goal_date=(TODAY + timedelta(days=30)).isoformat(),
                        level="intermediate", weeks_total=1,
                        start_date=(TODAY - timedelta(days=TODAY.weekday())).isoformat(),
                        status="active")
    session.add(plan)
    session.flush()
    week = TrainingPlanWeek(plan_id=plan.id, week_number=1, phase="Build", target_km=40.0)
    session.add(week)
    session.flush()
    session.add(TrainingPlanSession(
        week_id=week.id, day_of_week=0, session_type="tempo", title="Tempo 8km",
        execution_score=91.0, execution_status="done",
    ))
    session.flush()

    captured: dict = {}

    class _Spy:
        def chat_message(self, messages, system):
            captured["system"] = system
            return "ok", "fake", "simple"

    monkeypatch.setattr(chat_service, "get_coach", lambda: _Spy())
    send_message(session, "Come sto andando?", None, None, None)
    assert "Volume ridotto" in captured["system"]
    assert "Tempo 8km" in captured["system"] and "execution 91/100" in captured["system"]


# ── Plan-negotiation mode: same §CTX§/§READY§ flow, new surface ──────────────


_CTX = json.dumps({
    "weekly_km": 45,
    "threshold_pace": "4:30/km",
    "week_structure": [
        {"day": "mar", "type": "intervals", "note": "Ripetute col gruppo"},
        {"day": "gio", "type": "tempo", "pace": "4:30/km"},
        {"day": "dom", "type": "long"},
        {"day": "lun", "type": "rest"},
    ],
})


class _PlanCoach:
    """Fake negotiation coach: first turn asks, second turn completes."""

    def chat_for_plan(self, messages):
        user_turns = sum(1 for m in messages if m["role"] == "user")
        if user_turns < 2:
            return "Quanti km fai a settimana?", False, None
        return "Riepilogo: mar ripetute, gio tempo, dom lungo.", True, _CTX

    def chat_message(self, messages, system):  # pragma: no cover
        raise AssertionError("plan mode must not call chat_message")


def test_plan_mode_flows_through_chat_surface(session, monkeypatch):
    monkeypatch.setattr(chat_service, "get_coach", lambda: _PlanCoach())

    first = send_message(session, "Voglio un piano", None, None, None,
                         mode="plan_negotiation")
    assert first.mode == "plan_negotiation"
    assert first.plan_ready is False and first.runner_context is None
    assert session.get(ChatSession, first.session_id).mode == "plan_negotiation"
    assert first.session_title == "Costruzione piano"

    # Second message on the SAME session keeps plan mode without re-passing it.
    second = send_message(session, "Faccio 45 km a settimana", first.session_id,
                          None, None, None)
    assert second.plan_ready is True
    assert json.loads(second.runner_context)["weekly_km"] == 45


def test_mode_only_honoured_at_session_creation(session, monkeypatch):
    monkeypatch.setattr(chat_service, "get_coach", lambda: _CitingCoach())
    resp = send_message(session, "Ciao", None, None, None)  # general session
    # Re-sending with mode=plan on the SAME session must not switch it.
    resp2 = send_message(session, "E ora?", resp.session_id, None, None, None,
                         mode="plan_negotiation")
    assert resp2.mode == "general"


def test_plan_flow_end_to_end_through_new_surface(client, session, monkeypatch):
    """chat(plan-mode) → §READY§ → /api/plan/generate → enforcement (acceptance)."""
    monkeypatch.setattr(chat_service, "get_coach", lambda: _PlanCoach())

    r1 = client.post("/api/chat/send",
                     json={"message": "Voglio un piano", "mode": "plan_negotiation"})
    assert r1.status_code == 200
    sid = r1.json()["session_id"]
    r2 = client.post("/api/chat/send",
                     json={"message": "45 km a settimana", "session_id": sid})
    body = r2.json()
    assert body["plan_ready"] is True and body["runner_context"]

    goal = (TODAY + timedelta(days=90)).isoformat()
    gen = client.post("/api/plan/generate", json={
        "goal_type": "marathon", "goal_date": goal, "goal_time": "3:45:00",
        "level": "intermediate", "days_per_week": 4, "long_run_day": 6,
        "runner_context": body["runner_context"],
    })
    assert gen.status_code == 201, gen.text
    checked = 0
    for week in gen.json()["weeks"]:
        by_day = {s["day_of_week"]: s for s in week["sessions"]}
        if any(s["session_type"] == "race" for s in week["sessions"]):
            continue
        assert by_day[1]["session_type"] == "intervals"
        assert by_day[3]["session_type"] == "tempo"
        assert by_day[0]["session_type"] == "rest"
        checked += 1
    assert checked > 0


def test_sessions_list_carries_mode(client, session, monkeypatch):
    monkeypatch.setattr(chat_service, "get_coach", lambda: _PlanCoach())
    client.post("/api/chat/send",
                json={"message": "Piano!", "mode": "plan_negotiation"})
    sessions = client.get("/api/chat/sessions").json()
    assert sessions and sessions[0]["mode"] == "plan_negotiation"


# ── Episodic memory v0 ───────────────────────────────────────────────────────


def test_memory_extracts_and_stores_facts(session):
    stored = maybe_update_memory(
        session, "Di solito corro la mattina presto prima del lavoro",
        call_fn=lambda s, u: '["Corre di solito la mattina presto"]',
    )
    assert stored == ["Corre di solito la mattina presto"]
    assert list_memory_facts(session) == ["Corre di solito la mattina presto"]


def test_memory_dedupes_same_fact(session):
    fn = lambda s, u: '["Corre la mattina"]'  # noqa: E731
    maybe_update_memory(session, "x", call_fn=fn)
    maybe_update_memory(session, "y", call_fn=fn)
    assert session.query(CoachMemory).count() == 1


def test_memory_garbage_and_errors_are_swallowed(session):
    assert maybe_update_memory(session, "x", call_fn=lambda s, u: "non-json") == []

    def _boom(s, u):
        raise TimeoutError("slow")

    assert maybe_update_memory(session, "x", call_fn=_boom) == []
    assert session.query(CoachMemory).count() == 0


def test_memory_noop_without_key(session):
    # Test env has no ANTHROPIC_API_KEY and no injected call_fn → no-op.
    assert maybe_update_memory(session, "corro sempre alle 6") == []


def test_memory_flows_into_next_chat_prompt(session, monkeypatch):
    session.add(CoachMemory(fact="Preferisce correre in pista"))
    session.flush()
    captured: dict = {}

    class _Spy:
        def chat_message(self, messages, system):
            captured["system"] = system
            return "ok", "fake", "simple"

    monkeypatch.setattr(chat_service, "get_coach", lambda: _Spy())
    send_message(session, "Che allenamento faccio?", None, None, None)
    assert "Preferisce correre in pista" in captured["system"]
