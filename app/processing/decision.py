"""Coach Decision Engine v2 (World-Class Roadmap #7).

Turns the quantitative training signals into a single, dominant, structured
"what to do today" recommendation - the decision the home screen leads with.

Pure and deterministic: given the metrics, the athlete profile, today's planned
session, the latest check-in, upcoming sessions and days to race, it returns a
:class:`CoachDecision` with the decision, a concrete prescription, plain-language
reasoning, real confidence (signal disagreement, not just missing-data count),
safety flags, expected outcome (for the feedback loop) and a contextual daily
note.

Rule-based on purpose: it runs offline with zero cost, is fully testable and
never hallucinates. The AI layer can enrich the wording later, but the decision
itself stays explainable and reproducible.

v2 changes:
- Profile awareness: level and risk_tolerance adjust thresholds (P0-1).
- Real confidence: signal disagreement + data uncertainty (P0-7).
- Lookahead: upcoming sessions and days_to_race influence today (P1-3).
- Taper-aware: quality is not downgraded to easy in taper (P0-2/P2-2).
- Expected outcome: each decision carries a testable prediction (P2-1).
- DailyNote 2.0: contextual, varied, race-aware (P3-1).
"""

from __future__ import annotations

from datetime import date

from app.schemas import (
    AthleteProfile,
    CoachDecision,
    DailyCheckin,
    PlanSessionOut,
    TrainingMetrics,
)

# Session-type families (accepts both English plan types and Italian labels).
_HARD_TYPES = {"tempo", "intervals", "intervalli", "threshold", "soglia", "vo2max"}
_LONG_TYPES = {"long", "lungo"}
_REST_TYPES = {"rest", "riposo"}
_EASY_TYPES = {"easy", "recovery", "recupero", "cross", "strides", "medio"}

# Thresholds.
_ACWR_DANGER = 1.5
_TSB_DEEP_FATIGUE = -25.0
_TSB_VERY_FRESH = 15.0

# Taper window: within this many days of race, quality is preserved (P0-2).
_TAPER_DAYS = 14
# Race-day proximity: within 1 day, only rest or shakeout.
_RACE_EVE_DAYS = 1

# Risk-tolerance multipliers for safety thresholds (P0-1).
_RISK_ADJUST = {
    "conservative": 0.85,
    "moderate": 1.0,
    "aggressive": 1.15,
}

# Level-based volume suggestions for no-plan recommendations (P0-1).
_LEVEL_EASY_KM = {
    "beginner": (3.0, 5.0),
    "intermediate": (5.0, 8.0),
    "advanced": (8.0, 12.0),
}
_LEVEL_EASY_MIN = {
    "beginner": (20, 35),
    "intermediate": (35, 50),
    "advanced": (50, 70),
}


def _is_hard(session_type: str | None) -> bool:
    return (session_type or "").lower() in _HARD_TYPES


def _fmt_km(v: float | None) -> str | None:
    if v is None:
        return None
    return f"{int(v)} km" if v == int(v) else f"{v:.1f} km"


def _collect_signals(m: TrainingMetrics) -> list[str]:
    """Human-readable evidence signals the decision rests on."""
    signals: list[str] = []
    if m.tsb is not None:
        signals.append(f"Forma (TSB) {m.tsb:+.0f}")
    if m.acwr is not None:
        signals.append(f"ACWR {m.acwr:.2f}")
    if m.readiness_state and m.readiness_state != "unknown":
        signals.append(f"Recupero {m.readiness_state}")
    if m.injury_level:
        signals.append(f"Rischio infortuni {m.injury_level}")
    if m.form_state and m.form_state != "unknown":
        signals.append(f"Stato: {m.form_state}")
    return signals


def _safety_flags(m: TrainingMetrics, profile: AthleteProfile | None = None) -> list[str]:
    flags: list[str] = []
    risk_mult = _RISK_ADJUST.get(
        (profile.risk_tolerance if profile else "moderate"), 1.0
    )
    acwr_threshold = _ACWR_DANGER * risk_mult
    tsb_threshold = _TSB_DEEP_FATIGUE * risk_mult
    if m.injury_level == "high":
        flags.append("Rischio infortuni alto")
    if m.acwr is not None and m.acwr >= acwr_threshold:
        flags.append(f"Carico acuto elevato (ACWR {m.acwr:.2f})")
    if m.readiness_state == "red":
        flags.append("Recupero insufficiente oggi")
    if m.tsb is not None and m.tsb <= tsb_threshold:
        flags.append("Fatica profonda (TSB molto negativo)")
    if m.monotony is not None and m.monotony >= 2.0:
        flags.append("Monotonia del carico alta: varia gli stimoli")
    return flags


