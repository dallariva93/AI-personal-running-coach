"""Whole-plan what-if (Fase F, feature #10).

The periodization engine is pure and instant, so "what if I gave myself two
more weeks / trained 5 days / targeted a faster time?" is answered by building
two Plan Specs and diffing their headline numbers — no LLM, no persistence, no
waiting. Deterministic given a fixed ``ref``.
"""

from __future__ import annotations

from datetime import date

from app.processing.periodization import build_plan_spec
from app.schemas import (
    AthleteProfile,
    PlanGenerateRequest,
    PlanWhatIfOut,
    PlanWhatIfRequest,
    PlanWhatIfSummary,
    TrainingMetrics,
)

_OVERRIDES = ("goal_type", "goal_date", "goal_time", "level", "days_per_week", "long_run_day")


def _summary(spec: dict) -> PlanWhatIfSummary:
    weeks = spec.get("weeks", [])
    kms = [float(w.get("target_km", 0.0)) for w in weeks]
    total = round(sum(kms), 1)
    return PlanWhatIfSummary(
        weeks_total=spec.get("weeks_total", len(weeks)),
        total_km=total,
        peak_week_km=round(max(kms), 1) if kms else 0.0,
        avg_weekly_km=round(total / len(kms), 1) if kms else 0.0,
    )


def _scenario_request(req: PlanWhatIfRequest) -> PlanGenerateRequest:
    """Apply the non-None overrides onto a copy of the base request."""
    changes = {f: getattr(req, f) for f in _OVERRIDES if getattr(req, f) is not None}
    return req.base.model_copy(update=changes)


def _notes(base: PlanWhatIfSummary, scen: PlanWhatIfSummary) -> list[str]:
    notes: list[str] = []
    dw = scen.weeks_total - base.weeks_total
    if dw:
        notes.append(
            f"{abs(dw)} settimane {'in più' if dw > 0 else 'in meno'} di preparazione."
        )
    dpeak = round(scen.peak_week_km - base.peak_week_km, 1)
    if abs(dpeak) >= 1:
        notes.append(
            f"Picco settimanale {'+' if dpeak > 0 else ''}{dpeak} km "
            f"({base.peak_week_km} → {scen.peak_week_km})."
        )
    davg = round(scen.avg_weekly_km - base.avg_weekly_km, 1)
    if abs(davg) >= 1:
        notes.append(
            f"Media settimanale {'+' if davg > 0 else ''}{davg} km."
        )
    if not notes:
        notes.append("Impatto trascurabile sui volumi complessivi.")
    return notes


def plan_whatif(
    req: PlanWhatIfRequest,
    profile: AthleteProfile | None = None,
    metrics: TrainingMetrics | None = None,
    ref: date | None = None,
) -> PlanWhatIfOut:
    """Compare the base plan with the overridden scenario, instantly."""
    base_spec = build_plan_spec(req.base, profile=profile, metrics=metrics, ref=ref)
    scen_spec = build_plan_spec(
        _scenario_request(req), profile=profile, metrics=metrics, ref=ref
    )
    base, scenario = _summary(base_spec), _summary(scen_spec)
    deltas = {
        "weeks_total": float(scenario.weeks_total - base.weeks_total),
        "total_km": round(scenario.total_km - base.total_km, 1),
        "peak_week_km": round(scenario.peak_week_km - base.peak_week_km, 1),
        "avg_weekly_km": round(scenario.avg_weekly_km - base.avg_weekly_km, 1),
    }
    return PlanWhatIfOut(
        baseline=base, scenario=scenario, deltas=deltas, notes=_notes(base, scenario)
    )
