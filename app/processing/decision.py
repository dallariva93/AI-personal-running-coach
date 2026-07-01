"""Coach Decision Engine v1 (World-Class Roadmap #7).

Turns the quantitative training signals into a single, dominant, structured
"what to do today" recommendation — the decision the home screen leads with.

Pure and deterministic: given the metrics, the athlete profile, today's planned
session and the latest check-in it returns a :class:`CoachDecision` with the
decision, a concrete prescription, plain-language reasoning, the confidence, the
signals it used, the data that was missing, alternatives and safety flags.

Rule-based on purpose: it runs offline with zero cost, is fully testable and
never hallucinates. The AI layer can enrich the wording later, but the decision
itself stays explainable and reproducible.
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


def _safety_flags(m: TrainingMetrics) -> list[str]:
    flags: list[str] = []
    if m.injury_level == "high":
        flags.append("Rischio infortuni alto")
    if m.acwr is not None and m.acwr >= _ACWR_DANGER:
        flags.append(f"Carico acuto elevato (ACWR {m.acwr:.2f})")
    if m.readiness_state == "red":
        flags.append("Recupero insufficiente oggi")
    if m.tsb is not None and m.tsb <= _TSB_DEEP_FATIGUE:
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


def _confidence(missing: list[str], flags: list[str]) -> str:
    """More missing data → lower confidence; a clear safety signal is decisive."""
    if len(missing) >= 3:
        return "low"
    if len(missing) <= 1:
        return "high"
    return "medium"


def daily_note(decision: str, m: TrainingMetrics) -> str:
    """A short, human, motivational one-liner for today (Roadmap #3).

    Deterministic and contextual: keyed on the decision plus the dominant live
    signal. Not a report — one sentence that adds tone, not data.
    """
    tsb = m.tsb
    if decision == "rest":
        return "Il riposo di oggi è un investimento: recupera davvero, senza sensi di colpa."
    if decision == "modify":
        return "Ascolta il corpo oggi: alleggerire ora protegge tutta la settimana."
    if decision == "long":
        return "Il lungo si corre con la testa: parti piano, finisci forte."
    if decision == "quality":
        return "Sei fresco: rendi ogni ripetuta pulita, non solo veloce."
    # easy / run
    if tsb is not None and tsb <= -15:
        return "Hai ancora fatica nelle gambe: oggi vinci se corri piano."
    if tsb is not None and tsb >= 15:
        return "Ti senti bene, ma non sprecare energia nei primi km: resta in controllo."
    return "Costruisci continuità, non solo chilometri: una corsa facile fatta bene conta."


def decide_today(
    metrics: TrainingMetrics,
    profile: AthleteProfile | None,
    today_session: PlanSessionOut | None,
    checkin: DailyCheckin | None,
    ref: date | None = None,
) -> CoachDecision:
    """Produce today's structured coaching decision with its daily note."""
    decision = _decide_core(metrics, profile, today_session, checkin, ref)
    decision.daily_note = daily_note(decision.decision, metrics)
    return decision


def _decide_core(
    metrics: TrainingMetrics,
    profile: AthleteProfile | None,
    today_session: PlanSessionOut | None,
    checkin: DailyCheckin | None,
    ref: date | None = None,
) -> CoachDecision:
    """The rule cascade producing the decision (note attached by the wrapper)."""
    ref = ref or date.today()
    signals = _collect_signals(metrics)
    flags = _safety_flags(metrics)
    missing = _missing_data(metrics, checkin, today_session is not None, ref)
    confidence = _confidence(missing, flags)
    # A hard safety signal caps confidence at medium (we act, but flag the risk).
    if flags and confidence == "high":
        confidence = "medium"

    should_ease = bool(flags)  # any safety flag → pull intensity back

    # ── Case A: a plan session is scheduled today ────────────────────────────
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
                    "Il recupero è parte dell'allenamento: è quando il corpo "
                    "assorbe il carico e diventa più forte."
                ),
                confidence=confidence,
                signals=signals,
                missing_data=missing,
                alternatives=["Mobilità o stretching leggero", "Camminata rigenerante"],
                safety_flags=flags,
                plan_session_id=today_session.id,
                session_type="rest",
            )

        if _is_hard(st) and should_ease:
            # Downgrade the quality session to protect the athlete.
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
                    f"{reason}: forzare la qualità oggi aumenta il rischio senza "
                    "beneficio. Sposta lo stimolo intenso a quando sarai recuperato."
                ),
                confidence=confidence,
                signals=signals,
                missing_data=missing,
                alternatives=[
                    "Corsa facile 30–40 min in Z2",
                    "Riposo completo",
                    "Riprogramma il lavoro intenso tra 1–2 giorni",
                ],
                safety_flags=flags,
                plan_session_id=today_session.id,
                session_type="easy",
                target_pace=None,
            )

        # Follow the plan (optionally with a caution note).
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
            alternatives=_alternatives_for(decision),
            safety_flags=flags,
            plan_session_id=today_session.id,
            session_type=st,
            target_distance_km=base_km,
            target_pace=base_pace,
            target_duration_min=base_dur,
        )

    # ── Case B: no plan session today — recommend from live signals ──────────
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
                alternatives=["Camminata leggera", "Mobilità e stretching"],
                safety_flags=flags,
            )
        return CoachDecision(
            date=ref.isoformat(),
            decision="easy",
            headline="Corsa facile e breve",
            prescription="Corsa rilassata 30–40 min in Z2, senza forzare il passo.",
            rationale=(
                "I segnali suggeriscono prudenza: mantieni il movimento ma tieni "
                "l'intensità bassa per favorire il recupero."
            ),
            confidence=confidence,
            signals=signals,
            missing_data=missing,
            alternatives=["Riposo completo", "Cross-training leggero"],
            safety_flags=flags,
            session_type="easy",
        )

    if metrics.tsb is not None and metrics.tsb >= _TSB_VERY_FRESH:
        return CoachDecision(
            date=ref.isoformat(),
            decision="quality",
            headline="Sei fresco: giornata di qualità",
            prescription=(
                "Approfitta della freschezza: intervalli o un medio-veloce, "
                "es. 5×1000 in Z4 o 20–30 min a ritmo controllato."
            ),
            rationale=(
                "La tua forma è alta (TSB positivo) e il carico è sotto controllo: "
                "è il momento giusto per uno stimolo di qualità che faccia progredire."
            ),
            confidence=confidence,
            signals=signals,
            missing_data=missing,
            alternatives=["Corsa facile lunga", "Fartlek libero"],
            safety_flags=flags,
            session_type="tempo",
        )

    return CoachDecision(
        date=ref.isoformat(),
        decision="easy",
        headline="Corsa facile",
        prescription="Corsa aerobica in Z2, 40–50 min a ritmo conversazionale.",
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
