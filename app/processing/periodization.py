"""Periodization: turn a goal race into a phased macrocycle (GAP 2 + 17).

A real coach doesn't decide week by week — it works backwards from the race
date through a sequence of phases:

    Base → Build → Specific → Peak → Taper → Race

Each phase has a target weekly volume (relative to the athlete's current
baseline) and an intensity focus. The final **taper** sheds volume progressively
so the athlete arrives fresh. All functions here are pure and deterministic.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta

from app.schemas import Goal, PeriodizationPlan, PhasePlan

# Taper length (weeks) by race distance — longer races need a longer taper.
_TAPER_WEEKS = {"marathon": 3, "half": 2, "10k": 1, "5k": 1, "trail": 2}

# Share of the *preparation* weeks (everything before the taper) per phase.
_PREP_SHARES = {"base": 0.35, "build": 0.30, "specific": 0.20, "peak": 0.15}

# Weekly volume relative to baseline, and the focus, per phase.
_PHASE_PROFILE = {
    "base": (1.0, "Costruzione aerobica: tanti km facili in Z2, 80/20.", [
        "Lungo progressivo in Z2",
        "Fondo medio facile",
        "Allunghi/strides a fine seduta",
    ]),
    "build": (1.15, "Aumento del volume e introduzione della soglia.", [
        "Tempo run in Z3-Z4",
        "Lungo con tratti a ritmo medio",
        "Ripetute medie (1000-2000m)",
    ]),
    "specific": (1.2, "Lavoro al ritmo gara e resistenza specifica.", [
        "Lungo con porzioni a ritmo gara",
        "Ripetute al ritmo gara",
        "Tempo run lungo alla soglia",
    ]),
    "peak": (1.1, "Affinamento: meno volume, qualità alta vicino al ritmo gara.", [
        "Ripetute brevi veloci (VO2max)",
        "Lungo medio con finale veloce",
        "Simulazione parziale di gara",
    ]),
    "taper": (0.6, "Scarico progressivo: riduci il volume, mantieni un po' di ritmo.", [
        "Sedute brevi con qualche allungo a ritmo gara",
        "Volume ridotto, recupero",
    ]),
    "race": (0.3, "Settimana gara: riposo, attivazione leggera, gara.", [
        "Attivazione 20-30 min con 3-4 allunghi",
        "Riposo pre-gara",
    ]),
}

_PHASE_ORDER = ["base", "build", "specific", "peak", "taper", "race"]


def _parse(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _allocate_prep_weeks(prep_weeks: int) -> dict[str, int]:
    """Split the preparation weeks across base/build/specific/peak.

    Rounds each share and gives any remainder to ``base`` (the foundation).
    """
    if prep_weeks <= 0:
        return {k: 0 for k in _PREP_SHARES}
    alloc = {name: int(round(prep_weeks * share)) for name, share in _PREP_SHARES.items()}
    drift = prep_weeks - sum(alloc.values())
    alloc["base"] += drift  # absorb rounding error
    if alloc["base"] < 0:  # pathological tiny runways
        alloc["base"] = 0
    return alloc


def build_periodization(
    goal: Goal | None,
    baseline_km: float,
    ref: date | None = None,
) -> PeriodizationPlan | None:
    """Build the macrocycle from ``ref`` to the goal race, or None if N/A."""
    ref = ref or date.today()
    if goal is None:
        return None
    target = _parse(goal.target_date)
    if target is None or target < ref:
        return None

    days = (target - ref).days
    weeks_to_race = max(1, math.ceil((days + 1) / 7))

    taper_weeks = _TAPER_WEEKS.get(goal.goal_type, 2)
    # Always leave at least the race week; never let taper exceed the runway.
    race_weeks = 1
    taper_weeks = min(taper_weeks, max(0, weeks_to_race - race_weeks))
    prep_weeks = max(0, weeks_to_race - taper_weeks - race_weeks)
    alloc = _allocate_prep_weeks(prep_weeks)
    alloc["taper"] = taper_weeks
    alloc["race"] = race_weeks if weeks_to_race >= 1 else 0

    baseline = max(baseline_km, 0.0)
    phases: list[PhasePlan] = []
    cursor = _monday(ref)
    for name in _PHASE_ORDER:
        weeks = alloc.get(name, 0)
        if weeks <= 0:
            continue
        factor, focus, workouts = _PHASE_PROFILE[name]
        start = cursor
        end = cursor + timedelta(days=weeks * 7 - 1)
        phases.append(
            PhasePlan(
                name=name,
                start_date=start.isoformat(),
                end_date=end.isoformat(),
                weeks=weeks,
                volume_factor=factor,
                intensity_focus=focus,
                key_workouts=workouts,
            )
        )
        cursor = end + timedelta(days=1)

    current = current_phase(phases, ref) or (phases[0].name if phases else "base")
    return PeriodizationPlan(
        goal_type=goal.goal_type,
        target_date=target.isoformat(),
        weeks_to_race=weeks_to_race,
        baseline_km=round(baseline, 1),
        current_phase=current,
        phases=phases,
    )


def current_phase(phases: list[PhasePlan], ref: date | None = None) -> str | None:
    """Return the name of the phase containing ``ref`` (default today)."""
    ref = ref or date.today()
    for p in phases:
        start, end = _parse(p.start_date), _parse(p.end_date)
        if start and end and start <= ref <= end:
            return p.name
    return None


def phase_for(plan: PeriodizationPlan | None, ref: date | None = None) -> PhasePlan | None:
    """Return the full :class:`PhasePlan` active at ``ref``."""
    if plan is None:
        return None
    name = current_phase(plan.phases, ref) or plan.current_phase
    for p in plan.phases:
        if p.name == name:
            return p
    return None
