"""Enforcement of the chat-agreed weekly structure on generated plans."""

from __future__ import annotations

import json

from app.processing.plan_enforcement import (
    enforce_week_structure,
    parse_week_structure,
)


def _session(dow: int, stype: str, km: float | None = None, pace: str | None = None):
    return {
        "day_of_week": dow,
        "session_type": stype,
        "title": stype.capitalize(),
        "description": f"{stype} desc",
        "target_distance_km": km,
        "target_pace": pace,
        "target_duration_min": None,
    }


def _plan(weeks: list[list[dict]]) -> dict:
    return {
        "weeks_total": len(weeks),
        "start_date": "2026-06-22",
        "weeks": [
            {
                "week_number": i + 1,
                "phase": "Base",
                "target_km": 40.0,
                "sessions": sessions,
            }
            for i, sessions in enumerate(weeks)
        ],
    }


def _ctx(week_structure=None, fixed_sessions=None) -> str:
    ctx: dict = {"weekly_km": 45}
    if week_structure is not None:
        ctx["week_structure"] = week_structure
    if fixed_sessions is not None:
        ctx["fixed_sessions"] = fixed_sessions
    return json.dumps(ctx)


def test_parse_handles_day_names_and_synonyms():
    ctx = _ctx(
        week_structure=[
            {"day": "martedì", "type": "ripetute"},
            {"day": "gio", "type": "race_pace", "pace": "4:30/km"},
            {"day": "Sunday", "type": "lungo", "distance_km": 16},
        ]
    )
    entries = parse_week_structure(ctx)
    assert [(e["dow"], e["type"]) for e in entries] == [
        (1, "intervals"),
        (3, "race"),
        (6, "long"),
    ]
    assert entries[2]["distance_km"] == 16.0


def test_parse_falls_back_to_fixed_sessions():
    ctx = _ctx(fixed_sessions=[{"day": "mar", "type": "intervals"}])
    entries = parse_week_structure(ctx)
    assert entries == [
        {"dow": 1, "type": "intervals", "pace": None, "distance_km": None, "note": None}
    ]


def test_parse_garbage_is_safe():
    assert parse_week_structure(None) == []
    assert parse_week_structure("not json") == []
    assert parse_week_structure(json.dumps({"week_structure": "nope"})) == []
    # Invalid days/types are skipped.
    ctx = _ctx(week_structure=[{"day": "xyz", "type": "intervals"}, {"day": "mar"}])
    assert parse_week_structure(ctx) == []


def test_matching_day_kept_and_pace_applied():
    plan = _plan([[_session(1, "intervals", 10.0), _session(6, "long", 16.0)]])
    ctx = _ctx(week_structure=[{"day": "mar", "type": "intervals", "pace": "4:15/km"}])
    out, notes = enforce_week_structure(plan, ctx)
    sess = out["weeks"][0]["sessions"][0]
    assert sess["session_type"] == "intervals"
    assert sess["target_pace"] == "4:15/km"
    assert notes == []  # nothing moved


def test_swap_preserves_generated_details():
    # Generator put intervals on Wednesday, agreement says Tuesday.
    plan = _plan(
        [[_session(1, "easy", 8.0), _session(2, "intervals", 10.0, "4:20/km")]]
    )
    ctx = _ctx(week_structure=[{"day": "mar", "type": "intervals"}])
    out, notes = enforce_week_structure(plan, ctx)
    by_day = {s["day_of_week"]: s for s in out["weeks"][0]["sessions"]}
    assert by_day[1]["session_type"] == "intervals"
    assert by_day[1]["target_distance_km"] == 10.0  # details travel with the swap
    assert by_day[2]["session_type"] == "easy"
    assert notes and "spostata" in notes[0]


def test_mutation_when_type_absent():
    plan = _plan([[_session(1, "easy", 8.0)]])
    ctx = _ctx(
        week_structure=[
            {"day": "mar", "type": "intervals", "note": "Ripetute col gruppo"}
        ]
    )
    out, notes = enforce_week_structure(plan, ctx)
    sess = out["weeks"][0]["sessions"][0]
    assert sess["session_type"] == "intervals"
    assert sess["title"] == "Ripetute col gruppo"
    assert notes


def test_rest_day_forced_and_cleared():
    plan = _plan([[_session(0, "easy", 8.0, "5:40/km")]])
    ctx = _ctx(week_structure=[{"day": "lun", "type": "rest"}])
    out, _ = enforce_week_structure(plan, ctx)
    sess = out["weeks"][0]["sessions"][0]
    assert sess["session_type"] == "rest"
    assert sess["target_distance_km"] is None
    assert sess["target_pace"] is None


def test_race_week_untouched():
    race_week = [_session(6, "race", 21.1)]
    plan = _plan([race_week])
    ctx = _ctx(week_structure=[{"day": "dom", "type": "long"}])
    out, notes = enforce_week_structure(plan, ctx)
    assert out["weeks"][0]["sessions"][0]["session_type"] == "race"
    assert notes == []


def test_applies_to_every_non_race_week():
    week = lambda: [_session(1, "easy", 8.0), _session(2, "intervals", 10.0)]  # noqa: E731
    plan = _plan([week(), week(), [_session(6, "race", 10.0)]])
    ctx = _ctx(week_structure=[{"day": "mar", "type": "intervals"}])
    out, notes = enforce_week_structure(plan, ctx)
    for wk in out["weeks"][:2]:
        by_day = {s["day_of_week"]: s for s in wk["sessions"]}
        assert by_day[1]["session_type"] == "intervals"
    assert len(notes) == 2


def test_no_context_no_changes():
    plan = _plan([[_session(1, "easy", 8.0)]])
    out, notes = enforce_week_structure(plan, None)
    assert notes == []
    assert out["weeks"][0]["sessions"][0]["session_type"] == "easy"
