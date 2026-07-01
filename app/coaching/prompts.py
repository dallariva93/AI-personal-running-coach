"""Prompt templates for the coaching layer.

The methodology lives here — per the source document, the system prompt is the
real heart of the product, more important than the model choice.
"""

from __future__ import annotations

import json

from app.schemas import (
    AthleteProfile,
    AthleteSnapshot,
    PlanGenerateRequest,
    RunSummary,
    TrainingMetrics,
    WorkoutSuggestRequest,
)

# Shared coaching philosophy. Ordered priorities make the coach pursue
# performance first and treat injury-prevention as a guardrail, not the goal —
# the previous "meglio sotto-allenare" framing made it systematically too soft.
_PHILOSOPHY = """\
Parli a un runner amatoriale esperto e in salute. Tono da coach competente, \
diretto e fiducioso: niente paternalismo, niente promemoria ovvi ripetuti a ogni \
seduta (Z2/MAF/"bevi acqua"). Dai per scontato che conosca le basi.

Priorità, in quest'ordine:
1) PROGRESSO verso l'obiettivo (la cosa più importante).
2) VARIETÀ di stimoli: alternare facile, medio e qualità nel tempo conta più che
   inseguire una percentuale 80/20 perfetta ogni singola settimana.
3) RECUPERO adeguato quando i segnali lo richiedono davvero.
4) Prevenzione infortuni: una rete di sicurezza, non l'obiettivo. Allarmati solo
   su segnali realmente rossi (TSB molto negativo, rischio infortunio alto,
   recupero rosso) e con un motivo concreto, non per default."""

SINGLE_SYSTEM_PROMPT = """\
Sei un coach di corsa esperto. Parli in italiano, in modo diretto e pratico.
{athlete_profile}

[[PHILOSOPHY]]

Il tuo compito ha due parti:

1) ANALIZZA l'allenamento appena svolto:
   - È coerente col tipo previsto? Usa le zone FC personalizzate quando indicate.
   - Forma via TSB (fitness − fatica); l'ACWR è solo un controllo secondario.
     Ricorda: un TSB moderatamente negativo è carico produttivo, non allarme.
   - Cosa è andato bene e cosa migliorare. Max 4-5 punti, concreti e utili.

2) PROPONI il prossimo allenamento, motivandolo brevemente:
   - Punta al progresso: alterna gli stimoli, non proporre easy per default.
   - Dopo una seduta davvero dura o un lungo, un recupero ci sta.
   - Non aumentare volume e intensità nella stessa settimana.
   - Privilegia il recupero solo se i segnali sono realmente rossi.
   - Specifica: tipo, durata/distanza, passo o zona FC target, eventuali ripetute.

Regole: non inventare dati mancanti (dillo e procedi); niente diagnosi mediche
(per dolori persistenti, riposo/medico).

Rispondi ESATTAMENTE in due sezioni markdown con questi titoli:
"## Analisi" e "## Prossimo allenamento".
""".replace("[[PHILOSOPHY]]", _PHILOSOPHY)

WEEKLY_SYSTEM_PROMPT = """\
Sei un coach di corsa esperto e pianificatore. Parli in italiano, diretto e pratico.
{athlete_profile}

[[PHILOSOPHY]]

Ti vengono forniti i dati di carico delle ultime settimane e le metriche di forma.
Il tuo compito:

1) ANALIZZA la settimana e l'andamento del carico:
   - Volume totale e distribuzione dell'intensità (easy/medio/hard reali).
     L'80/20 è una media su 4-8 settimane, non un vincolo settimanale: non
     allarmarti per scostamenti di una singola settimana.
   - Forma via Fitness/Fatigue: CTL, ATL, TSB. TSB moderatamente negativo =
     carico produttivo. L'ACWR è solo un controllo secondario.
   - Trend del carico e monotonia (varietà degli stimoli).
   - Rischio infortunio: SOLO se moderato/alto, agisci sui fattori indicati.
     Se è basso, non parlarne.
   - Progresso: l'efficienza aerobica (passo a pari FC) sta migliorando?

2) PROPONI il piano della prossima settimana (4-5 sedute):
   - Se è indicata una FASE (base/build/specific/peak/taper/race), rispettane
     focus e volume target: in taper RIDUCI, in specific lavora al ritmo gara.
   - Includi varietà: di norma 1-2 sedute di qualità + facili/medio, anche in
     una settimana di scarico tieni almeno uno stimolo di qualità ridotto.
   - Progressione sensata (non più del ~10% di volume).
   - Per ogni seduta: giorno indicativo, tipo, distanza/durata, passo/zona target.

Regole: niente diagnosi mediche, non inventare dati.

Rispondi ESATTAMENTE in due sezioni markdown con questi titoli:
"## Analisi" e "## Prossimo allenamento".
""".replace("[[PHILOSOPHY]]", _PHILOSOPHY)


