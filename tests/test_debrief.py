"""Post-run voice debrief → structured signals (Roadmap A4 / Passo 12).

Deterministic tests exercise the rule-based Italian extractor and the whole
persistence path (activity, source-precedence check-in, pain event) with no
network. LLM-path tests inject a fake ``call_fn`` to prove the defensive parse
and fallback. A nightly ``eval_llm`` golden hits the real model.
"""

from __future__ import annotations

import json
import os
from datetime import date

import pytest
from sqlalchemy import select

from app.db.models import Activity, CoachEvent, DailyCheckinRow
from app.schemas import DailyCheckin
from app.services.checkin import save_checkin
from app.services.debrief import (
    extract_debrief,
    maybe_prompt_debrief,
    process_debrief,
)
from app.services.push import _build_fcm_message

TODAY = date.today().isoformat()


# ── Rule-based extraction on real Italian debriefs ───────────────────────────


def test_extract_real_italian_acceptance_text():
    """The acceptance example from the roadmap brief."""
    d = extract_debrief("Fatta dura, polpaccio destro un po' teso, 7 di fatica")
    assert d.rpe == 7
    assert d.soreness is not None and d.soreness >= 3
    assert d.pain_location == "polpaccio destro"
    assert "polpaccio" in d.notes.lower()


def test_extract_easy_run_no_pain():
    d = extract_debrief("Corsa facile e scorrevole, gambe leggere, mi sono divertito")
    assert d.rpe == 3
    assert d.pain_location is None  # "gambe leggere" is positive, not a complaint
    assert d.mood == "bene"


def test_extract_explicit_soreness_and_knee_pain():
    d = extract_debrief("Ginocchio sinistro fa male, 8 di dolore, tirata forte")
    assert d.pain_location == "ginocchio sinistro"
    assert d.soreness == 8
    assert d.rpe == 8


def test_extract_slash_ten_effort():
    d = extract_debrief("Andata bene, sforzo 6/10, nessun problema")
    assert d.rpe == 6
    assert d.pain_location is None
    assert d.mood == "bene"


def test_extract_tired_mood_hard_effort_keyword():
    d = extract_debrief("Durissima, sono distrutto, che stanchezza")
    assert d.rpe == 9
    assert d.mood == "stanco"


def test_extract_empty_text_is_blank():
    d = extract_debrief("   ")
    assert d.rpe is None and d.soreness is None and d.pain_location is None
    assert d.notes == ""


# ── LLM path: defensive parse + fallback ─────────────────────────────────────


def test_llm_path_parses_json():
    payload = {
        "rpe": 7, "soreness": 4, "pain_location": "polpaccio destro",
        "mood": "stanco", "notes": "corsa dura",
    }
    d = extract_debrief("qualcosa", call_fn=lambda s, u: json.dumps(payload))
    assert d.rpe == 7 and d.soreness == 4
    assert d.pain_location == "polpaccio destro" and d.mood == "stanco"


def test_llm_path_clamps_out_of_range():
    d = extract_debrief(
        "x", call_fn=lambda s, u: json.dumps({"rpe": 99, "soreness": 0, "notes": ""})
    )
    assert d.rpe == 10 and d.soreness == 1


def test_llm_path_garbage_falls_back_to_rules():
    # Model returns non-JSON → fall back to the rule-based parser on the text.
    d = extract_debrief("7 di fatica", call_fn=lambda s, u: "non è json affatto")
    assert d.rpe == 7  # rule-based recovered it


def test_llm_path_exception_falls_back():
    def _boom(s, u):
        raise TimeoutError("slow model")

    d = extract_debrief("facile facile", call_fn=_boom)
    assert d.rpe == 3  # rule-based fallback


# ── Source precedence: proxy must never overwrite a voice debrief ────────────


def test_proxy_does_not_overwrite_voice(session):
    save_checkin(session, DailyCheckin(date=TODAY, fatigue=7, soreness=4, source="voice"))
    # A later Garmin proxy for the same day tries to write fatigue=2.
    save_checkin(
        session,
        DailyCheckin(date=TODAY, fatigue=2, hrv_rmssd=55.0, source="garmin_proxy"),
    )
    row = session.scalar(
        select(DailyCheckinRow).where(DailyCheckinRow.date == TODAY)
    )
    assert row.fatigue == 7  # voice value preserved
    assert row.source == "voice"  # stronger label kept
    assert row.hrv_rmssd == 55.0  # proxy still filled the empty HRV gap


def test_voice_overwrites_proxy_but_keeps_hrv(session):
    save_checkin(
        session,
        DailyCheckin(date=TODAY, fatigue=2, hrv_rmssd=55.0, source="garmin_proxy"),
    )
    # Voice debrief carries HRV forward (as process_debrief does) and wins.
    save_checkin(
        session,
        DailyCheckin(date=TODAY, fatigue=8, hrv_rmssd=55.0, source="voice"),
    )
    row = session.get(DailyCheckinRow, 1)
    assert row.fatigue == 8 and row.source == "voice" and row.hrv_rmssd == 55.0


