"""What-if counterfactuals on the plan (Roadmap A7).

Turns the plan from a document into a simulator: "what happens if I skip the
long run / get sick for a week / add a training day?". A pure function clones
the projected load series in memory, applies the change, re-projects CTL/ATL/TSB
forward to race day with the *same* Banister EWMA the live metrics use
(:func:`app.processing.metrics.project_form`), and nudges the race prediction by
the resulting fitness delta.

Pure and side-effect-free: no DB, no dates.today(). The DB-reading orchestrator
(:mod:`app.services.whatif_service`) derives the daily loads, the planned
sessions and the baseline prediction, then calls :func:`simulate_scenario`.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta

from app.processing.metrics import project_form

# The three v0 scenarios (enumerated — the API rejects anything else).
SCENARIOS = ("skip_next_long", "sick_one_week", "add_training_day")

_LONG_TYPES = {"long", "lungo"}
_EASY_TYPES = {"easy", "recupero", "recovery", "medio"}
_DEFAULT_EASY_LOAD = 24.0  # sRPE fallback for an added easy day (RPE 3 × ~48min)

# Race-time elasticity to fitness (A7 v0): a 10% loss of projected CTL at race
# day ≈ this fraction slower. Deliberately conservative and documented — the
# what-if surfaces *direction and rough magnitude*, not a race-day guarantee.
_CTL_ELASTICITY = 0.5

# TSB bands at race day used for the qualitative risk notes.
_TSB_FLAT_MIN = -10.0   # below this: likely arriving fatigued
_TSB_FLAT_MAX = 25.0    # above this: likely detrained / over-tapered


@dataclass
class PlannedSession:
    """One future prescribed session, with its projected internal (sRPE) load."""

    date: date
    session_type: str
    load: float


@dataclass
class WhatIfResult:
    """Baseline-vs-scenario comparison for one what-if (A7). Zero persistence."""

    scenario: str
    baseline_race_seconds: float | None
    scenario_race_seconds: float | None
    race_time_delta_seconds: float | None  # scenario - baseline; +ve = slower
    baseline_tsb_at_race: float
    scenario_tsb_at_race: float
    baseline_ctl_at_race: float
    scenario_ctl_at_race: float
    risk_notes: list[str] = field(default_factory=list)


def _baseline_daily(
    past_daily_loads: dict[date, float], planned: list[PlannedSession]
) -> dict[date, float]:
    daily = dict(past_daily_loads)
    for s in planned:
        daily[s.date] = daily.get(s.date, 0.0) + s.load
    return daily


def _apply_scenario(
    scenario: str, planned: list[PlannedSession], ref: date
) -> tuple[list[PlannedSession], str | None]:
    """Return the modified planned sessions and an optional headline note."""
    if scenario == "skip_next_long":
        for i, s in enumerate(planned):
            if s.session_type.lower() in _LONG_TYPES and s.date > ref:
                dropped = planned[:i] + planned[i + 1:]
                return dropped, f"Salti il lungo del {s.date.isoformat()}"
        return list(planned), "Nessun lungo in programma da saltare"

    if scenario == "sick_one_week":
        window_end = ref + timedelta(days=7)
        kept = [s for s in planned if not (ref < s.date <= window_end)]
        return kept, "Settimana di stop per malattia"

    if scenario == "add_training_day":
        easy_loads = [s.load for s in planned if s.session_type.lower() in _EASY_TYPES]
        added_load = round(statistics.median(easy_loads), 1) if easy_loads else _DEFAULT_EASY_LOAD
        taken = {s.date for s in planned}
        free = next(
            (ref + timedelta(days=i) for i in range(1, 8) if ref + timedelta(days=i) not in taken),
            None,
        )
        if free is None:
            return list(planned), "Settimana già piena: nessun giorno libero"
        extra = PlannedSession(date=free, session_type="easy", load=added_load)
        return planned + [extra], f"Aggiungi un facile il {free.isoformat()}"

    return list(planned), None


def _risk_notes(
    scenario: str,
    headline: str | None,
    baseline_ctl: float,
    scenario_ctl: float,
    scenario_tsb: float,
    delta_seconds: float | None,
) -> list[str]:
    notes: list[str] = []
    if headline:
        notes.append(headline)

    ctl_drop = baseline_ctl - scenario_ctl
    if ctl_drop >= 1.0:
        notes.append(f"Fitness proiettata più bassa (CTL {scenario_ctl:g} vs {baseline_ctl:g}).")
    elif ctl_drop <= -1.0:
        notes.append(f"Fitness proiettata più alta (CTL {scenario_ctl:g} vs {baseline_ctl:g}).")

    if scenario == "add_training_day" and scenario_tsb <= _TSB_FLAT_MIN:
        notes.append("Occhio al recupero: arrivi con più fatica, rischio infortuni in aumento.")
    if scenario_tsb < _TSB_FLAT_MIN:
        notes.append("Rischi di arrivare alla gara affaticato (TSB molto negativo).")
    elif scenario_tsb > _TSB_FLAT_MAX:
        notes.append("Rischi di arrivare scarico/detrained (TSB troppo alto).")

    if delta_seconds is not None:
        if delta_seconds > 1.0:
            notes.append(f"Previsione gara ~{int(round(delta_seconds))}s più lenta.")
        elif delta_seconds < -1.0:
            notes.append(f"Previsione gara ~{int(round(-delta_seconds))}s più veloce.")
    return notes


def simulate_scenario(
    scenario: str,
    past_daily_loads: dict[date, float],
    planned: list[PlannedSession],
    ref: date,
    race_date: date,
    base_predicted_seconds: float | None,
) -> WhatIfResult:
    """Simulate one what-if scenario. Pure — clones everything in memory."""
    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown scenario: {scenario!r}")

    baseline_daily = _baseline_daily(past_daily_loads, planned)
    modified_planned, headline = _apply_scenario(scenario, planned, ref)
    scenario_daily = _baseline_daily(past_daily_loads, modified_planned)

    base_ctl, _base_atl, base_tsb = project_form(baseline_daily, race_date)
    scen_ctl, _scen_atl, scen_tsb = project_form(scenario_daily, race_date)

    delta_seconds = None
    scenario_seconds = None
    if base_predicted_seconds is not None:
        # Lower projected fitness at race day → slower; higher → faster.
        rel = (base_ctl - scen_ctl) / base_ctl if base_ctl > 0 else 0.0
        delta_seconds = round(base_predicted_seconds * _CTL_ELASTICITY * rel, 0)
        scenario_seconds = round(base_predicted_seconds + delta_seconds, 0)

    return WhatIfResult(
        scenario=scenario,
        baseline_race_seconds=base_predicted_seconds,
        scenario_race_seconds=scenario_seconds,
        race_time_delta_seconds=delta_seconds,
        baseline_tsb_at_race=base_tsb,
        scenario_tsb_at_race=scen_tsb,
        baseline_ctl_at_race=base_ctl,
        scenario_ctl_at_race=scen_ctl,
        risk_notes=_risk_notes(
            scenario, headline, base_ctl, scen_ctl, scen_tsb, delta_seconds
        ),
    )
