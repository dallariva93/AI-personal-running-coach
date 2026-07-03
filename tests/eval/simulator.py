"""Day-by-day coaching pipeline simulator + safety checkers (Roadmap A9).

Given a :class:`~tests.eval.athletes.SyntheticAthlete` and a scenario, this
seeds a load history, a safe base plan and per-day check-ins, then runs the
*real* pipeline for each simulated day — :func:`build_today_decision`,
:func:`adapt_plan_after_sync`, :func:`evaluate_plan_executions` — exactly as the
post-sync path does in production. The collected decisions and the final plan
state are then asserted against deterministic safety invariants.

The base plan is built here (not via the LLM/offline generator) so it is
anchored at the simulation start and is a known-safe precondition: 5 training
days, two quality days never adjacent, the long run after a rest day. The
harness then verifies the *engine* never violates safety on top of that base.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.db.models import Activity, TrainingPlan, TrainingPlanSession, TrainingPlanWeek
from app.processing.decision import _HARD_TYPES
from app.processing.recovery import readiness
from app.schemas import CoachDecision, DailyCheckin, Goal
from app.services.adaptive_plan import _is_severe, _is_taper, adapt_plan_after_sync
from app.services.checkin import hrv_history, latest_checkin, save_checkin
from app.services.decision_service import build_today_decision
from app.services.execution_service import evaluate_plan_executions
from app.services.ingest import _all_summaries
from app.services.profile import get_profile, save_profile
from tests.eval.athletes import SyntheticAthlete

# The weekly skeleton: (day_of_week, session_type). Two quality days (Tue, Thu)
# are separated by an easy Wednesday; the long run (Sat) follows a rest Friday.
# No two hard sessions are ever adjacent — a deliberately safe precondition.
_WEEK_PATTERN: list[tuple[int, str]] = [
    (0, "easy"),
    (1, "tempo"),
    (2, "easy"),
    (3, "intervals"),
    (4, "rest"),
    (5, "long"),
    (6, "easy"),
]

_BASE_KM = {"easy": 8.0, "tempo": 10.0, "intervals": 9.0, "long": 18.0}

# Weekly volume split by weekday (0=Mon..6=Sun): varied, with a rest day, so the
# seeded history has realistic day-to-day variation. A flat distribution would
# spike training monotony and drive injury risk artificially "high".
_WEEKLY_KM_SPLIT = [0.15, 0.20, 0.0, 0.18, 0.12, 0.25, 0.10]

# Weekly volume scale factors (index = week number - 1). A modest progression
# with a cutback; not the subject of the ramp test (that uses the real offline
# generator) — this only gives the adaptive engine something to reshape.
_WEEK_SCALE = [1.0, 1.08, 1.16, 0.93]

# Check-in presets per readiness state, tuned against
# ``app.processing.recovery.readiness`` so the resulting state is unambiguous.
_CHECKIN_PRESETS = {
    "green": dict(sleep_h=8.0, fatigue=2, soreness=1, motivation=8, hrv_rmssd=65.0),
    "amber": dict(sleep_h=5.0, fatigue=7, soreness=5, motivation=4, hrv_rmssd=55.0),
    "red": dict(sleep_h=3.0, fatigue=10, soreness=9, motivation=2, hrv_rmssd=30.0),
}


def _hard(session_type: str | None) -> bool:
    return (session_type or "").lower() in _HARD_TYPES


def _day_km(weekly_km: float, day: date) -> float:
    """Distance for a given calendar day from the varied weekly split (0 = rest)."""
    return round(weekly_km * _WEEKLY_KM_SPLIT[day.weekday()], 1)


def readiness_for_day(pattern: str, day_index: int, total: int) -> str:
    """Map a readiness pattern + day index to a target readiness state."""
    if pattern in ("green", "amber", "red"):
        return pattern
    if pattern == "volatile":
        return "red" if day_index % 2 else "green"
    if pattern == "declining":
        if day_index == 0:
            return "green"
        return "amber" if day_index < total // 2 else "red"
    raise ValueError(f"unknown readiness pattern: {pattern}")


@dataclass
class DayRecord:
    """What the pipeline decided on one simulated day, with its live context."""

    day: date
    readiness_state: str
    is_taper: bool
    is_severe: bool
    decision: CoachDecision

    @property
    def decision_type(self) -> str:
        return self.decision.decision


@dataclass
class SimulationResult:
    """Outcome of one scenario: the per-day decisions and the final plan."""

    athlete_key: str
    scenario_key: str
    start: date
    plan_id: int
    taper: bool
    days: list[DayRecord] = field(default_factory=list)
    base_hard_days: set[date] = field(default_factory=set)

    @property
    def any_severe(self) -> bool:
        return any(d.is_severe for d in self.days)


def _goal_for(taper: bool, start: date) -> Goal:
    """A goal race far away (build phase) or imminent (taper phase)."""
    days_out = 7 if taper else 120
    return Goal(
        goal_type="marathon",
        target_date=(start + timedelta(days=days_out)).isoformat(),
        target_time="3:30:00",
    )


def _seed_history(db: Session, athlete: SyntheticAthlete, start: date, days: int) -> None:
    """Insert varied easy runs before the sim so chronic load is established."""
    for offset in range(days, 0, -1):
        d = start - timedelta(days=offset)
        km = _day_km(athlete.weekly_km, d)
        if km <= 0:
            continue
        db.add(
            Activity(
                date=d.isoformat(),
                sport="run",
                activity_type="easy",
                distance_km=km,
                duration_min=round(km * 6.0, 1),
                avg_hr=135,
                rpe=3,
            )
        )
    db.flush()


def _build_plan(db: Session, start: date, weeks: int) -> TrainingPlan:
    """Persist a safe multi-week base plan anchored at ``start`` (a Monday)."""
    plan = TrainingPlan(
        goal_type="marathon",
        goal_date=(start + timedelta(days=weeks * 7)).isoformat(),
        level="intermediate",
        weeks_total=weeks,
        start_date=start.isoformat(),
        status="active",
    )
    db.add(plan)
    db.flush()
    for wk in range(1, weeks + 1):
        scale = _WEEK_SCALE[(wk - 1) % len(_WEEK_SCALE)]
        sessions = []
        for dow, stype in _WEEK_PATTERN:
            km = None if stype == "rest" else round(_BASE_KM[stype] * scale, 1)
            sessions.append((dow, stype, km))
        target_km = round(sum(km for _, _, km in sessions if km), 1)
        week = TrainingPlanWeek(
            plan_id=plan.id, week_number=wk, phase="Build", target_km=target_km
        )
        db.add(week)
        db.flush()
        for dow, stype, km in sessions:
            db.add(
                TrainingPlanSession(
                    week_id=week.id,
                    day_of_week=dow,
                    session_type=stype,
                    title=f"{stype} w{wk}",
                    target_distance_km=km,
                )
            )
    db.flush()
    return plan


def _base_hard_days(db: Session, plan: TrainingPlan, start: date) -> set[date]:
    """Calendar dates carrying a hard session in the untouched base plan."""
    out: set[date] = set()
    for wk in plan.weeks:
        for s in wk.sessions:
            if _hard(s.session_type):
                out.add(start + timedelta(days=(wk.week_number - 1) * 7 + s.day_of_week))
    return out


def _current_metrics(db: Session, ref: date):
    """Recompute metrics exactly as the pipeline does, for context recording."""
    from app.processing import compute_metrics

    return compute_metrics(
        _all_summaries(db),
        ref=ref,
        profile=get_profile(db),
        checkin=latest_checkin(db),
        hrv_history=hrv_history(db, ref=ref),
    )


def run_simulation(
    db: Session,
    athlete: SyntheticAthlete,
    *,
    readiness_pattern: str,
    taper: bool,
    start: date,
    days: int = 7,
    history_days: int = 28,
) -> SimulationResult:
    """Run one full scenario and return the collected decisions + final plan."""
    goal = _goal_for(taper, start)
    save_profile(db, athlete.profile(goal))
    _seed_history(db, athlete, start, history_days)
    plan = _build_plan(db, start, weeks=2 if taper else 4)
    base_hard = _base_hard_days(db, plan, start)

    result = SimulationResult(
        athlete_key=athlete.key,
        scenario_key=f"{athlete.key}|{readiness_pattern}|{'taper' if taper else 'build'}",
        start=start,
        plan_id=plan.id,
        taper=taper,
        base_hard_days=base_hard,
    )

    for i in range(days):
        ref = start + timedelta(days=i)
        state = readiness_for_day(readiness_pattern, i, days)
        checkin = DailyCheckin(date=ref.isoformat(), **_CHECKIN_PRESETS[state])
        save_checkin(db, checkin)
        # A varied easy run (rest days skipped) keeps load realistic and feeds
        # execution scoring without inflating monotony.
        km = _day_km(athlete.weekly_km, ref)
        if km > 0:
            db.add(
                Activity(
                    date=ref.isoformat(),
                    sport="run",
                    activity_type="easy",
                    distance_km=km,
                    duration_min=round(km * 6.0, 1),
                    avg_hr=135,
                    rpe=3,
                )
            )
        db.flush()

        decision = build_today_decision(db, ref=ref, persist=True)
        adapt_plan_after_sync(db, ref=ref)
        evaluate_plan_executions(db, ref=ref)

        # readiness_state is derived directly from the check-in (deterministic,
        # no extra metrics pass). is_taper/is_severe need the periodization
        # metrics, but only the taper checker consumes them — so we only pay for
        # that recompute in taper scenarios.
        readiness_state = readiness(checkin)[1]
        is_taper = is_severe = False
        if taper:
            metrics = _current_metrics(db, ref)
            is_taper = _is_taper(metrics)
            is_severe = _is_severe(metrics)

        result.days.append(
            DayRecord(
                day=ref,
                readiness_state=readiness_state,
                is_taper=is_taper,
                is_severe=is_severe,
                decision=decision,
            )
        )
    db.flush()
    return result


# ── Safety invariant checkers ────────────────────────────────────────────────
# Each returns a list of human-readable violations (empty == safe). Kept as
# plain functions so the "deliberately broken engine" meta-test can call them
# directly and prove the harness has teeth.


def check_no_quality_when_red(result: SimulationResult) -> list[str]:
    """Outside taper, a red-readiness day must never be prescribed quality.

    Scoped to non-taper days: during taper the engine intentionally preserves a
    reduced quality stimulus (P0-2), so a red taper day may still be "quality".
    """
    bad: list[str] = []
    for rec in result.days:
        if rec.readiness_state == "red" and not rec.is_taper and rec.decision_type == "quality":
            bad.append(
                f"{result.scenario_key} {rec.day}: quality prescribed on a red day "
                f"(headline={rec.decision.headline!r})"
            )
    return bad


def check_adaptive_volume_cap(db: Session, result: SimulationResult) -> list[str]:
    """No adapted session may exceed 110% of its captured base volume (ramp cap)."""
    bad: list[str] = []
    plan = db.get(TrainingPlan, result.plan_id)
    for wk in plan.weeks:
        for s in wk.sessions:
            base = s.base_target_distance_km
            if base is not None and s.target_distance_km is not None:
                if s.target_distance_km > base * 1.1 + 1e-6:
                    bad.append(
                        f"{result.scenario_key} session {s.id}: "
                        f"{s.target_distance_km} km > 110% of base {base} km"
                    )
    return bad


def check_no_new_hard_back_to_back(db: Session, result: SimulationResult) -> list[str]:
    """The pipeline must never add a hard day, nor create hard back-to-back."""
    bad: list[str] = []
    plan = db.get(TrainingPlan, result.plan_id)
    hard_days: set[date] = set()
    for wk in plan.weeks:
        for s in wk.sessions:
            if _hard(s.session_type):
                d = result.start + timedelta(
                    days=(wk.week_number - 1) * 7 + s.day_of_week
                )
                hard_days.add(d)
    for d in sorted(hard_days):
        if d not in result.base_hard_days:
            bad.append(f"{result.scenario_key} {d}: hard day created by the pipeline")
        if (d + timedelta(days=1)) in hard_days:
            bad.append(f"{result.scenario_key} {d}: hard back-to-back created")
    return bad


def check_taper_quality_preserved(db: Session, result: SimulationResult) -> list[str]:
    """During taper (no severe day), quality sessions must not be downgraded."""
    if not result.taper or result.any_severe:
        return []
    bad: list[str] = []
    plan = db.get(TrainingPlan, result.plan_id)
    for wk in plan.weeks:
        for s in wk.sessions:
            if _hard(s.base_session_type) and not _hard(s.session_type):
                bad.append(
                    f"{result.scenario_key} session {s.id}: taper quality "
                    f"downgraded {s.base_session_type!r} -> {s.session_type!r}"
                )
    return bad


def all_violations(db: Session, result: SimulationResult) -> list[str]:
    """Run every applicable safety checker and collect all violations."""
    return (
        check_no_quality_when_red(result)
        + check_adaptive_volume_cap(db, result)
        + check_no_new_hard_back_to_back(db, result)
        + check_taper_quality_preserved(db, result)
    )
