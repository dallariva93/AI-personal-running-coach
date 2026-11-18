"""Unit tests for whole-plan what-if (Fase F, feature #10)."""

from __future__ import annotations

from datetime import date

from app.processing.plan_whatif import plan_whatif
from app.schemas import PlanGenerateRequest, PlanWhatIfRequest

REF = date(2026, 6, 22)


def _base(**kw) -> PlanGenerateRequest:
    d = {
        "goal_type": "marathon",
        "goal_date": "2026-11-08",
        "level": "intermediate",
        "days_per_week": 4,
        "long_run_day": 6,
    }
    d.update(kw)
    return PlanGenerateRequest(**d)


def test_no_overrides_is_a_no_op():
    out = plan_whatif(PlanWhatIfRequest(base=_base()), ref=REF)
    assert out.baseline == out.scenario
    assert all(v == 0 for v in out.deltas.values())
    assert "trascurabile" in out.notes[0]


def test_more_weeks_increases_total_volume():
    req = PlanWhatIfRequest(base=_base(), goal_date="2026-12-06")  # ~4 weeks later
    out = plan_whatif(req, ref=REF)
    assert out.scenario.weeks_total > out.baseline.weeks_total
    assert out.deltas["total_km"] > 0
    assert any("settimane in più" in n for n in out.notes)


def test_more_days_raises_weekly_average():
    req = PlanWhatIfRequest(base=_base(days_per_week=3), days_per_week=6)
    out = plan_whatif(req, ref=REF)
    assert out.scenario.avg_weekly_km > out.baseline.avg_weekly_km


def test_is_deterministic():
    req = PlanWhatIfRequest(base=_base(), days_per_week=5)
    assert plan_whatif(req, ref=REF) == plan_whatif(req, ref=REF)


def test_base_request_is_not_mutated():
    base = _base(days_per_week=4)
    plan_whatif(PlanWhatIfRequest(base=base, days_per_week=6), ref=REF)
    assert base.days_per_week == 4  # override applied to a copy, not the base