def _missing_data(
    m: TrainingMetrics, checkin: DailyCheckin | None, has_plan: bool, ref: date
) -> list[str]:
    missing: list[str] = []
    if checkin is None or checkin.date != ref.isoformat():
        missing.append("Nessun check-in di oggi (recupero stimato)")
    if m.hrv_rmssd is None:
        missing.append("HRV non disponibile")
    if not has_plan:
        missing.append("Nessun piano attivo: raccomandazione generica")
    return missing


def _confidence(
    missing: list[str], flags: list[str], m: TrainingMetrics
) -> str:
    """Real confidence: blends data uncertainty with signal disagreement (P0-7).

    - Missing data lowers confidence (data uncertainty).
    - Contradictory signals lower confidence (e.g. TSB fresh but readiness red).
    - Safety flags cap confidence at medium (we act, but acknowledge the risk).
    """
    disagreement = _signal_disagreement(m)
    uncertainty = len(missing)
    if uncertainty >= 3 or disagreement >= 2:
        return "low"
    if flags and disagreement >= 1:
        return "low"
    if flags:
        return "medium"
    if uncertainty <= 1 and disagreement == 0:
        return "high"
    return "medium"


def _signal_disagreement(m: TrainingMetrics) -> int:
    """Count pairs of signals that point in opposite directions (P0-7).

    Examples: TSB says fresh but readiness is red; TSB fresh but injury high;
    ACWR high but TSB balanced (load spike without fatigue yet).
    """
    disagreements = 0
    tsb_fresh = m.tsb is not None and m.tsb >= _TSB_VERY_FRESH
    tsb_fatigued = m.tsb is not None and m.tsb <= _TSB_DEEP_FATIGUE
    readiness_low = m.readiness_state == "red"
    injury_high = m.injury_level == "high"
    acwr_high = m.acwr is not None and m.acwr >= _ACWR_DANGER

    if tsb_fresh and readiness_low:
        disagreements += 1
    if tsb_fresh and injury_high:
        disagreements += 1
    if tsb_fatigued and m.readiness_state == "green":
        disagreements += 1
    if acwr_high and not tsb_fatigued and not readiness_low:
        disagreements += 1
    return disagreements


def daily_note(
    decision: str,
    m: TrainingMetrics,
    profile: AthleteProfile | None = None,
    days_to_race: int | None = None,
) -> str:
    """DailyNote 2.0: contextual, varied, race-aware one-liner (P3-1).

    Template system with variable slots: the note adapts to the decision, the
    dominant live signal, the phase of the macrocycle and the proximity to the
    goal race. Deterministic but varied enough to not feel repetitive.
    """
    tsb = m.tsb
    phase = m.phase
    in_taper = phase == "taper" or (
        days_to_race is not None and days_to_race <= _TAPER_DAYS
    )
    race_imminent = days_to_race is not None and days_to_race <= _RACE_EVE_DAYS

    if race_imminent and decision != "rest":
        return "Domani e gara: oggi solo un leggero shakeout, niente di piu."
    if race_imminent and decision == "rest":
        return "Riposo completo: la forma si fa fermandosi al momento giusto."

    if in_taper:
        if decision == "rest":
            return "Taper: il riposo di oggi e quello che trasforma la fatica in forma."
        if decision in ("quality", "run"):
            return "Taper: quality breve e brillante, non cercare la fatica."
        return "Taper: corri leggero, mangia e dormi. La forma arriva da sola."

    if decision == "rest":
        return "Il riposo di oggi e un investimento: recupera davvero, senza sensi di colpa."
    if decision == "modify":
        return "Ascolta il corpo oggi: alleggerire ora protegge tutta la settimana."
    if decision == "long":
        return "Il lungo si corre con la testa: parti piano, finisci forte."
    if decision == "quality":
        if tsb is not None and tsb >= _TSB_VERY_FRESH:
            return "Sei fresco: rendi ogni ripetuta pulita, non solo veloce."
        return "Qualita oggi: punta alla precisione del ritmo, non alla velocita."
    # easy / run
    if tsb is not None and tsb <= -15:
        return "Hai ancora fatica nelle gambe: oggi vinci se corri piano."
    if tsb is not None and tsb >= 15:
        return "Ti senti bene, ma non sprecare energia nei primi km: resta in controllo."
    if phase == "base":
        return "Fase base: costruisci il fondo, ogni km facile e un mattone."
    if phase == "build":
        return "Fase build: il volume sale, ma la pazienza nei facili e la tua arma."
    if phase == "specific":
        return "Fase specifica: ogni seduta ha un obiettivo preciso, non improvvisare."
    return "Costruisci continuita, non solo chilometri: una corsa facile fatta bene conta."


