"""Workout Execution Score (World-Class Roadmap #9).

Answers the question the plan can't answer on its own: *did the athlete execute
the prescribed session as prescribed?* Comparing the completed activity against
its plan session — distance, duration, session type, intensity, and RPE/HR when
present — yields a 0-100 score and a status, so the coach adapts from real
compliance, not just from load and readiness.

Pure and deterministic: given a :class:`PlanSessionOut` and a :class:`RunSummary`
it returns an :class:`ExecutionResult`. No I/O, no AI.
"""

from __future__ import annotations

from app.schemas import ExecutionResult, PlanSessionOut, RunSummary

# Intensity rank per session/activity type (0=rest … 4=hard). Accepts both plan
# session types and the Italian activity labels.
_RANK: dict[str, int] = {
    "rest": 0,
    "riposo": 0,
    "recovery": 1,
    "recupero": 1,
    "easy": 1,
    "strides": 1,
    "cross": 1,
    "long": 2,
    "lungo": 2,
    "medio": 2,
    "trail": 2,
    "tempo": 3,
    "threshold": 3,
    "soglia": 3,
    "intervals": 4,
    "intervalli": 4,
    "vo2max": 4,
    "race": 4,
    "gara": 4,
}


def _rank(t: str | None) -> int:
    return _RANK.get((t or "").lower(), 2)


def _pace_sec(pace: str | None) -> float | None:
    """Parse ``M:SS/km`` into seconds/km."""
    if not pace:
        return None
    core = pace.split("/")[0]
    parts = core.split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
    except (ValueError, TypeError):
        return None
    return None


def score_execution(
    session: PlanSessionOut, run: RunSummary | None, date_str: str
) -> ExecutionResult:
    """Score how faithfully ``run`` executed the prescribed ``session``."""
    # No activity found on the prescribed day → skipped.
    if run is None:
        return ExecutionResult(
            plan_session_id=session.id,
            activity_id=None,
            date=date_str,
            execution_score=0.0,
            execution_status="skipped",
            execution_notes="Seduta non svolta.",
            evidence=["Nessuna attività trovata nella data prevista"],
        )

    evidence: list[str] = []
    score = 100.0
    expected = _rank(session.session_type)
    actual = _rank(run.activity_type)

    # ── Distance ─────────────────────────────────────────────────────────────
    dist_ratio: float | None = None
    if session.target_distance_km:
        dist_ratio = run.distance_km / session.target_distance_km
        evidence.append(
            f"Distanza {run.distance_km:.1f}/{session.target_distance_km:.0f} km"
        )
        if dist_ratio < 1.0:
            score -= min(45.0, (1.0 - dist_ratio) * 90.0)
        elif dist_ratio > 1.2:
            score -= min(20.0, (dist_ratio - 1.2) * 50.0)

    # ── Duration (weighted less when a distance target exists) ───────────────
    dur_ratio: float | None = None
    if session.target_duration_min:
        dur_ratio = run.duration_min / session.target_duration_min
        evidence.append(
            f"Durata {run.duration_min:.0f}/{session.target_duration_min:.0f} min"
        )
        weight = 0.4 if session.target_distance_km else 1.0
        if dur_ratio < 1.0:
            score -= min(35.0, (1.0 - dur_ratio) * 70.0) * weight
        elif dur_ratio > 1.25:
            score -= min(15.0, (dur_ratio - 1.25) * 40.0) * weight

    # ── Intensity / type match ───────────────────────────────────────────────
    evidence.append(f"Tipo: previsto {session.session_type}, svolto {run.activity_type}")
    intensity_status: str | None = None
    if expected >= 3 and actual <= 1:
        score -= 35.0
        intensity_status = "turned_easy"
    elif expected >= 3 and actual < expected:
        score -= 20.0
        intensity_status = "quality_missed"
    elif expected <= 1 and actual >= 3:
        score -= 30.0
        intensity_status = "too_hard"

    # RPE nuance: a hard-felt easy day is a red flag even if the type looked easy.
    if expected <= 1 and run.rpe is not None and run.rpe >= 7:
        score -= 12.0
        evidence.append(f"RPE {run.rpe} alto per una giornata facile")
        intensity_status = intensity_status or "too_hard"

    # Pace nuance: markedly faster than the easy/target pace on an easy day.
    tgt = _pace_sec(session.target_pace)
    act = _pace_sec(run.avg_pace)
    if tgt and act and expected <= 2 and act < tgt * 0.93:
        score -= 8.0
        evidence.append("Passo più veloce del previsto in giornata facile")
        intensity_status = intensity_status or "too_hard"

    score = max(0.0, min(100.0, round(score, 0)))

    status = _status(dist_ratio, dur_ratio, intensity_status, score)
    notes = _notes(status)
    return ExecutionResult(
        plan_session_id=session.id,
        activity_id=None,  # filled by the service
        date=date_str,
        execution_score=score,
        execution_status=status,
        execution_notes=notes,
        evidence=evidence,
    )


def _status(
    dist_ratio: float | None,
    dur_ratio: float | None,
    intensity_status: str | None,
    score: float,
) -> str:
    """Pick the single dominant outcome from the deviations."""
    # Excess volume dominates (safety-relevant).
    if (dist_ratio is not None and dist_ratio > 1.3) or (
        dur_ratio is not None and dur_ratio > 1.4
    ):
        return "volume_excess"
    # Way too short → effectively not the session.
    if dist_ratio is not None and dist_ratio < 0.7:
        return "too_short"
    if dur_ratio is not None and dist_ratio is None and dur_ratio < 0.7:
        return "too_short"
    if intensity_status is not None:
        return intensity_status
    if score >= 75:
        return "completed_well"
    return "too_short" if (dist_ratio is not None and dist_ratio < 0.9) else "quality_missed"


_NOTES = {
    "completed_well": "Seduta eseguita come prescritta. Ottimo lavoro.",
    "too_hard": "Più intensa del previsto: attenzione a non anticipare la fatica.",
    "too_short": "Più corta del previsto: volume sotto il target.",
    "skipped": "Seduta non svolta.",
    "turned_easy": "Qualità trasformata in facile: lo stimolo previsto è mancato.",
    "quality_missed": "Obiettivo di qualità non pienamente centrato.",
    "volume_excess": "Volume oltre il previsto: occhio all'eccesso di carico.",
}


def _notes(status: str) -> str:
    return _NOTES.get(status, "")