def test_manual_overwrites_proxy(session):
    save_checkin(session, DailyCheckin(date=TODAY, fatigue=2, source="garmin_proxy"))
    save_checkin(session, DailyCheckin(date=TODAY, fatigue=6, source="manual"))
    row = session.get(DailyCheckinRow, 1)
    assert row.fatigue == 6 and row.source == "manual"


# ── process_debrief: full persistence path ───────────────────────────────────


def _add_run(session) -> Activity:
    run = Activity(
        date=TODAY, sport="run", activity_type="tempo",
        distance_km=10.0, duration_min=50.0,
    )
    session.add(run)
    session.flush()
    return run


def test_process_updates_activity_and_checkin(session):
    run = _add_run(session)
    result = process_debrief(
        session, "Fatta dura, 7 di fatica, tutto ok", activity_id=run.id
    )
    assert result.activity_id == run.id
    session.refresh(run)
    assert run.rpe == 7
    assert run.notes and "fatica" in run.notes.lower()
    row = session.scalar(
        select(DailyCheckinRow).where(DailyCheckinRow.date == TODAY)
    )
    assert row.fatigue == 7 and row.source == "voice"


def test_process_pain_creates_high_priority_event(session):
    run = _add_run(session)
    process_debrief(
        session, "Polpaccio destro un po' teso, per il resto ok", activity_id=run.id
    )
    events = session.query(CoachEvent).filter_by(event_type="debrief_pain").all()
    assert len(events) == 1
    ev = events[0]
    assert ev.notifiable and ev.priority == "high"
    assert "polpaccio destro" in ev.detail
    assert ev.after.get("deep_link") == "debrief"


def test_process_no_pain_no_event(session):
    run = _add_run(session)
    process_debrief(session, "Corsa facile, gambe leggere", activity_id=run.id)
    assert session.query(CoachEvent).filter_by(event_type="debrief_pain").count() == 0


def test_process_without_activity_id_attaches_latest_run(session):
    run = _add_run(session)
    result = process_debrief(session, "5 di fatica")
    assert result.activity_id == run.id


def test_process_then_proxy_keeps_voice(session):
    """End-to-end: debrief writes voice, a later proxy can't clobber fatigue."""
    run = _add_run(session)
    process_debrief(session, "8 di fatica, dura", activity_id=run.id)
    save_checkin(session, DailyCheckin(date=TODAY, fatigue=2, source="garmin_proxy"))
    row = session.scalar(
        select(DailyCheckinRow).where(DailyCheckinRow.date == TODAY)
    )
    assert row.fatigue == 8 and row.source == "voice"


# ── Debrief prompt event (bridge from the execution-score push) ──────────────


def test_maybe_prompt_debrief_is_notifiable_and_deduped(session):
    run = _add_run(session)
    maybe_prompt_debrief(session, run)
    maybe_prompt_debrief(session, run)  # second call must not duplicate
    events = session.query(CoachEvent).filter_by(event_type="debrief_prompt").all()
    assert len(events) == 1
    assert events[0].notifiable and events[0].after.get("deep_link") == "debrief"
    assert events[0].after.get("activity_id") == run.id


def test_maybe_prompt_debrief_ignores_non_run(session):
    bike = Activity(date=TODAY, sport="bike", activity_type="easy", distance_km=20.0)
    session.add(bike)
    session.flush()
    maybe_prompt_debrief(session, bike)
    assert session.query(CoachEvent).filter_by(event_type="debrief_prompt").count() == 0


# ── FCM message builder carries the deep-link data ───────────────────────────


def test_build_fcm_message_includes_deeplink_data():
    msg = _build_fcm_message(
        "tok", "Com'è andata?", "Raccontami",
        "NORMAL", {"deep_link": "debrief", "activity_id": 12},
    )
    assert msg["message"]["data"] == {"deep_link": "debrief", "activity_id": "12"}
    assert msg["message"]["notification"]["title"] == "Com'è andata?"


def test_build_fcm_message_without_data_has_no_data_key():
    msg = _build_fcm_message("tok", "t", "b", "HIGH")
    assert "data" not in msg["message"]


# ── HTTP endpoint ────────────────────────────────────────────────────────────


def test_debrief_endpoint(client, session):
    run = Activity(date=TODAY, sport="run", activity_type="tempo", distance_km=8.0)
    session.add(run)
    session.commit()
    resp = client.post(
        "/api/debrief",
        json={"text": "Ginocchio destro fa male, 7 di fatica", "activity_id": run.id},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["rpe"] == 7
    assert body["pain_location"] == "ginocchio destro"


# ── Nightly golden: real LLM extraction ──────────────────────────────────────

_HAS_KEY = bool(os.environ.get("ANTHROPIC_API_KEY"))


@pytest.mark.eval_llm
@pytest.mark.skipif(not _HAS_KEY, reason="ANTHROPIC_API_KEY not set")
def test_llm_extraction_golden(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", os.environ["ANTHROPIC_API_KEY"])
    from app.config import get_settings

    get_settings.cache_clear()
    d = extract_debrief("Fatta dura, polpaccio destro un po' teso, 7 di fatica")
    assert d.rpe == 7
    assert d.pain_location and "polpaccio" in d.pain_location.lower()