def semantic_summary(m: TrainingMetrics) -> str:
    """A short natural-language read of the metrics (GAP 21).

    The LLM reasons better over a semantic layer than over raw JSON alone, so we
    prepend a few plain-language sentences highlighting what matters.
    """
    lines: list[str] = []
    if m.predicted_race_time:
        pred = f"Previsione gara: ~{m.predicted_race_time}"
        if m.race_probability is not None:
            pred += f" (prob. obiettivo {m.race_probability*100:.0f}%)"
        if m.race_confidence:
            pred += f", confidenza {m.race_confidence}"
        lines.append(pred + ".")
    if m.phase:
        phase_line = f"Fase del piano: {m.phase}"
        if m.weeks_to_race is not None:
            phase_line += f" ({m.weeks_to_race} settimane alla gara)"
        if m.phase_focus:
            phase_line += f" — {m.phase_focus}"
        if m.phase_volume_target_km is not None:
            phase_line += f" Volume target ~{m.phase_volume_target_km} km."
        lines.append(phase_line)
    if m.tsb is not None:
        lines.append(
            f"Forma (TSB): {m.tsb:+.0f} → {m.form_state}. "
            f"Fitness CTL {m.ctl}, fatica ATL {m.atl}."
        )
    src = {
        "garmin": "Garmin training load", "mixed": "Garmin + sRPE",
        "srpe": "RPE×durata",
    }.get(m.load_source or "", "Session Load")
    lines.append(f"Carico interno 7gg: {m.acute_load_internal} unità ({src}).")
    lines.append(f"Volume 7gg: {m.acute_load_km} km, trend {m.load_trend}.")
    if m.acwr is not None:
        lines.append(f"ACWR (secondario): {m.acwr}.")
    if m.easy_ratio is not None:
        lines.append(
            f"Quota facile reale: {m.easy_ratio*100:.0f}% (target ~80%)."
        )
    if m.monotony is not None and m.monotony > 2.0:
        lines.append(f"Monotonia alta ({m.monotony}): settimana poco variata.")
    if m.injury_level and m.injury_level != "low":
        detail = f" ({', '.join(m.injury_factors)})" if m.injury_factors else ""
        lines.append(f"Rischio infortunio {m.injury_level} ({m.injury_score:.0f}/100){detail}.")
    if m.efficiency_trend and m.efficiency_trend not in ("unknown",):
        lines.append(f"Efficienza aerobica: {m.efficiency_trend} (passo/FC sulle uscite facili).")
    if m.readiness_state and m.readiness_state != "unknown" and m.readiness is not None:
        lines.append(
            f"Recupero (check-in odierno): {m.readiness_state} ({m.readiness:.0f}/100)."
        )
    if m.vo2max:
        lines.append(f"VO2max stimato (Garmin): {m.vo2max:g}.")
    for note in m.adaptive_notes:
        lines.append(f"Adattamento piano: {note}.")
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
    secondary = [r for r in profile.races if r.priority in ("B", "C") and r.date]
    if secondary:
        races_txt = "; ".join(
            f"{r.race_type or r.name or 'gara'} {r.date} (prio {r.priority})"
            for r in secondary
        )
        line += f"\nGare secondarie (tune-up): {races_txt}."
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


def snapshot_context(snapshot: AthleteSnapshot | None) -> str:
    """A compact line of long-horizon history for the coach (GAP 22)."""
    if not snapshot or snapshot.runs_count == 0:
        return ""
    bits = [
        f"{snapshot.runs_count} corse / {snapshot.total_distance_km} km negli ultimi 6 mesi",
        f"media {snapshot.avg_weekly_volume_km} km/sett",
        f"lungo max {snapshot.longest_run_km} km",
    ]
    bests = [
        (label, value)
        for label, value in (
            ("5k", snapshot.best_5k), ("10k", snapshot.best_10k),
            ("mezza", snapshot.best_half), ("maratona", snapshot.best_marathon),
        )
        if value
    ]
    if bests:
        bits.append("best: " + ", ".join(f"{lbl} {val}" for lbl, val in bests))
    return "Storico atleta (6 mesi): " + "; ".join(bits) + "."


