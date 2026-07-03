"""Digital Twin orchestrator (Roadmap A5): gather history → estimate → persist.

The pure estimators live in :mod:`app.processing.digital_twin`; this service is
the only place that touches the DB. It derives the plain-data inputs the pure
functions need (weekly loads + bad-outcome flags, recovery episodes, heat
points), stores the three learned constants in ``athlete_model`` and reads them
back, throttled to one recompute per day in the post-sync pipeline.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Activity, AthleteModelRow, DailyCheckinRow, TrainingPlan
from app.logging_config import get_logger
from app.processing import weekly_buckets
from app.processing.digital_twin import (
    HEAT_MIN_HOT_SAMPLES,
    RAMP_MIN_SAMPLES,
    RECOVERY_MIN_SAMPLES,
    WeekObservation,
    build_athlete_model,
)
from app.processing.recovery import readiness
from app.schemas import AthleteModel, AthleteModelEstimate, DailyCheckin
from app.services.checkin import _row_to_schema
from app.services.ingest import _all_summaries

logger = get_logger("app.services.athlete_model")

_EASY_TYPES = {"easy", "recupero", "recovery", "medio"}
_EXEC_COLLAPSE_SCORE = 50.0  # execution below this = a "collapse" (bad outcome)
_EXEC_RECOVERED_SCORE = 80.0  # execution at/above this = recovered
_RECOVERY_SCAN_DAYS = 10  # how far to look forward for a recovery signal

# Per-key sample thresholds mirror the pure module's, for the learning flag.
_MIN_SAMPLES = {
    "ramp_tolerance_pct": RAMP_MIN_SAMPLES,
    "recovery_halflife_days": RECOVERY_MIN_SAMPLES,
    "heat_sensitivity_s_per_c": HEAT_MIN_HOT_SAMPLES,
}


# ── Small parsing / readiness helpers ────────────────────────────────────────


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


def _readiness_state_by_date(db: Session, ref: date, days: int = 180) -> dict[str, str]:
    """Reconstruct the daily readiness traffic-light from stored check-ins.

    Uses absolute HRV thresholds (no per-day baseline) — good enough for the
    twin's historical reconstruction and fully deterministic.
    """
    since = (ref - timedelta(days=days)).isoformat()
    rows = db.scalars(
        select(DailyCheckinRow).where(
            DailyCheckinRow.date >= since, DailyCheckinRow.date <= ref.isoformat()
        )
    ).all()
    out: dict[str, str] = {}
    for row in rows:
        checkin: DailyCheckin = _row_to_schema(row)
        _, state = readiness(checkin)
        out[row.date] = state
    return out


# ── Derive the pure-function inputs ───────────────────────────────────────────


def _executed_sessions(db: Session) -> list[tuple[date, str | None, float | None]]:
    """(date, execution_status, execution_score) for every scored plan session."""
    out: list[tuple[date, str | None, float | None]] = []
    plans = db.scalars(select(TrainingPlan)).all()
    for plan in plans:
        try:
            start = date.fromisoformat(plan.start_date)
        except (ValueError, TypeError):
            continue
        for week in plan.weeks:
            for sess in week.sessions:
                if sess.execution_status is None and sess.execution_score is None:
                    continue
                d = start + timedelta(days=(week.week_number - 1) * 7 + sess.day_of_week)
                out.append((d, sess.execution_status, sess.execution_score))
    return out


def _week_observations(
    db: Session, summaries, ref: date, readiness_by_date: dict[str, str], weeks: int = 16
) -> list[WeekObservation]:
    """Weekly load series with a ``bad_after`` flag (readiness red or execution
    collapse in the 7 days after the week)."""
    buckets = weekly_buckets(summaries, weeks=weeks)
    executed = _executed_sessions(db)
    obs: list[WeekObservation] = []
    for b in buckets:
        try:
            wk_start = date.fromisoformat(b.week_start)
        except (ValueError, TypeError):
            continue
        window_start = wk_start + timedelta(days=7)
        window_end = wk_start + timedelta(days=13)
        bad = any(
            window_start <= date.fromisoformat(d) <= window_end and state == "red"
            for d, state in readiness_by_date.items()
        )
        if not bad:
            bad = any(
                window_start <= d <= window_end
                and (status == "too_hard" or (score is not None and score < _EXEC_COLLAPSE_SCORE))
                for d, status, score in executed
            )
        obs.append(WeekObservation(load=b.distance_km, bad_after=bad))
    return obs


def _recovery_episodes(
    db: Session, readiness_by_date: dict[str, str]
) -> list[float]:
    """Days from a hard/too-hard effort (or race) to the first recovery signal:
    a readiness-green day or a later execution score >= 80."""
    executed = _executed_sessions(db)
    # A hard effort = a session executed too hard, or a race activity.
    efforts: list[date] = [d for d, status, _score in executed if status == "too_hard"]
    races = db.scalars(
        select(Activity.date).where(Activity.activity_type.in_(["gara", "race"]))
    ).all()
    for r in races:
        try:
            efforts.append(date.fromisoformat(r))
        except (ValueError, TypeError):
            continue
    efforts = sorted(set(efforts))

    recovered_by_score = {d for d, _s, score in executed
                          if score is not None and score >= _EXEC_RECOVERED_SCORE}
    episodes: list[float] = []
    for eff in efforts:
        for gap in range(1, _RECOVERY_SCAN_DAYS + 1):
            day = eff + timedelta(days=gap)
            if readiness_by_date.get(day.isoformat()) == "green" or day in recovered_by_score:
                episodes.append(float(gap))
                break
    return episodes


def _heat_points(summaries) -> list[tuple[float, float]]:
    """(temperature_c, grade-adjusted pace sec/km) for easy runs with both."""
    points: list[tuple[float, float]] = []
    for r in summaries:
        if (r.activity_type or "").lower() not in _EASY_TYPES:
            continue
        if r.temperature_c is None:
            continue
        gap = _pace_sec(r.avg_grade_adjusted_pace) or _pace_sec(r.avg_pace)
        if gap is None:
            continue
        points.append((float(r.temperature_c), gap))
    return points


# ── Orchestrate, persist, load ────────────────────────────────────────────────


def estimate_athlete_model(db: Session, ref: date | None = None) -> AthleteModel:
    """Gather history and compute the Digital Twin (does not persist)."""
    ref = ref or date.today()
    summaries = _all_summaries(db)
    readiness_by_date = _readiness_state_by_date(db, ref)
    weeks = _week_observations(db, summaries, ref, readiness_by_date)
    recovery = _recovery_episodes(db, readiness_by_date)
    heat = _heat_points(summaries)
    return build_athlete_model(weeks, recovery, heat, computed_at=ref.isoformat())


def save_athlete_model(db: Session, model: AthleteModel) -> None:
    """Upsert the three learned constants into ``athlete_model``."""
    now = datetime.utcnow()
    pairs = {
        "ramp_tolerance_pct": model.ramp_tolerance_pct,
        "recovery_halflife_days": model.recovery_halflife_days,
        "heat_sensitivity_s_per_c": model.heat_sensitivity_s_per_c,
    }
    for key, est in pairs.items():
        row = db.get(AthleteModelRow, key)
        if row is None:
            row = AthleteModelRow(key=key)
            db.add(row)
        row.value = est.value
        row.confidence = est.confidence
        row.computed_at = now
    db.flush()


def _estimate_from_row(
    row: AthleteModelRow | None, key: str, default: float
) -> AthleteModelEstimate:
    if row is None:
        return AthleteModelEstimate(value=default, confidence=0, learning=True)
    learning = row.confidence < _MIN_SAMPLES[key]
    return AthleteModelEstimate(value=row.value, confidence=row.confidence, learning=learning)


def load_athlete_model(db: Session) -> AthleteModel:
    """Read the persisted twin; defaults (learning) for keys not yet computed."""
    from app.processing.digital_twin import (
        HEAT_DEFAULT_S_PER_C,
        RAMP_DEFAULT_PCT,
        RECOVERY_DEFAULT_DAYS,
    )

    ramp = db.get(AthleteModelRow, "ramp_tolerance_pct")
    rec = db.get(AthleteModelRow, "recovery_halflife_days")
    heat = db.get(AthleteModelRow, "heat_sensitivity_s_per_c")
    computed = next((r.computed_at for r in (ramp, rec, heat) if r is not None), None)
    return AthleteModel(
        ramp_tolerance_pct=_estimate_from_row(ramp, "ramp_tolerance_pct", RAMP_DEFAULT_PCT),
        recovery_halflife_days=_estimate_from_row(
            rec, "recovery_halflife_days", RECOVERY_DEFAULT_DAYS
        ),
        heat_sensitivity_s_per_c=_estimate_from_row(
            heat, "heat_sensitivity_s_per_c", HEAT_DEFAULT_S_PER_C
        ),
        computed_at=computed.date().isoformat() if computed else None,
    )


def maybe_refresh_athlete_model(db: Session, ref: date | None = None) -> bool:
    """Recompute+persist at most once per day (post-sync pipeline). Best-effort.

    Returns True when a recompute happened. Never raises: a twin failure must
    not break the sync pipeline.
    """
    ref = ref or date.today()
    try:
        latest = db.scalar(
            select(AthleteModelRow.computed_at)
            .order_by(AthleteModelRow.computed_at.desc())
        )
        if latest is not None and latest.date() >= ref:
            return False
        model = estimate_athlete_model(db, ref=ref)
        save_athlete_model(db, model)
        return True
    except Exception as exc:  # noqa: BLE001 - twin never breaks the pipeline
        logger.warning("Athlete-model refresh failed: %s", exc)
        return False


# ── Consumption helpers (used by decision & adaptive engines) ─────────────────


def personal_ramp_factor(db: Session) -> float | None:
    """Personal weekly ramp cap as a multiplier (e.g. 1.12), or None while
    learning — callers then keep the population default."""
    row = db.get(AthleteModelRow, "ramp_tolerance_pct")
    if row is None or row.confidence < RAMP_MIN_SAMPLES:
        return None
    return round(1 + row.value / 100.0, 3)


def personal_recovery_halflife(db: Session) -> int | None:
    """Personal recovery half-life in days, or None while learning."""
    row = db.get(AthleteModelRow, "recovery_halflife_days")
    if row is None or row.confidence < RECOVERY_MIN_SAMPLES:
        return None
    return int(round(row.value))
