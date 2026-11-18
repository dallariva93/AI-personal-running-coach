"""Unit tests for the plan verbalizer (Fase B).

The LLM only rewrites descriptions; every structured field stays exactly as the
periodization engine set it, and any failure falls back to the templates.
"""

from __future__ import annotations

import json
from datetime import date

from app.coaching.plan_verbalize import _prescriptions, verbalize_plan_spec
from app.processing.periodization import build_plan_spec
from app.schemas import PlanGenerateRequest

REF = date(2026, 6, 22)


class _NoAI:
    ai_enabled = False


def _spec():
    req = PlanGenerateRequest(
        goal_type="marathon",
        goal_date="2026-11-08",
        level="intermediate",
        days_per_week=4,
        long_run_day=6,
    )
    return build_plan_spec(req, ref=REF), req


def _structured(spec):
    """Every structured field, keyed by (week, day) — description excluded."""
    return {
        (w["week_number"], s["day_of_week"]): (
            s["session_type"],
            s["target_distance_km"],
            s["target_pace"],
            s["target_duration_min"],
            s["title"],
        )
        for w in spec["weeks"]
        for s in w["sessions"]
    }


def _echo_call(system, user):
    """A fake model: rewrite every prescription it's handed, numbers untouched."""
    payload = next(line for line in user.splitlines() if line.startswith("["))
    pres = json.loads(payload)
    return json.dumps(
        {p["id"]: f"Coach: {p['type']} {p['distance_km']}km" for p in pres}
    )


def test_no_call_fn_and_no_ai_leaves_spec_untouched():
    spec, req = _spec()
    before = json.dumps(spec, sort_keys=True)
    out = verbalize_plan_spec(spec, request=req, settings=_NoAI(), call_fn=None)
    assert json.dumps(out, sort_keys=True) == before


def test_verbalize_rewrites_only_descriptions():
    spec, req = _spec()
    before = _structured(spec)
    out = verbalize_plan_spec(spec, request=req, call_fn=_echo_call)
    # Structured fields are byte-for-byte identical.
    assert _structured(out) == before
    # Non-rest descriptions were rewritten; rest days keep their template text.
    for w in out["weeks"]:
        for s in w["sessions"]:
            if s["session_type"] == "rest":
                assert "Recupero" in s["description"]
            else:
                assert s["description"].startswith("Coach:")


def test_failure_keeps_template_descriptions():
    spec, req = _spec()
    templates = {
        (w["week_number"], s["day_of_week"]): s["description"]
        for w in spec["weeks"]
        for s in w["sessions"]
    }

    def boom(system, user):
        raise RuntimeError("model unavailable")

    out = verbalize_plan_spec(spec, request=req, call_fn=boom)
    for w in out["weeks"]:
        for s in w["sessions"]:
            assert s["description"] == templates[(w["week_number"], s["day_of_week"])]


def test_partial_reply_degrades_gracefully():
    spec, req = _spec()
    pres = _prescriptions(spec)
    first_id = pres[0]["id"]
    template_second = None
    # Grab the template of the *second* prescription so we can assert it survives.
    second_id = pres[1]["id"]

    def partial(system, user):
        return json.dumps({first_id: "Solo questa riscritta"})

    # Record the template descriptions keyed by id before the call.
    id_to_template = {
        f"w{w['week_number']}d{s['day_of_week']}": s["description"]
        for w in spec["weeks"]
        for s in w["sessions"]
    }
    template_second = id_to_template[second_id]

    verbalize_plan_spec(spec, request=req, call_fn=partial)

    got = {
        f"w{w['week_number']}d{s['day_of_week']}": s["description"]
        for w in spec["weeks"]
        for s in w["sessions"]
    }
    assert got[first_id] == "Solo questa riscritta"
    assert got[second_id] == template_second  # untouched


def test_non_object_reply_is_ignored():
    spec, req = _spec()
    templates = json.dumps(spec, sort_keys=True)

    def array_reply(system, user):
        return json.dumps(["not", "a", "mapping"])

    out = verbalize_plan_spec(spec, request=req, call_fn=array_reply)
    assert json.dumps(out, sort_keys=True) == templates


def test_prescriptions_skip_rest_days():
    spec, _ = _spec()
    pres = _prescriptions(spec)
    types = {p["type"] for p in pres}
    assert "rest" not in types
    assert pres  # something to verbalize
