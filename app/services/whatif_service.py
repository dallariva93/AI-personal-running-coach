"""What-if orchestrator (Roadmap A7): derive inputs, simulate, format. No writes.

The only module that touches the DB for the what-if. It derives the actual past
daily loads, the future planned-session loads and the baseline race prediction,
hands them to the pure :func:`app.processing.whatif.simulate_scenario`, and maps
the result onto the API schema. Strictly read-only — never persists.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import TrainingPlan
from app.processing.efficiency import aerobic_efficiency
from app.processing.load import calibrate_garmin_factor, internal_load
from app.processing.performance import predict_race_time, seconds_to_time
from app.processing.snapshot import build_snapshot
from app.processing.whatif import PlannedSession, simulate_scenario
from app.schemas import RunSummary, WhatIfResultOut
from app.services.ingest import _all_summaries
from app.services.profile import get_profile

# Reasonable session length (min) when a planned session carries neither a
# duration nor enough to derive one from distance × pace.
_DEFAULT_SESSION_MIN = 45.0
_EASY_PACE_MIN_PER_KM = 6.0


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value[:10])
    except (ValueError, TypeError):
        return None


def _pace_sec(pace: str | None) -> float | None:
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


def _planned_duration_min(dist: float, pace: str | None, duration: float | None) -> float:
    if duration and duration > 0:
        return duration
    pace_sec = _pace_sec(pace)
    if dist > 0 and pace_sec:
        return dist * pace_sec / 60.0
    if dist > 0:
        return dist * _EASY_PACE_MIN_PER_KM
    return _DEFAULT_SESSION_MIN


def _planned_sessions(
    plan: TrainingPlan, start: date, ref: date, race_date: date, profile, garmin_factor
) -> list[PlannedSession]:
    """Future (ref < date <= race) non-rest sessions, with projected sRPE load."""
    out: list[PlannedSession] = []
    for week in plan.weeks:
        for sess in week.sessions:
            d = start + timedelta(days=(week.week_number - 1) * 7 + sess.day_of_week)
            if d <= ref or d > race_date:
                continue
            stype = (sess.session_type or "easy").lower()
            if stype in ("rest", "riposo"):
                continue
            dist = sess.target_distance_km or 0.0
            dur = _planned_duration_min(dist, sess.target_pace, sess.target_duration_min)
            synthetic = RunSummary(
                date=d.isoformat(), activity_type=stype, sport="run",
                distance_km=dist, duration_min=dur, avg_pace=sess.target_pace,
            )
            out.append(PlannedSession(
                date=d, session_type=stype,
                load=internal_load(synthetic, profile, garmin_factor),
            ))
    return out


def _delta_label(delta_seconds: float | None) -> str | None:
    if delta_seconds is None or abs(delta_seconds) < 1.0:
        return None
    secs = int(round(abs(delta_seconds)))
    return f"{secs}s più lento del previsto" if delta_seconds > 0 else \
        f"{secs}s più veloce del previsto"


def run_whatif(db: Session, scenario: str, ref: date | None = None) -> WhatIfResultOut | None:
    """Run one what-if against the active plan. Returns None if there is none."""
    ref = ref or date.today()
    plan = db.scalar(select(TrainingPlan).where(TrainingPlan.status == "active"))
    if plan is None:
        return None
    start = _parse_date(plan.start_date)
    if start is None:
        return None

    race_date = _parse_date(plan.goal_date) or (ref + timedelta(days=1))
    if race_date <= ref:
        race_date = ref + timedelta(days=1)

    profile = get_profile(db)
    summaries = _all_summaries(db)
    garmin_factor = calibrate_garmin_factor(summaries, profile)

    # Actual past daily loads — same construction as metrics._daily_internal_loads,
    # so the forward projection matches the live CTL/ATL/TSB on known history.
    past_daily: dict[date, float] = {}
    for r in summaries:
        d = _parse_date(r.date)
        if d and d <= ref:
            past_daily[d] = past_daily.get(d, 0.0) + internal_load(r, profile, garmin_factor)

    planned = _planned_sessions(plan, start, ref, race_date, profile, garmin_factor)

    # Baseline race prediction (unchanged by the scenario — the current-fitness
    # estimate the what-if then nudges by the projected fitness delta).
    goal = profile.goal if profile else None
    _, eff_trend = aerobic_efficiency(summaries)
    prediction = predict_race_time(goal, build_snapshot(summaries), eff_trend)
    base_seconds = prediction.predicted_seconds if prediction else None

    result = simulate_scenario(
        scenario, past_daily, planned, ref, race_date, base_seconds
    )
    return WhatIfResultOut(
        scenario=result.scenario,
        baseline_race_time=seconds_to_time(result.baseline_race_seconds),
        scenario_race_time=seconds_to_time(result.scenario_race_seconds),
        race_time_delta_seconds=result.race_time_delta_seconds,
        race_time_delta_label=_delta_label(result.race_time_delta_seconds),
        baseline_tsb_at_race=result.baseline_tsb_at_race,
        scenario_tsb_at_race=result.scenario_tsb_at_race,
        risk_notes=result.risk_notes,
    )
