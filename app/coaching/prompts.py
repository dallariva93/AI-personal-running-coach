"""Prompt templates for the coaching layer.

The methodology lives here — per the source document, the system prompt is the
real heart of the product, more important than the model choice.
"""

from __future__ import annotations

import json

from app.schemas import AthleteProfile, RunSummary, TrainingMetrics

SINGLE_SYSTEM_PROMPT = """\
Sei un coach di corsa esperto. Parli in italiano, in modo diretto e pratico.
{athlete_profile}

Il tuo compito ha due parti:

1) ANALIZZA l'allenamento appena svolto:
   - È coerente col tipo previsto (es. un "easy" deve restare in Z1-Z2)?
   - Segnali di affaticamento o sovraccarico. Guarda PRIMA il TSB (forma =
     fitness − fatica): TSB molto negativo = affaticato. L'ACWR è un controllo
     secondario. Considera anche FC alta a parità di passo e RPE alto su sforzo basso.
   - Cosa è andato bene, cosa migliorare. Massimo 4-5 punti, concreti.

2) PROPONI il prossimo allenamento, motivandolo brevemente:
   - Rispetta la distribuzione 80/20 (circa 80% facile, 20% intenso a settimana).
   - Dopo una sessione dura o un lungo, proponi recupero/easy.
   - Progressione graduale: non aumentare volume e intensità nella stessa settimana.
   - Se i segnali (forma, ACWR, monotonia) sono rossi, privilegia il recupero.
   - Specifica: tipo, durata o distanza, passo/zona FC target, eventuali ripetute.

Regole:
- Sii prudente sugli infortuni: meglio sotto-allenare che spingere su segnali rossi.
- Non inventare dati che non hai. Se mancano (es. niente RPE), dillo e procedi.
- Niente diagnosi mediche. Per dolori persistenti, suggerisci riposo/medico.

Rispondi ESATTAMENTE in due sezioni markdown con questi titoli:
"## Analisi" e "## Prossimo allenamento".
"""

WEEKLY_SYSTEM_PROMPT = """\
Sei un coach di corsa esperto e pianificatore. Parli in italiano, diretto e pratico.
{athlete_profile}

Ti vengono forniti i dati di carico delle ultime settimane e le metriche di forma.
Il tuo compito:

1) ANALIZZA la settimana e l'andamento del carico:
   - Volume totale e distribuzione 80/20 (basata sull'intensità reale).
   - Forma via modello Fitness/Fatigue: CTL (fitness), ATL (fatica),
     TSB (forma = CTL − ATL). L'ACWR è un controllo secondario.
   - Trend del carico (in salita, stabile, in discesa) e rischi associati.
   - Monotonia: la settimana è troppo uniforme (rischio) o ben variata?

2) PROPONI il piano della prossima settimana (4-5 sedute):
   - Bilancia facile/intenso secondo l'80/20.
   - Tieni conto dello stato di forma e dell'ACWR (se alto, settimana di scarico).
   - Una progressione settimanale sensata (non più del ~10% di volume).
   - Per ogni seduta: giorno indicativo, tipo, distanza/durata, passo/zona target.

Regole: prudenza sugli infortuni, niente diagnosi mediche, non inventare dati.

Rispondi ESATTAMENTE in due sezioni markdown con questi titoli:
"## Analisi" e "## Prossimo allenamento".
"""


def semantic_summary(m: TrainingMetrics) -> str:
    """A short natural-language read of the metrics (GAP 21).

    The LLM reasons better over a semantic layer than over raw JSON alone, so we
    prepend a few plain-language sentences highlighting what matters.
    """
    lines: list[str] = []
    if m.tsb is not None:
        lines.append(
            f"Forma (TSB): {m.tsb:+.0f} → {m.form_state}. "
            f"Fitness CTL {m.ctl}, fatica ATL {m.atl}."
        )
    lines.append(f"Carico interno 7gg: {m.acute_load_internal} unità (Session Load).")
    lines.append(f"Volume 7gg: {m.acute_load_km} km, trend {m.load_trend}.")
    if m.acwr is not None:
        lines.append(f"ACWR (secondario): {m.acwr}.")
    if m.easy_ratio is not None:
        lines.append(
            f"Quota facile reale: {m.easy_ratio*100:.0f}% (target ~80%)."
        )
    if m.monotony is not None and m.monotony > 2.0:
        lines.append(f"Monotonia alta ({m.monotony}): settimana poco variata.")
    return "Sintesi:\n- " + "\n- ".join(lines)


def goal_context(profile: AthleteProfile | None) -> str:
    """A line describing the target race so the coach trains *towards* it."""
    if not profile or not profile.goal:
        return ""
    g = profile.goal
    parts = [f"Obiettivo: {g.goal_type}"]
    if g.target_time:
        parts.append(f"tempo target {g.target_time}")
    days = g.days_to_go()
    if g.target_date:
        when = f"il {g.target_date}"
        if days is not None:
            when += f" (tra {days} giorni, ~{max(0, days)//7} settimane)"
        parts.append(when)
    parts.append(f"priorità {g.priority}")
    line = "Gara obiettivo → " + ", ".join(parts) + "."
    if profile.available_days:
        line += f"\nGiorni disponibili: {', '.join(profile.available_days)}."
    return line


def build_single_user_message(
    run: RunSummary,
    history: list[RunSummary],
    metrics: TrainingMetrics,
    profile: AthleteProfile | None = None,
) -> str:
    """Assemble the user-turn payload for single-run coaching."""
    history_lines = [
        f"{h.date} | {h.activity_type} {h.distance_km}km {h.avg_pace or '?'} "
        f"FC{h.avg_hr or '?'}"
        for h in history[:10]
    ]
    goal = goal_context(profile)
    return (
        (f"{goal}\n\n" if goal else "")
        + f"{semantic_summary(metrics)}\n\n"
        "Metriche di carico e forma:\n"
        f"{json.dumps(metrics.model_dump(), ensure_ascii=False, indent=2)}\n\n"
        "Storico recente (una riga per corsa):\n"
        + ("\n".join(history_lines) if history_lines else "(nessuno)")
        + "\n\nAllenamento appena svolto:\n"
        f"{json.dumps(run.model_dump(), ensure_ascii=False, indent=2)}"
    )


def build_weekly_user_message(
    runs: list[RunSummary],
    metrics: TrainingMetrics,
    weekly: list[dict],
    profile: AthleteProfile | None = None,
) -> str:
    """Assemble the user-turn payload for weekly planning."""
    goal = goal_context(profile)
    return (
        (f"{goal}\n\n" if goal else "")
        + f"{semantic_summary(metrics)}\n\n"
        "Metriche di carico e forma:\n"
        f"{json.dumps(metrics.model_dump(), ensure_ascii=False, indent=2)}\n\n"
        "Carico per settimana (le ultime):\n"
        f"{json.dumps(weekly, ensure_ascii=False, indent=2)}\n\n"
        "Corse della finestra recente:\n"
        + "\n".join(
            f"{r.date} | {r.activity_type} {r.distance_km}km {r.avg_pace or '?'} "
            f"FC{r.avg_hr or '?'}"
            for r in runs[:14]
        )
    )