def decide_today(
    metrics: TrainingMetrics,
    profile: AthleteProfile | None,
    today_session: PlanSessionOut | None,
    checkin: DailyCheckin | None,
    ref: date | None = None,
    next_sessions: list[PlanSessionOut] | None = None,
) -> CoachDecision:
    """Produce today's structured coaching decision with its daily note (v2).

    ``next_sessions`` is the lookahead window (P1-3): upcoming planned sessions
    for the next 7 days, used to avoid stacking quality sessions and to preserve
    taper logic.
    """
    ref = ref or date.today()
    days_to_race = metrics.weeks_to_race
    if days_to_race is not None:
        days_to_race = days_to_race * 7
    decision = _decide_core(
        metrics, profile, today_session, checkin, ref, next_sessions, days_to_race
    )
    decision.daily_note = daily_note(
        decision.decision, metrics, profile, days_to_race
    )
    decision.expected_outcome = _expected_outcome(decision, metrics, days_to_race)
    decision.engine_version = "2.0"
    return decision


def _expected_outcome(
    decision: CoachDecision,
    m: TrainingMetrics,
    days_to_race: int | None,
) -> str:
    """What the coach expects to happen, for retrospective calibration (P2-1).

    A short, testable prediction that can be compared against the actual
    execution score and the next-day readiness.
    """
    if decision.decision == "rest":
        return "readiness improves by >=10 pts next check-in"
    if decision.decision == "modify":
        return "readiness improves by >=5 pts; no injury flare-up"
    if decision.decision == "quality":
        return "execution_score >=70; RPE <=8; readiness stable or up"
    if decision.decision == "long":
        return "execution_score >=65; RPE <=7; no soreness spike next day"
    return "execution_score >=60; RPE <=6; readiness stable"


def _in_taper(days_to_race: int | None) -> bool:
    return days_to_race is not None and days_to_race <= _TAPER_DAYS


def _race_eve(days_to_race: int | None) -> bool:
    return days_to_race is not None and days_to_race <= _RACE_EVE_DAYS


def _has_quality_tomorrow(
    next_sessions: list[PlanSessionOut] | None, ref: date
) -> bool:
    """Check if there is a hard session scheduled tomorrow (P1-3 lookahead)."""
    if not next_sessions:
        return False
    for sess in next_sessions:
        st = (sess.session_type or "").lower()
        if _is_hard(st):
            return True
    return False


def _level_easy_km(profile: AthleteProfile | None) -> tuple[float, float]:
    level = (profile.level if profile else "intermediate")
    return _LEVEL_EASY_KM.get(level, _LEVEL_EASY_KM["intermediate"])


def _level_easy_min(profile: AthleteProfile | None) -> tuple[int, int]:
    level = (profile.level if profile else "intermediate")
    return _LEVEL_EASY_MIN.get(level, _LEVEL_EASY_MIN["intermediate"])


