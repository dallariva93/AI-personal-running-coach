"""Unit tests for the deterministic Plan Spec engine (Fase A).

These pin the physiological invariants the offline generator must guarantee now
that it delegates to ``build_plan_spec``: a fixed ``ref`` makes every plan
reproducible, volumes always add up, the progression is smooth with deloads,
the taper unloads, and the chat-agreed skeleton (§CTX§) is honoured verbatim.
"""

from __future__ import annotations

import json
from datetime import date

from app.processing.periodization import build_plan_spec
from app.schemas import (
    AthletePhysiology,
    AthleteProfile,
    PlanGenerateRequest,
    TrainingMetrics,
)

REF = date(2026, 6, 22)  # a Monday


def _pace_sec(pace: str) -> int:
    m, s = pace.replace("/km", "").split(":")
    return int(m) * 60 + int(s)


def _pace_series(spec: dict, stype: str) -> list[int]:
    """Ordered per-week pace (sec/km) for every week that has ``stype``."""
    out = []
    for w in spec["weeks"]:
        s = next((x for x in w["sessions"] if x["session_type"] == stype), None)
        if s and s["target_pace"]:
            out.append(_pace_sec(s["target_pace"]))
    return out


def _req(**kw) -> PlanGenerateRequest:
    base = {
        "goal_type": "marathon",
        "goal_date": "2026-11-08",
        "goal_time": "3:45:00",
        "level": "intermediate",
        "days_per_week": 4,
        "long_run_day": 6,
    }
    base.update(kw)
    return PlanGenerateRequest(**base)


def _non_deload(weeks: list[dict], phase: str) -> list[dict]:
    return [
        w for w in weeks
        if w["phase"] == phase and "scarico" not in w["description"].lower()
    ]


# ── Determinism ──────────────────────────────────────────────────────────────

def test_is_deterministic_for_fixed_ref():
    a = build_plan_spec(_req(), ref=REF)
    b = build_plan_spec(_req(), ref=REF)
    assert a == b


# ── Structural invariants (must match the old template contract) ─────────────

def test_seven_sessions_and_full_week_every_week():
    spec = build_plan_spec(_req(), ref=REF)
    assert 4 <= spec["weeks_total"] <= 24
    assert spec["start_date"] == "2026-06-22"
    for w in spec["weeks"]:
        assert {"week_number", "phase", "target_km", "sessions"} <= set(w)
        assert len(w["sessions"]) == 7
        assert sorted(s["day_of_week"] for s in w["sessions"]) == list(range(7))


def test_week_target_equals_session_sum():
    """The header volume can never disagree with the sessions again."""
    spec = build_plan_spec(_req(days_per_week=5), ref=REF)
    for w in spec["weeks"]:
        total = round(sum(s["target_distance_km"] or 0.0 for s in w["sessions"]), 1)
        assert total == w["target_km"], f"week {w['week_number']}"


# ── Smooth progression & deloads ─────────────────────────────────────────────

def test_base_phase_progression_is_monotonic_between_deloads():
    spec = build_plan_spec(_req(), ref=REF)
    base = _non_deload(spec["weeks"], "Base")
    assert len(base) >= 2
    vols = [w["target_km"] for w in base]
    assert vols == sorted(vols)  # non-decreasing
    assert vols[-1] > vols[0]  # and it actually builds


def test_deload_week_dips_below_its_neighbours():
    spec = build_plan_spec(_req(), ref=REF)
    weeks = spec["weeks"]
    deloads = [w for w in weeks if "scarico" in w["description"].lower()]
    assert deloads, "a multi-month build must contain at least one deload"
    for w in deloads:
        i = w["week_number"] - 1
        assert weeks[i - 1]["target_km"] > w["target_km"]