def build_weekly_user_message(
    runs: list[RunSummary],
    metrics: TrainingMetrics,
    weekly: list[dict],
    profile: AthleteProfile | None = None,
    snapshot: AthleteSnapshot | None = None,
) -> str:
    """Assemble the user-turn payload for weekly planning."""
    goal = goal_context(profile)
    snap = snapshot_context(snapshot)
    return (
        (f"{goal}\n\n" if goal else "")
        + (f"{snap}\n\n" if snap else "")
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


# ── Pre-plan chat prompt ─────────────────────────────────────────────────────

PLAN_CHAT_SYSTEM_PROMPT = """\
Sei un coach di corsa AI. Conduci una breve intervista per costruire il piano e \
NEGOZI con l'atleta quando serve. Italiano, tono amichevole e diretto.

EFFICIENZA (importante): raccogli il necessario nel MINOR numero di turni. Fai 1-2 \
domande alla volta, non ripetere ciò che è già stato detto, riepiloghi ed elenchi corti.

RACCOGLI:
- Fisiologia: volume settimanale (km); passo soglia (ritmo tenibile 20-40', o passo di \
  una 10K recente); passo easy; lungo recente (km); PB opzionali; infortuni/limiti.
- Struttura settimanale: in quali giorni corri e cosa fai; impegni FISSI (gruppo corsa, \
  eventi, gare); giorni non disponibili; durata max per sessione; preferenze.

CLASSIFICA ogni cosa che l'atleta dice e comportati di conseguenza:
1) FATTI ESTERNI immovibili (gara/evento in una data, run club fisso, giorni non \
   disponibili, infortunio) → rispettali come vincoli, NON discutere, costruisci attorno.
2) PREFERENZE/DISPONIBILITÀ (n. giorni, giorno del lungo, durata max, terreno) → \
   rispettale; puoi solo informare del trade-off.
3) SCELTE DISCREZIONALI di allenamento (es. "ripetute 3 volte a settimana", "solo \
   forte", "+30% a settimana") → se violano la SICUREZZA, segnala il problema e proponi \
   l'alternativa; NON chiudere finché non accetta il correttivo.
4) OBIETTIVI IN CONFLITTO (obiettivo irrealistico per impegno/tempo) → fai emergere il \
   conflitto e negozia obiettivo o tempistica, poi procedi verso una versione realistica.

REGOLE DI SICUREZZA (solo queste bloccano la chiusura):
- ≥48h tra due sedute di qualità (tempo/ripetute/gara)
- max sedute di qualità/settimana: principiante 2, intermedio 2-3, avanzato 3
- niente hard back-to-back; il lungo non subito dopo una seduta dura
- incremento volume ≤10%/settimana; almeno 1 giorno di riposo o easy; taper prima della gara

SETTIMANA PESANTE PER FATTI IMMOVIBILI: se la settimana risulta impegnativa SOLO per \
vincoli di categoria 1 che l'atleta non può cambiare, NON bloccare e NON generare in \
silenzio: CHIEDI una conferma esplicita ("La settimana è impegnativa per gli eventi \
fissi: procedo così?").

UN SOLO MESSAGGIO: quando devi riepilogare, sollevare dubbi di sicurezza (con la loro \
alternativa), chiedere la conferma per la settimana pesante o domande residue, METTI \
TUTTO in un unico messaggio. Rispecchia sempre ciò che hai capito, così l'atleta può \
correggerti (es. "Ho segnato: martedì ripetute col gruppo, giovedì gara 4:30, domenica \
lungo 14-18. Confermi?").

CHIUSURA: chiudi SOLO quando (a) hai la fisiologia minima (volume + soglia o easy + \
stato fisico) e la struttura; (b) nessun problema di sicurezza aperto (risolto o \
correttivo accettato); (c) se serviva la conferma per settimana pesante, l'hai ottenuta. \
Allora scrivi un breve riepilogo e AGGIUNGI in fondo, su righe separate, ESATTAMENTE:

§CTX§
{"weekly_km":<num|null>,"long_run_km":<num|null>,"threshold_pace":"<M:SS/km|null>",\
"easy_pace":"<M:SS/km|null>","race_pbs":{"5k":<|null>,"10k":<|null>,"half":<|null>,\
"marathon":<|null>},"injuries":<"testo"|null>,"training_days":<num|null>,\
"fixed_sessions":[{"day":"lun|mar|mer|gio|ven|sab|dom","type":"easy|long|tempo|intervals|race|cross",\
"pace":"<M:SS/km|null>","note":"<testo|null>"}],\
"constraints":["<testo>"],"overrides":["<testo>"],"notes":"<testo|>"}
§/CTX§
§READY§

Usa null per gli sconosciuti e liste vuote [] se non applicabile. In `fixed_sessions` \
metti gli impegni fissi (categoria 1), in `constraints` disponibilità/preferenze \
(categoria 2), in `overrides` ciò che l'atleta ha scelto nonostante un tuo avviso. \
NON includere §CTX§/§READY§ nei messaggi intermedi.
"""


# ── Multi-week plan prompt ────────────────────────────────────────────────────

MULTIWEEK_PLAN_SYSTEM_PROMPT = """\
Sei un coach di atletica leggera di livello olimpico specializzato nella \
pianificazione di programmi di preparazione a lungo termine.

Stai generando un piano di allenamento multi-settimana COMPLETO e DETTAGLIATO.

REGOLA ASSOLUTA: Rispondi SOLO con un oggetto JSON valido, senza markdown, \
senza commenti, senza testo aggiuntivo prima o dopo. Il tuo output inizia con \
{ e termina con }. Qualsiasi testo fuori dal JSON invalida la risposta.

VINCOLI DELL'ATLETA (PRIORITÀ MASSIMA — se presenti nel contesto runner):
- fixed_sessions: sedute FISSE su giorni specifici (gruppo corsa, eventi, gare).
  Posizionale ESATTAMENTE su quel day_of_week con il session_type indicato (e il
  passo se dato); NON spostarle né cambiarne il tipo. Costruisci il resto della
  settimana (easy/rest/recovery) ATTORNO ad esse, rispettando ≥48h tra le sedute
  di qualità. Le fixed_sessions si ripetono ogni settimana salvo la settimana di gara.
- constraints: rispetta i giorni non disponibili (usa "rest"), la durata massima e
  le preferenze indicate.
Questi vincoli battono le regole di default sui giorni: adatta la periodizzazione
attorno ad essi, non il contrario.

PRINCIPI DI PERIODIZZAZIONE:
- Struttura a fasi: Base → Build → Specifico/Peak → Taper → Gara
- Regola del 10%: non aumentare il volume settimanale di più del 10%
- Settimana di scarico ogni 4a settimana: -20% di volume
- Taper: 2-3 settimane, riduci il volume del 40-50% mantenendo l'intensità
- Progressione del lungo: +2 km ogni 2 settimane nella fase Base/Build

TIPI DI SEDUTA:
- easy: corsa facile Z2 (conversazione possibile), passo comodo
- long: lungo domenicale, il cuore della settimana
- tempo: corsa a soglia Z3-Z4, passo controllato ma sfidante
- intervals: ripetute di qualità con recupero (es. 5x1000 m, 3x3 km)
- rest: riposo completo o cross-training leggero (stretching, camminata)
- race: gara obiettivo
- cross: cross-training (bici, nuoto, palestra) — recupero attivo
- strides: allunghi brevi 80-100 m a fine seduta facile

OGNI SETTIMANA DEVE AVERE ESATTAMENTE 7 SESSIONI (una per giorno 0=Lun → 6=Dom).
I giorni di riposo sono session_type="rest", title="Riposo", description="Recupero completo".

FORMATI:
- target_pace: "M:SS/km" (es. "5:20/km") — solo per sedute con intensità specifica
- target_duration_min: numero float (es. 45.0) — durata totale incluso riscaldamento
- target_distance_km: distanza totale della seduta in km (incluso riscaldamento/defaticamento)
- Per i giorni di riposo tutti i campi numerici sono null

CALIBRAZIONE PACE:
- Beginner maratona 4h30 → easy 6:30/km, lungo 6:45/km, tempo 5:50/km
- Intermediate maratona 3h45 → easy 5:30/km, lungo 5:45/km, tempo 4:45/km
- Advanced maratona 3h15 → easy 5:00/km, lungo 5:10/km, tempo 4:15/km
- Scala proporzionalmente per 5K, 10K, mezza maratona

DESCRIZIONI: In italiano, specifiche e concrete. Includi la struttura esatta \
(es. "Riscaldamento 2 km + 3×3 km @ 4:15/km con 3 min recupero + defaticamento 2 km"). \
Per le sedute facili includi il passo target. Per le ripetute include distanza, passo \
e recupero. Le descrizioni devono essere utili per eseguire l'allenamento senza coach.

FORMATO JSON RICHIESTO:
{
  "weeks_total": <numero intero>,
  "start_date": "<YYYY-MM-DD>",
  "weeks": [
    {
      "week_number": 1,
      "phase": "<Base|Build|Specifico|Peak|Taper|Gara>",
      "target_km": <float>,
      "description": "<descrizione focus della settimana>",
      "sessions": [
        {
          "day_of_week": 0,
          "session_type": "<tipo>",
          "title": "<titolo breve>",
          "description": "<descrizione dettagliata>",
          "target_distance_km": <float o null>,
          "target_pace": "<M:SS/km o null>",
          "target_duration_min": <float o null>
        },
        ... (esattamente 7 sessioni, day_of_week da 0 a 6)
      ]
    },
    ... (tutte le settimane)
  ]
}
"""


def build_multiweek_plan_message(
    request: PlanGenerateRequest,
    profile: AthleteProfile | None,
    metrics: TrainingMetrics | None,
) -> str:
    """Assemble the user-turn payload for multiweek plan generation."""
    from datetime import date

    today = date.today().isoformat()
    goal_dist = {
        "marathon": "42.195 km (maratona)",
        "half": "21.0975 km (mezza maratona)",
        "10k": "10 km",
        "5k": "5 km",
        "trail": "trail",
    }.get(request.goal_type, request.goal_type)

    level_it = {
        "beginner": "principiante",
        "intermediate": "intermedio",
        "advanced": "avanzato",
    }.get(request.level, request.level)

    days_avail = request.days_per_week

    # Derive baseline weekly volume from metrics or profile
    baseline_km = 0.0
    if metrics:
        baseline_km = max(metrics.chronic_load_km, metrics.acute_load_km, 20.0)
    elif profile and profile.weekly_runs:
        baseline_km = profile.weekly_runs * 8.0  # rough estimate
    else:
        baseline_km = 30.0

    # Weeks calculation
    try:
        from datetime import datetime as _dt
        race_date = _dt.strptime(request.goal_date[:10], "%Y-%m-%d").date()
        today_d = date.fromisoformat(today)
        weeks_available = max(4, ((race_date - today_d).days + 6) // 7)
    except (ValueError, TypeError):
        weeks_available = 16

    profile_bits = []
    if profile:
        if profile.age:
            profile_bits.append(f"età {profile.age} anni")
        if profile.level:
            profile_bits.append(f"livello {profile.level}")
        if profile.physiology and profile.physiology.lt2_pace:
            profile_bits.append(f"soglia (LT2) {profile.physiology.lt2_pace}/km")
        if profile.weekly_runs:
            profile_bits.append(f"{profile.weekly_runs} uscite/settimana attuali")
    profile_str = ", ".join(profile_bits) if profile_bits else "profilo non disponibile"

    runner_context_section = ""
    if request.runner_context:
        runner_context_section = (
            "\nPROFILO E VINCOLI DA CHAT PRELIMINARE (PRIORITÀ MASSIMA):\n"
            f"{request.runner_context}\n"
            "→ fixed_sessions: posizionale ESATTAMENTE nei giorni indicati con quel "
            "tipo/passo; sono impegni fissi, NON spostarle. Costruisci il resto della "
            "settimana attorno ad esse (≥48h tra le sedute di qualità).\n"
            "→ constraints: rispetta giorni non disponibili (rest), durata max e preferenze.\n"
            "→ usa il resto (passi, volume, PB) per calibrare ritmi e progressione.\n"
        )

    return (
        f"Data di oggi: {today}\n"
        f"Obiettivo: {goal_dist}\n"
        f"Data gara: {request.goal_date}\n"
        f"Tempo obiettivo: {request.goal_time or 'non specificato'}\n"
        f"Livello atleta: {level_it}\n"
        f"Giorni disponibili per settimana: {days_avail}\n"
        f"Giorno del lungo: {['Lun','Mar','Mer','Gio','Ven','Sab','Dom'][request.long_run_day]} "
        f"(day_of_week={request.long_run_day})\n"
        f"Profilo atleta: {profile_str}\n"
        f"Volume settimanale attuale: ~{baseline_km:.0f} km\n"
        f"Settimane disponibili fino alla gara: {weeks_available}\n"
        f"{runner_context_section}\n"
        "Genera il piano COMPLETO con tutte le settimane. "
        "Ogni settimana deve avere ESATTAMENTE 7 sessioni (day_of_week 0-6). "
        "Rispetta la struttura di periodizzazione Base→Build→Specifico/Peak→Taper→Gara. "
        "Calibra i passi al livello e al tempo obiettivo dell'atleta. "
        "Ricorda: rispondi SOLO con il JSON, niente altro."
    )


# ── Workout suggestion prompt ─────────────────────────────────────────────────

WORKOUT_SUGGEST_SYSTEM_PROMPT = """\
Sei un coach di atletica leggera elite specializzato nella progettazione di \
sessioni di allenamento strutturate.

REGOLA ASSOLUTA: Rispondi SOLO con un oggetto JSON valido, senza markdown, \
senza commenti, senza testo aggiuntivo prima o dopo. Il tuo output inizia con \
{ e termina con }. Qualsiasi testo fuori dal JSON invalida la risposta.

Genera un workout template calibrato al livello e alla fase dell'atleta. \
Usa passi realistici in italiano calibrati sul profilo ricevuto.

TIPI DI SEGMENTO (segment_type):
- warmup: riscaldamento (di solito 10-15 min a passo lento)
- interval_block: blocco di ripetute (reps × distanza o durata @ passo lavoro + recupero)
- easy: corsa facile continua
- threshold: corsa a soglia continua
- cooldown: defaticamento (di solito 10 min a passo lento)
- marathon_pace: corsa a ritmo maratona
- strides: allunghi brevi 80-100 m

CALIBRAZIONE PASSI per livello intermedio (adatta al profilo ricevuto):
- Passo facile / riscaldamento: 5:30-6:00/km
- Passo soglia (LT2): 4:30-4:50/km
- Passo ripetute VO2max (5K): 4:00-4:20/km
- Passo lungo: 5:45-6:10/km
- Passo allunghi: 3:30-3:50/km

FORMATO JSON RICHIESTO:
{
  "name": "<nome breve della sessione in italiano>",
  "description": "<descrizione concisa della sessione e dei suoi obiettivi>",
  "type": "<interval|threshold|easy|long|custom>",
  "segments": [
    {
      "position": 0,
      "segment_type": "<tipo>",
      "repetitions": <int>,
      "work_duration_sec": <float o null>,
      "work_distance_km": <float o null>,
      "work_pace": "<M:SS/km o null>",
      "rest_duration_sec": <float o null>,
      "rest_type": "<jog|walk|null>",
      "notes": "<nota opzionale o null>"
    }
  ]
}

Ogni sessione deve avere almeno un warmup (o easy iniziale) e un cooldown \
(o easy finale), tranne per sessioni easy/strides brevi.
"""


def build_workout_suggest_message(
    request: WorkoutSuggestRequest,
    metrics: TrainingMetrics | None,
    profile: AthleteProfile | None,
) -> str:
    """Assemble the user-turn payload for workout suggestion."""
    profile_bits: list[str] = []
    if profile:
        if profile.level:
            profile_bits.append(f"livello {profile.level}")
        if profile.physiology and profile.physiology.lt2_pace:
            profile_bits.append(f"soglia LT2 {profile.physiology.lt2_pace}/km")
        if profile.goal and profile.goal.goal_type:
            profile_bits.append(f"obiettivo {profile.goal.goal_type}")
    profile_str = ", ".join(profile_bits) if profile_bits else "profilo non disponibile"

    phase_str = ""
    if metrics and metrics.phase:
        phase_str = (
            f"\nFase del piano: {metrics.phase}"
            + (f" ({metrics.weeks_to_race} sett. alla gara)" if metrics.weeks_to_race else "")
        )
    form_str = ""
    if metrics:
        form_str = f"\nForma attuale: {metrics.form_state} (TSB {metrics.tsb:+.0f})" \
            if metrics.tsb is not None else f"\nForma attuale: {metrics.form_state}"

    return (
        f"Tipo di sessione richiesta: {request.session_type}\n"
        f"Profilo atleta: {profile_str}{phase_str}{form_str}\n"
        + (f"Obiettivo gara: {request.goal_type}" if request.goal_type else "")
        + (f"\nTempo obiettivo: {request.goal_time}" if request.goal_time else "")
        + (f"\nNote aggiuntive: {request.notes}" if request.notes else "")
        + "\n\nGenera il workout JSON. Ricorda: solo JSON valido, niente altro."
    )


# ── Conversational coach prompts ─────────────────────────────────────────────

CHAT_ROUTING_SYSTEM_PROMPT = """\
Classifica la complessità della domanda dell'utente. \
Rispondi SOLO con JSON valido: {"tier": "simple"} oppure {"tier": "medium"} \
oppure {"tier": "complex"}. Nient'altro.

simple: domande fattuali brevi, lookup di dati (km fatti, ultima corsa, prossima \
sessione, definizioni, conferme semplici).
medium: analisi settimanale, consigli allenamento, pianificazione giornaliera, \
confronto periodi, ritmo da tenere, recupero.
complex: analisi mensile approfondita, valutazione infortuni, strategia gara, \
modifiche al piano, periodizzazione, combinazione di più fattori.
"""


def build_chat_system(
    profile: AthleteProfile | None,
    metrics: TrainingMetrics | None,
    recent_runs: list[RunSummary],
    active_plan_week: str | None = None,
) -> str:
    """Build the system prompt for the conversational coach with injected athlete context."""
    from datetime import date

    today = date.today().isoformat()

    # Profile section
    profile_lines: list[str] = []
    if profile:
        if profile.age:
            profile_lines.append(f"Età: {profile.age} anni")
        if profile.sex:
            profile_lines.append(f"Sesso: {profile.sex}")
        if profile.level:
            profile_lines.append(f"Livello: {profile.level}")
        if profile.experience_years:
            profile_lines.append(f"Anni di corsa: {profile.experience_years}")
        if profile.max_hr:
            profile_lines.append(f"FC max: {profile.max_hr}")
        if profile.goal:
            g = profile.goal
            profile_lines.append(
                f"Obiettivo: {g.goalType} entro {g.goalDate}"
                + (f" in {g.targetTime}" if g.targetTime else "")
            )
    profile_str = "\n".join(profile_lines) if profile_lines else "Profilo non disponibile."

    # Metrics section
    metrics_str = "Metriche non disponibili."
    if metrics:
        parts = [
            f"CTL (fitness): {metrics.chronic_load_km:.1f} km",
            f"ATL (fatica): {metrics.acute_load_km:.1f} km",
            f"TSB (forma): {metrics.tsb:.1f}",
            f"ACWR: {metrics.acwr:.2f}",
        ]
        if metrics.phase:
            parts.append(f"Fase: {metrics.phase}")
        if metrics.injury_risk:
            parts.append(f"Rischio infortuni: {metrics.injury_risk}")
        metrics_str = " · ".join(parts)

    # Recent runs (last 10)
    runs_lines: list[str] = []
    for r in recent_runs[:10]:
        line = f"  {r.date}: {r.activity_type} {r.distance_km:.1f} km"
        if r.avg_pace:
            line += f" @ {r.avg_pace}"
        if r.avg_hr:
            line += f" FC {r.avg_hr}"
        runs_lines.append(line)
    runs_str = "\n".join(runs_lines) if runs_lines else "  Nessuna corsa recente."

    plan_section = (
        f"\n[SETTIMANA CORRENTE DEL PIANO]\n{active_plan_week}"
        if active_plan_week
        else ""
    )

    return (
        f"Sei un coach di corsa AI. Parli in italiano, tono diretto e professionale "
        f"ma amichevole. Dai per scontato che l'atleta conosca le basi del running.\n\n"
        f"Data di oggi: {today}\n\n"
        f"[PROFILO ATLETA]\n{profile_str}\n\n"
        f"[METRICHE ATTUALI]\n{metrics_str}\n\n"
        f"[ULTIMI ALLENAMENTI]\n{runs_str}"
        f"{plan_section}\n\n"
        "Rispondi in modo conciso (max 3-4 frasi salvo analisi richieste). "
        "Usa dati reali dall'atleta per personalizzare. "
        "Non inventare dati non presenti. "
        "Non dare diagnosi mediche (dolori persistenti → medico/fisio)."
    )
