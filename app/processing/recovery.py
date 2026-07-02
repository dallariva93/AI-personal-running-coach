"""Daily readiness from subjective check-ins (GAP 9).

Training load is only half the story: sleep, fatigue, soreness and motivation
shape what the athlete can absorb today. This module turns a daily check-in into
a 0-100 **readiness** score and a traffic-light state the coach can act on.

Pure function: no I/O.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import date, timedelta

from app.schemas import DailyCheckin

# Below this many valid days of history the 7d/28d windows are too thin to
# trust: fall back to the absolute-threshold classification.
_LEARNING_MIN_DAYS = 21
_BAND_SD_MULT = 0.75


def hrv_status(hrv_rmssd: float | None) -> str:
    """Return HRV status: 'low' | 'normal' | 'high' | 'unknown'.

    Absolute-threshold fallback, used while the personal baseline is still
    learning (see :func:`hrv_baseline`).
    """
    if hrv_rmssd is None:
        return "unknown"
    if hrv_rmssd < 25:
        return "low"
    if hrv_rmssd <= 55:
        return "normal"
    return "high"


@dataclass
class HrvBaseline:
    """Personal HRV baseline: 7-day trend vs the athlete's own 28-day norm."""

    ln_mean_7d: float | None
    ln_mean_28d: float | None
    ln_sd_28d: float | None
    status: str  # "low" | "normal" | "high" | "unknown"
    learning: bool  # True when <21 days of history: falls back to absolute thresholds
    days_tracked: int  # valid HRV days seen so far, for the "day X/21" UI copy


def hrv_baseline(history: list[tuple[date, float]]) -> HrvBaseline:
    """Classify today's HRV against the athlete's own recent history.

    ``history`` is ``(date, rmssd)`` pairs, ideally the last 35 days including
    today. The most recent 7 days become the trend window; the 28 days before
    that are the personal baseline (mean ± 0.75·SD of ``ln(rMSSD)``, which is
    closer to normally distributed than the raw value). Outliers (<=0 or
    >200 ms) are dropped rather than interpolated.
    """
    pts = sorted(
        (d, v) for d, v in history if v is not None and 0 < v <= 200
    )
    if not pts:
        return HrvBaseline(None, None, None, "unknown", learning=True, days_tracked=0)

    ref = pts[-1][0]
    recent = [v for d, v in pts if ref - timedelta(days=6) <= d <= ref]
    prior = [
        v for d, v in pts if ref - timedelta(days=34) <= d <= ref - timedelta(days=7)
    ]
    learning = len(pts) < _LEARNING_MIN_DAYS

    ln_mean_7d = statistics.mean(math.log(v) for v in recent) if recent else None
    ln_mean_28d = statistics.mean(math.log(v) for v in prior) if prior else None
    ln_sd_28d = statistics.pstdev(math.log(v) for v in prior) if len(prior) >= 2 else None

    if learning or ln_mean_7d is None or ln_mean_28d is None:
        status = hrv_status(pts[-1][1])
    else:
        sd = ln_sd_28d or 0.0
        if ln_mean_7d < ln_mean_28d - _BAND_SD_MULT * sd:
            status = "low"
        elif ln_mean_7d > ln_mean_28d + _BAND_SD_MULT * sd:
            status = "high"
        else:
            status = "normal"

    return HrvBaseline(ln_mean_7d, ln_mean_28d, ln_sd_28d, status, learning, days_tracked=len(pts))


def readiness(
    checkin: DailyCheckin | None, hrv_band_status: str | None = None
) -> tuple[float | None, str]:
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

    # Factor in HRV: relative to the athlete's own baseline band when known
    # (Q1), falling back to absolute RMSSD thresholds otherwise.
    hrv = checkin.hrv_rmssd
    if hrv_band_status is not None:
        if hrv_band_status == "low":
            score -= 15
        elif hrv_band_status == "high":
            score += 10
    elif hrv is not None:
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