def test_aggressive_ramp_tightens_deload_cadence():
    """A high ACWR / ramp should schedule deloads every 3 weeks, not 4."""
    metrics = TrainingMetrics(chronic_load_km=40, acute_load_km=52, acwr=1.3)
    spec = build_plan_spec(_req(), metrics=metrics, ramp_pct=10.0, ref=REF)
    deload_weeks = [
        w["week_number"] for w in spec["weeks"]
        if "scarico" in w["description"].lower()
    ]
    # First deload lands on the 3rd prep week rather than the 4th.
    assert deload_weeks and deload_weeks[0] == 3


# ── Taper ────────────────────────────────────────────────────────────────────

def test_taper_unloads_progressively_and_below_peak():
    spec = build_plan_spec(_req(), ref=REF)
    peak_km = max(w["target_km"] for w in spec["weeks"] if w["phase"] != "Gara")
    taper = [w for w in spec["weeks"] if w["phase"] == "Taper"]
    assert len(taper) == 3  # marathon taper
    tvols = [w["target_km"] for w in taper]
    assert tvols == sorted(tvols, reverse=True)  # sheds volume week over week
    assert all(v < peak_km for v in tvols)
    assert spec["weeks"][-1]["phase"] == "Gara"


# ── Baseline & short runway ──────────────────────────────────────────────────

def test_baseline_from_metrics_when_no_context():
    lo = build_plan_spec(_req(), metrics=TrainingMetrics(chronic_load_km=30), ref=REF)
    hi = build_plan_spec(_req(), metrics=TrainingMetrics(chronic_load_km=60), ref=REF)
    assert hi["weeks"][0]["target_km"] > lo["weeks"][0]["target_km"]


def test_short_runway_still_valid():
    spec = build_plan_spec(_req(goal_date="2026-07-12"), ref=REF)  # ~3 weeks out
    assert spec["weeks_total"] == 4  # clamped to the minimum
    for w in spec["weeks"]:
        assert len(w["sessions"]) == 7
    assert spec["weeks"][-1]["phase"] == "Gara"


# ── §CTX§ contract ───────────────────────────────────────────────────────────

def test_chat_week_structure_is_honoured_verbatim():
    ctx = json.dumps(
        {
            "weekly_km": 45,
            "week_structure": [
                {"day": "mar", "type": "intervals"},
                {"day": "gio", "type": "tempo", "pace": "4:30/km"},
                {"day": "dom", "type": "long", "distance_km": 20},
                {"day": "lun", "type": "rest"},
            ],
        }
    )
    spec = build_plan_spec(_req(runner_context=ctx), ref=REF)
    # Check a mid-build, non-race week.
    week = next(w for w in spec["weeks"] if w["phase"] == "Specifico")
    by_day = {s["day_of_week"]: s for s in week["sessions"]}
    assert by_day[1]["session_type"] == "intervals"
    assert by_day[3]["session_type"] == "tempo"
    assert by_day[6]["session_type"] == "long"
    assert by_day[6]["target_distance_km"] == 20.0  # pinned distance respected
    assert by_day[0]["session_type"] == "rest"


def test_chat_paces_propagate_to_sessions():
    ctx = json.dumps({"easy_pace": "5:15/km", "threshold_pace": "4:10/km"})
    spec = build_plan_spec(_req(), ref=REF)  # defaults first
    ctx_spec = build_plan_spec(_req(runner_context=ctx), ref=REF)

    def easy_pace(s):
        w = next(w for w in s["weeks"] if w["phase"] == "Base")
        return next(
            x["target_pace"] for x in w["sessions"] if x["session_type"] == "easy"
        )

    assert easy_pace(spec) != "5:15/km"
    assert easy_pace(ctx_spec) == "5:15/km"
    # Threshold drives tempo pace in a build week.
    build = next(w for w in ctx_spec["weeks"] if w["phase"] == "Build")
    tempo = next(
        (s for s in build["sessions"] if s["session_type"] == "tempo"), None
    )
    if tempo is not None:
        assert tempo["target_pace"] == "4:10/km"


