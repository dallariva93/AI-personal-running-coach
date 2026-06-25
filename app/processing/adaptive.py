"""Adaptive planning engine (Fase 4).

Periodization gives the *static* plan; this layer makes it **react** to how the
athlete is actually responding. It folds the live signals — injury risk, daily
readiness and progress versus the goal — into a single volume multiplier applied
to the phase target, plus human-readable notes explaining every adjustment.

Pure function: deterministic given a :class:`TrainingMetrics`.
"""

from __future__ import annotations

from app.schemas import TrainingMetrics

# Bounds so a single bad day can't zero the plan nor let it run away.
_MIN_FACTOR = 0.5
_MAX_FACTOR = 1.1


def adapt_plan(m: TrainingMetrics) -> tuple[float, list[str]]:
    """Return ``(volume_multiplier, notes)`` adapting the plan to live signals."""
    factor = 1.0
    notes: list[str] = []

    if m.injury_level == "high":
        factor *= 0.8
        notes.append("rischio infortunio alto: volume ridotto (-20%)")
    elif m.injury_level == "moderate":
        factor *= 0.9
        notes.append("rischio infortunio moderato: progressione prudente (-10%)")

    if m.readiness_state == "red":
        factor *= 0.8
        notes.append("recupero basso (check-in): settimana più leggera")

    if m.tsb is not None and m.tsb < -25:
        factor *= 0.9
        notes.append("fatica elevata (TSB molto negativo): assorbi il carico")

    # Progress vs goal: don't just pile on volume — steer the emphasis.
    if m.race_probability is not None and m.weeks_to_race and m.weeks_to_race > 3:
        if m.race_probability < 0.4:
            notes.append(
                "sei dietro all'obiettivo: priorità a qualità e lavoro specifico"
            )
        elif m.race_probability > 0.9:
            notes.append("ampiamente in linea con l'obiettivo: consolida, non strafare")

    factor = round(max(_MIN_FACTOR, min(_MAX_FACTOR, factor)), 2)
    return factor, notes
