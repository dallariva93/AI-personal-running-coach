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
    """Score how faithfully ``run`` executed the prescribed ``session``.

    v2: multi-dimensional sub-scores (volume, intensity, pace, structure,
    distribution) and HR time-in-zone validation (P0-5, P0-6).
    """
    # No activity found on the prescribed day -> skipped.
    if run is None:
        return ExecutionResult(
            plan_session_id=session.id,
            activity_id=None,
            date=date_str,
            execution_score=0.0,
            execution_status="skipped",
            execution_notes="Seduta non svolta.",
            evidence=["Nessuna attivita trovata nella data prevista"],
        )

    evidence: list[str] = []
    score = 100.0
    expected = _rank(session.session_type)
    actual = _rank(run.activity_type)

    # -- Distance (volume sub-score) -----------------------------------------
    dist_ratio: float | None = None
    volume_score = 100.0
    if session.target_distance_km:
        dist_ratio = run.distance_km / session.target_distance_km
        evidence.append(
            f"Distanza {run.distance_km:.1f}/{session.target_distance_km:.0f} km"
        )
        if dist_ratio < 1.0:
            penalty = min(45.0, (1.0 - dist_ratio) * 90.0)
            score -= penalty
            volume_score -= penalty
        elif dist_ratio > 1.2:
            penalty = min(20.0, (dist_ratio - 1.2) * 50.0)
            score -= penalty
            volume_score -= penalty

    # -- Duration (weighted less when a distance target exists) --------------
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

    # -- Intensity / type match (intensity sub-score) ------------------------
    evidence.append(f"Tipo: previsto {session.session_type}, svolto {run.activity_type}")
    intensity_score = 100.0
    intensity_status: str | None = None
    if expected >= 3 and actual <= 1:
        score -= 35.0
        intensity_score -= 35.0
        intensity_status = "turned_easy"
    elif expected >= 3 and actual < expected:
        score -= 20.0
        intensity_score -= 20.0
        intensity_status = "quality_missed"
    elif expected <= 1 and actual >= 3:
        score -= 30.0
        intensity_score -= 30.0
        intensity_status = "too_hard"

    # RPE nuance: a hard-felt easy day is a red flag even if the type looked easy.
    if expected <= 1 and run.rpe is not None and run.rpe >= 7:
        score -= 12.0
        intensity_score -= 12.0
        evidence.append(f"RPE {run.rpe} alto per una giornata facile")
        intensity_status = intensity_status or "too_hard"

    # -- Pace sub-score ------------------------------------------------------
    pace_score = 100.0
    tgt = _pace_sec(session.target_pace)
    act = _pace_sec(run.avg_pace)
    if tgt and act and expected <= 2 and act < tgt * 0.93:
        score -= 8.0
        pace_score -= 8.0
        evidence.append("Passo piu veloce del previsto in giornata facile")
        intensity_status = intensity_status or "too_hard"

    # -- HR time-in-zone check (P0-5) ----------------------------------------
    time_in_zone_pct: float | None = None
    if run.hr_zones and expected >= 3:
        # Quality sessions should spend significant time in Z3+.
        # hr_zones is a dict like {"z1": 120, "z2": 300, "z3": 600, ...}
        total_time = sum(run.hr_zones.values())
        if total_time > 0:
            hard_time = sum(
                v for k, v in run.hr_zones.items()
                if k.lower() in ("z3", "z4", "z5", "zone3", "zone4", "zone5")
            )
            time_in_zone_pct = round(hard_time / total_time * 100, 1)
            evidence.append(f"Tempo in zona target (Z3+): {time_in_zone_pct}%")
            if time_in_zone_pct < 20:
                score -= 15.0
                intensity_score -= 15.0
                intensity_status = intensity_status or "quality_missed"
                evidence.append("Tempo in zona insufficiente per una seduta di qualita")
    elif run.hr_zones and expected <= 1:
        # Easy sessions should be mostly Z1-Z2.
        total_time = sum(run.hr_zones.values())
        if total_time > 0:
            easy_time = sum(
                v for k, v in run.hr_zones.items()
                if k.lower() in ("z1", "z2", "zone1", "zone2")
            )
            time_in_zone_pct = round(easy_time / total_time * 100, 1)
            evidence.append(f"Tempo in zona facile (Z1-Z2): {time_in_zone_pct}%")
            if time_in_zone_pct < 60:
                score -= 10.0
                intensity_score -= 10.0
                intensity_status = intensity_status or "too_hard"
                evidence.append("Troppo tempo fuori dalla zona facile")

    score = max(0.0, min(100.0, round(score, 0)))

    # -- Structure sub-score: did the activity type match? -------------------
    structure_score = 100.0 if expected == actual else 70.0
    if intensity_status in ("turned_easy", "quality_missed", "too_hard"):
        structure_score = 50.0

    # -- Distribution sub-score: pace consistency (from splits) --------------
    distribution_score: float | None = None
    if run.splits_km and len(run.splits_km) >= 3:
        split_secs = [_pace_sec(s) for s in run.splits_km]
        valid = [s for s in split_secs if s is not None]
        if len(valid) >= 3:
            import statistics
            mean_pace = statistics.mean(valid)
            stdev = statistics.stdev(valid)
            cv = stdev / mean_pace if mean_pace > 0 else 0
            # CV < 0.05 = very consistent (100), CV > 0.15 = erratic (40)
            distribution_score = max(40.0, min(100.0, 100.0 - (cv - 0.05) * 600))
            distribution_score = round(distribution_score, 0)

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
        volume_score=round(max(0.0, min(100.0, volume_score)), 0),
        intensity_score=round(max(0.0, min(100.0, intensity_score)), 0),
        pace_score=round(max(0.0, min(100.0, pace_score)), 0),
        structure_score=round(structure_score, 0),
        distribution_score=distribution_score,
        time_in_zone_pct=time_in_zone_pct,
    )


def _status(
    dist_ratio: float | None,
    dur_ratio: float | None,
    intensity_status: str | None,
    score: float,
) -> str:
    """Pick the single dominant outcome from the deviations (P0-6: rewritten).

    Priority order:
    1. volume_excess  - safety-relevant, always surfaces first.
    2. intensity      - turned_easy / quality_missed / too_hard.
    3. too_short      - volume significantly under target (< 0.7).
    4. completed_well - score >= 75 with no major deviation.
    5. quality_missed - fallback for minor deviations.
    """
    if (dist_ratio is not None and dist_ratio > 1.3) or (
        dur_ratio is not None and dur_ratio > 1.4
    ):
        return "volume_excess"
    if intensity_status is not None:
        return intensity_status
    if dist_ratio is not None and dist_ratio < 0.7:
        return "too_short"
    if dur_ratio is not None and dist_ratio is None and dur_ratio < 0.7:
        return "too_short"
    if score >= 75:
        return "completed_well"
    if dist_ratio is not None and dist_ratio < 0.9:
        return "too_short"
    return "quality_missed"


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