def test_days_per_week_controls_training_days():
    three = build_plan_spec(_req(days_per_week=3), ref=REF)
    six = build_plan_spec(_req(days_per_week=6), ref=REF)

    def run_days(spec):
        w = next(w for w in spec["weeks"] if w["phase"] == "Base")
        return sum(
            1 for s in w["sessions"] if s["session_type"] != "rest"
        )

    assert run_days(three) < run_days(six)


# ── Fase C: fitness-derived, progressing paces ───────────────────────────────

def _profile(lt2: str) -> AthleteProfile:
    return AthleteProfile(level="intermediate", physiology=AthletePhysiology(lt2_pace=lt2))


def test_paces_anchor_on_current_threshold():
    """Week-1 paces derive from current LT2 (progress 0), not the goal pace.

    Easy ≈ LT2 × 1.22 at week 1; the goal (3:20) would imply a much faster easy,
    so anchoring on current form is what keeps early weeks runnable.
    """
    spec = build_plan_spec(
        _req(goal_time="3:20:00"), profile=_profile("5:10/km"), ref=REF
    )
    easy_wk1 = _pace_series(spec, "easy")[0]
    expected = round(_pace_sec("5:10/km") * 1.22)  # current LT2 → easy
    assert abs(easy_wk1 - expected) <= 3


def test_paces_progress_toward_goal():
    """When the goal is faster than current form, paces get faster across the block."""
    spec = build_plan_spec(
        _req(goal_time="3:20:00"), profile=_profile("5:10/km"), ref=REF
    )
    tempo = _pace_series(spec, "tempo")
    easy = _pace_series(spec, "easy")
    assert tempo[0] > tempo[-1]  # tempo gets faster (fewer sec/km)
    assert easy[0] > easy[-1]


def test_chat_pinned_threshold_pace_stays_flat():
    """A pace the athlete pinned in chat is a contract — it must not drift."""
    ctx = json.dumps({"threshold_pace": "4:30/km"})
    spec = build_plan_spec(
        _req(goal_time="3:00:00", runner_context=ctx), profile=_profile("5:10/km"), ref=REF
    )
    tempo = set(_pace_series(spec, "tempo"))
    assert tempo == {_pace_sec("4:30/km")}  # identical every week


def test_paces_never_prescribed_slower_than_current_form():
    """A soft goal must not make the plan prescribe *slower* than today's fitness."""
    spec = build_plan_spec(
        _req(goal_time="4:45:00"), profile=_profile("4:20/km"), ref=REF
    )
    tempo = _pace_series(spec, "tempo")
    assert max(tempo) <= _pace_sec("4:20/km") + 2  # never slower than current LT2


# ── Fase C: goal-realism gate ────────────────────────────────────────────────

def test_goal_realism_flags_ambitious_goal():
    metrics = TrainingMetrics(
        chronic_load_km=45, predicted_race_time="3:38:00",
        race_probability=0.35, race_confidence="medium",
    )
    spec = build_plan_spec(_req(goal_time="3:20:00"), metrics=metrics, ref=REF)
    realism = spec["goal_realism"]
    assert realism["verdict"] == "ambizioso"
    assert realism["required_improvement_pct"] > 0
    # The warning is surfaced on week 1.
    assert "ambizioso" in spec["weeks"][0]["description"].lower()


def test_goal_realism_realistic_goal_has_no_warning():
    metrics = TrainingMetrics(
        chronic_load_km=45, predicted_race_time="3:19:00", race_probability=0.55,
    )
    spec = build_plan_spec(_req(goal_time="3:20:00"), metrics=metrics, ref=REF)
    assert spec["goal_realism"]["verdict"] in {"realistico", "conservativo"}
    assert "ambizioso" not in spec["weeks"][0]["description"].lower()


def test_goal_realism_absent_without_prediction():
    spec = build_plan_spec(_req(goal_time="3:20:00"), ref=REF)  # no metrics
    assert spec["goal_realism"] is None
    assert "ambizioso" not in spec["weeks"][0]["description"].lower()