def _decide_core(
    metrics: TrainingMetrics,
    profile: AthleteProfile | None,
    today_session: PlanSessionOut | None,
    checkin: DailyCheckin | None,
    ref: date | None = None,
    next_sessions: list[PlanSessionOut] | None = None,
    days_to_race: int | None = None,
) -> CoachDecision:
    """The rule cascade producing the decision (v2: profile + lookahead + taper)."""
    ref = ref or date.today()
    signals = _collect_signals(metrics)
    flags = _safety_flags(metrics, profile)
    missing = _missing_data(metrics, checkin, today_session is not None, ref)
    confidence = _confidence(missing, flags, metrics)

    should_ease = bool(flags)
    taper = _in_taper(days_to_race)
    race_eve = _race_eve(days_to_race)
    quality_tomorrow = _has_quality_tomorrow(next_sessions, ref)

    # -- Case A: a plan session is scheduled today ---------------------------
    if today_session is not None:
        st = (today_session.session_type or "easy").lower()
        base_km = today_session.target_distance_km
        base_pace = today_session.target_pace
        base_dur = today_session.target_duration_min

        if st in _REST_TYPES:
            return CoachDecision(
                date=ref.isoformat(),
                decision="rest",
                headline="Riposo",
                prescription="Giornata di riposo pianificata: recupera e rigenera.",
                rationale=(
                    "Il recupero e parte dell'allenamento: e quando il corpo "
                    "assorbe il carico e diventa piu forte."
                ),
                confidence=confidence,
                signals=signals,
                missing_data=missing,
                alternatives=["Mobilita o stretching leggero", "Camminata rigenerante"],
                safety_flags=flags,
                plan_session_id=today_session.id,
                session_type="rest",
            )

        # P0-2: in taper, do NOT downgrade quality to easy unless injury is high.
        # Outside taper, safety flags downgrade quality as before.
        if _is_hard(st) and should_ease and not taper:
            reason = flags[0] if flags else "segnali di affaticamento"
            return CoachDecision(
                date=ref.isoformat(),
                decision="modify",
                headline="Allenamento alleggerito",
                prescription=(
                    f"Oggi era previsto un lavoro intenso ({today_session.title}). "
                    "Sostituiscilo con una corsa facile e rilassata, o riposa."
                ),
                rationale=(
                    f"{reason}: forzare la qualita oggi aumenta il rischio senza "
                    "beneficio. Sposta lo stimolo intenso a quando sarai recuperato."
                ),
                confidence=confidence,
                signals=signals,
                missing_data=missing,
                alternatives=[
                    "Corsa facile 30-40 min in Z2",
                    "Riposo completo",
                    "Riprogramma il lavoro intenso tra 1-2 giorni",
                ],
                safety_flags=flags,
                plan_session_id=today_session.id,
                session_type="easy",
                target_pace=None,
            )

        # In taper with safety flags: reduce volume but keep the quality stimulus.
        if _is_hard(st) and should_ease and taper:
            reduced_km = base_km * 0.6 if base_km else None
            return CoachDecision(
                date=ref.isoformat(),
                decision="quality",
                headline=f"Qualita ridotta (taper): {today_session.title}",
                prescription=(
                    f"Taper: mantieni il ritmo target ma riduci il volume "
                    f"({int(reduced_km) if reduced_km else '-'} km invece di "
                    f"{int(base_km) if base_km else '-'})."
                ),
                rationale=(
                    "In taper il stimolo qualita va preservato ma ridotto: "
                    "mantieni il ritmo, taglia il volume per arrivare fresco alla gara."
                ),
                confidence=confidence,
                signals=signals,
                missing_data=missing,
                alternatives=["Riduci ulteriormente se la sensazione non e buona"],
                safety_flags=flags,
                plan_session_id=today_session.id,
                session_type=st,
                target_distance_km=reduced_km,
                target_pace=base_pace,
                target_duration_min=base_dur * 0.6 if base_dur else None,
            )

        # P1-3: if quality is scheduled today AND tomorrow, warn about stacking.
        extra_alt = []
        if _is_hard(st) and quality_tomorrow:
            extra_alt.append("Valuta di spostare una delle due sedute di qualita")

        # Race eve: only rest or very light shakeout.
        if race_eve and _is_hard(st):
            return CoachDecision(
                date=ref.isoformat(),
                decision="easy",
                headline="Vigilia di gara: solo shakeout",
                prescription=(
                    "Domani e gara: sostituisci con 15-20 min molto leggeri "
                    "con 2-3 progressioni, niente lavoro intenso."
                ),
                rationale=(
                    "La qualita oggi spreccherebbe glicogeno e crearebbe fatica "
                    "inutile il giorno prima della gara."
                ),
                confidence=confidence,
                signals=signals,
                missing_data=missing,
                alternatives=["Riposo completo se preferisci"],
                safety_flags=flags,
                plan_session_id=today_session.id,
                session_type="easy",
            )

        # Follow the plan.
        decision = "long" if st in _LONG_TYPES else ("quality" if _is_hard(st) else "easy")
        headline = today_session.title or f"Sessione {st}"
        prescr = today_session.description or _prescription_from(st, base_km, base_dur, base_pace)
        rationale = (
            "In linea con la tua forma: segui il piano di oggi."
            if not should_ease
            else "Procedi ma resta in ascolto del corpo: fermati se qualcosa non va."
        )
        return CoachDecision(
            date=ref.isoformat(),
            decision=decision,
            headline=headline,
            prescription=prescr,
            rationale=rationale,
            confidence=confidence,
            signals=signals,
            missing_data=missing,
            alternatives=_alternatives_for(decision) + extra_alt,
            safety_flags=flags,
            plan_session_id=today_session.id,
            session_type=st,
            target_distance_km=base_km,
            target_pace=base_pace,
            target_duration_min=base_dur,
        )

    # -- Case B: no plan session today - recommend from live signals ----------
    if should_ease:
        rest = metrics.injury_level == "high" or metrics.readiness_state == "red"
        if rest:
            return CoachDecision(
                date=ref.isoformat(),
                decision="rest",
                headline="Meglio riposare oggi",
                prescription="Prenditi un giorno di recupero: niente corsa intensa.",
                rationale=(
                    (flags[0] if flags else "I segnali di recupero sono bassi")
                    + ". Un giorno di riposo ora protegge le prossime settimane."
                ),
                confidence=confidence,
                signals=signals,
                missing_data=missing,
                alternatives=["Camminata leggera", "Mobilita e stretching"],
                safety_flags=flags,
            )
        return CoachDecision(
            date=ref.isoformat(),
            decision="easy",
            headline="Corsa facile e breve",
            prescription="Corsa rilassata 30-40 min in Z2, senza forzare il passo.",
            rationale=(
                "I segnali suggeriscono prudenza: mantieni il movimento ma tieni "
                "l'intensita bassa per favorire il recupero."
            ),
            confidence=confidence,
            signals=signals,
            missing_data=missing,
            alternatives=["Riposo completo", "Cross-training leggero"],
            safety_flags=flags,
            session_type="easy",
        )

    if race_eve:
        return CoachDecision(
            date=ref.isoformat(),
            decision="easy",
            headline="Vigilia di gara: shakeout leggero",
            prescription="15-20 min molto leggeri con 2-3 progressioni di 100 m.",
            rationale="Attiva le gambe senza accumulare fatica prima della gara.",
            confidence=confidence,
            signals=signals,
            missing_data=missing,
            alternatives=["Riposo completo se preferisci"],
            safety_flags=flags,
            session_type="easy",
        )

    if metrics.tsb is not None and metrics.tsb >= _TSB_VERY_FRESH and not taper:
        return CoachDecision(
            date=ref.isoformat(),
            decision="quality",
            headline="Sei fresco: giornata di qualita",
            prescription=(
                "Approfitta della freschezza: intervalli o un medio-veloce, "
                "es. 5x1000 in Z4 o 20-30 min a ritmo controllato."
            ),
            rationale=(
                "La tua forma e alta (TSB positivo) e il carico e sotto controllo: "
                "e il momento giusto per uno stimolo di qualita che faccia progredire."
            ),
            confidence=confidence,
            signals=signals,
            missing_data=missing,
            alternatives=["Corsa facile lunga", "Fartlek libero"],
            safety_flags=flags,
            session_type="tempo",
        )

    # P0-1: level-aware easy run recommendation.
    lo_km, hi_km = _level_easy_km(profile)
    lo_min, hi_min = _level_easy_min(profile)
    return CoachDecision(
        date=ref.isoformat(),
        decision="easy",
        headline="Corsa facile",
        prescription=(
            f"Corsa aerobica in Z2, {lo_min}-{hi_min} min "
            f"({lo_km:.0f}-{hi_km:.0f} km) a ritmo conversazionale."
        ),
        rationale=(
            "Nessuna seduta pianificata oggi e i segnali sono nella norma: "
            "una corsa facile costruisce la base senza aggiungere fatica."
        ),
        confidence=confidence,
        signals=signals,
        missing_data=missing,
        alternatives=["Riposo se preferisci", "Cross-training"],
        safety_flags=flags,
        session_type="easy",
    )


def _prescription_from(
    st: str, km: float | None, dur: float | None, pace: str | None
) -> str:
    parts: list[str] = []
    km_s = _fmt_km(km)
    if km_s:
        parts.append(km_s)
    if dur:
        parts.append(f"{int(dur)} min")
    if pace:
        parts.append(f"a {pace}")
    tail = " ".join(parts) if parts else ""
    label = {
        "tempo": "Medio/soglia",
        "intervals": "Intervalli",
        "intervalli": "Intervalli",
        "long": "Lungo",
        "lungo": "Lungo",
        "easy": "Corsa facile",
        "recovery": "Recupero",
    }.get(st, st.capitalize())
    return f"{label}{': ' + tail if tail else ''}".strip()


def _alternatives_for(decision: str) -> list[str]:
    if decision == "long":
        return ["Spezza il lungo in 2 uscite se sei stanco", "Riduci di 15–20% se serve"]
    if decision == "quality":
        return ["Riduci le ripetute se il passo non arriva", "Sposta a domani se stanco"]
    return ["Riposo se preferisci", "Cross-training leggero"]
