"""Plan explainability — the "why" behind each week (Fase F, section 2.7).

Coach-grade trust and teaching: every week carries a short rationale explaining
its intent (phase purpose, where it sits in the block, why the volume moves the
way it does — build, deload, peak, taper, race). Pure and derived from what the
plan already persists (phase, week number, deload marker, race presence), so no
extra state is stored.
"""

from __future__ import annotations

_PHASE_INTENT = {
    "Base": "costruire il motore aerobico con volume facile (80/20)",
    "Build": "aggiungere volume e introdurre il lavoro di soglia",
    "Specifico": "allenare il ritmo gara e la resistenza specifica",
    "Peak": "affinare la forma: meno volume, qualità vicino al ritmo gara",
    "Taper": "scaricare la fatica mantenendo l'affilatura",
    "Gara": "arrivare freschi e correre la gara",
}


def week_rationale(
    phase: str,
    week_number: int,
    weeks_total: int,
    *,
    is_deload: bool = False,
    is_race_week: bool = False,
) -> str:
    """One-sentence explanation of why this week looks the way it does."""
    intent = _PHASE_INTENT.get(phase, "proseguire la preparazione")
    weeks_to_race = max(0, weeks_total - week_number)

    if is_race_week:
        return f"Settimana gara ({phase}): {intent}. Fidati del lavoro fatto."
    if is_deload:
        return (
            f"Scarico in fase {phase}: volume ridotto (~-20%) per assorbire il "
            f"carico e prevenire l'infortunio prima di ripartire in progressione."
        )
    if phase == "Taper":
        return (
            f"Taper a {weeks_to_race} settimane dalla gara: riduci il volume ma "
            f"mantieni un po' di intensità per restare affilato."
        )
    tail = (
        f" A {weeks_to_race} settimane dalla gara." if weeks_to_race else ""
    )
    return f"Fase {phase}: {intent}.{tail}"
