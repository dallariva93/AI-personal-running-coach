"""Daily readiness from subjective check-ins (GAP 9).

Training load is only half the story: sleep, fatigue, soreness and motivation
shape what the athlete can absorb today. This module turns a daily check-in into
a 0-100 **readiness** score and a traffic-light state the coach can act on.

Pure function: no I/O.
"""

from __future__ import annotations

from app.schemas import DailyCheckin


def hrv_status(hrv_rmssd: float | None) -> str:
    """Return HRV status: 'low' | 'normal' | 'high' | 'unknown'."""
    if hrv_rmssd is None:
        return "unknown"
    if hrv_rmssd < 25:
        return "low"
    if hrv_rmssd <= 55:
        return "normal"
    return "high"


def readiness(checkin: DailyCheckin | None) -> tuple[float | None, str]:
    """Return ``(score 0-100, state)`` where state is green | amber | red."""
    if checkin is None:
        return None, "unknown"

    score = 100.0
    if checkin.sleep_h is not None and checkin.sleep_h < 7:
        score -= (7 - checkin.sleep_h) * 8
    if checkin.fatigue is not None and checkin.fatigue > 5:
        score -= (checkin.fatigue - 5) * 6
    if checkin.soreness is not None and checkin.soreness > 3:
        score -= (checkin.soreness - 3) * 7
    if checkin.motivation is not None:
        score += (checkin.motivation - 5) * 3  # high motivation lifts, low drags

    # Factor in HRV RMSSD when available.
    hrv = checkin.hrv_rmssd
    if hrv is not None:
        if hrv < 25:
            score -= 15
        elif hrv < 40:
            score -= 5
        elif hrv > 80:
            score += 15
        elif hrv > 60:
            score += 10

    score = round(max(0.0, min(100.0, score)), 0)
    if score >= 70:
        state = "green"
    elif score >= 40:
        state = "amber"
    else:
        state = "red"
    return score, state
