"""Proactive behavioural triggers (Roadmap A1).

Beyond reacting to each sync, the coach watches for behavioural patterns and
takes the initiative. :func:`evaluate_triggers` runs at the tail of the
post-sync pipeline and may emit at most one notifiable :class:`CoachEvent` per
pattern per week (weekly ``dedupe_key`` — so a pattern that persists nags once,
not every day). Each event carries its suggested follow-up actions in
``after["actions"]`` so the app can offer a one-tap response.

Three triggers:

1. **re-engage** — a session prescribed yesterday was skipped and there is still
   no activity today → "Ci sei? Riorganizzo la settimana?" (defer / reduce).
2. **recalibrate** — >=3 ``too_hard`` executions in 10 days → "I tuoi ritmi
   target sembrano stretti: li ricalibro?" (recalibrate = +5 s/km on future
   targets).
3. **hrv-watch** — HRV below the personal baseline (Q1) for >=5 consecutive days
   → a pre-red nudge to back off before readiness collapses.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Activity, CoachEvent, TrainingPlan
from app.logging_config import get_logger
from app.processing.recovery import hrv_baseline
from app.services.checkin import hrv_history
from app.services.event_service import log_event

logger = get_logger("app.services.triggers")

_TOO_HARD_WINDOW_DAYS = 10
_TOO_HARD_THRESHOLD = 3
_HRV_LOW_STREAK_DAYS = 5


def _week_key(ref: date) -> str:
    y, w, _ = ref.isocalendar()
    return f"{y}-W{w:02d}"


def _has_run_on(db: Session, day: date) -> bool:
    return db.scalar(
        select(Activity.id)
        .where(Activity.sport == "run", Activity.date == day.isoformat())
        .limit(1)
    ) is not None


def _active_plan(db: Session) -> tuple[TrainingPlan | None, date | None]:
    plan = db.scalar(select(TrainingPlan).where(TrainingPlan.status == "active"))
    if plan is None:
        return None, None
    try:
        return plan, date.fromisoformat(plan.start_date)
    except (ValueError, TypeError):
        return None, None


def _session_on(plan: TrainingPlan, start: date, target: date):
    elapsed = (target - start).days
    if elapsed < 0:
        return None
    week_no = elapsed // 7 + 1
    week = next((w for w in plan.weeks if w.week_number == week_no), None)
    if week is None:
        return None
    return next((s for s in week.sessions if s.day_of_week == target.weekday()), None)


def _check_reengage(db: Session, ref: date) -> CoachEvent | None:
    """Yesterday's prescribed session was skipped and today is still empty."""
    plan, start = _active_plan(db)
    if plan is None:
        return None
    yesterday = ref - timedelta(days=1)
    sess = _session_on(plan, start, yesterday)
    if sess is None or (sess.execution_status or "") != "skipped":
        return None
    if _has_run_on(db, ref):
        return None
    return log_event(
        db,
        date_str=ref.isoformat(),
        event_type="trigger",
        title="Ci sei?",
        detail="Ieri hai saltato la seduta e oggi non hai ancora corso. "
        "Vuoi che riorganizzi la settimana?",
        after={"trigger": "reengage", "actions": ["defer", "reduce"], "deep_link": "coach/today"},
        notifiable=True,
        priority="medium",
        dedupe_key=f"trigger:reengage:{_week_key(ref)}",
    )


def _check_recalibrate(db: Session, ref: date) -> CoachEvent | None:
    """>=3 too-hard executions in the last 10 days → offer to loosen paces."""
    plan, start = _active_plan(db)
    if plan is None:
        return None
    cutoff = ref - timedelta(days=_TOO_HARD_WINDOW_DAYS)
    count = 0
    for week in plan.weeks:
        for sess in week.sessions:
            if (sess.execution_status or "") != "too_hard":
                continue
            d = start + timedelta(days=(week.week_number - 1) * 7 + sess.day_of_week)
            if cutoff <= d <= ref:
                count += 1
    if count < _TOO_HARD_THRESHOLD:
        return None
    return log_event(
        db,
        date_str=ref.isoformat(),
        event_type="trigger",
        title="Ritmi target troppo stretti?",
        detail=f"Hai chiuso {count} sedute piu' dure del previsto nelle ultime due "
        "settimane. Vuoi che ricalibri i ritmi (+5 s/km)?",
        after={"trigger": "recalibrate", "actions": ["recalibrate"]},
        notifiable=True,
        priority="low",
        dedupe_key=f"trigger:recalibrate:{_week_key(ref)}",
    )


def _hrv_low_streak(db: Session, ref: date) -> int:
    """Consecutive days ending at ``ref`` whose HRV is 'low' vs the baseline (Q1)."""
    history = hrv_history(db, ref=ref, days=40)
    if not history:
        return 0
    by_date = dict(history)
    streak = 0
    for offset in range(0, _HRV_LOW_STREAK_DAYS + 2):
        day = ref - timedelta(days=offset)
        if day not in by_date:
            break
        window = [(d, v) for d, v in history if d <= day]
        if hrv_baseline(window).status == "low":
            streak += 1
        else:
            break
    return streak


def _check_hrv_watch(db: Session, ref: date) -> CoachEvent | None:
    """HRV under the personal baseline for >=5 consecutive days → pre-red nudge."""
    if _hrv_low_streak(db, ref) < _HRV_LOW_STREAK_DAYS:
        return None
    return log_event(
        db,
        date_str=ref.isoformat(),
        event_type="trigger",
        title="HRV in calo da giorni",
        detail="La tua HRV e' sotto la baseline da diversi giorni: alleggerisci "
        "ora, prima che diventi affaticamento vero.",
        after={"trigger": "hrv_watch", "actions": ["reduce"]},
        notifiable=True,
        priority="medium",
        dedupe_key=f"trigger:hrv_watch:{_week_key(ref)}",
    )


def evaluate_triggers(db: Session, ref: date | None = None) -> list[CoachEvent]:
    """Run every behavioural trigger; return the events actually created.

    Each ``_check_*`` is independent and self-deduped; a failure in one must not
    suppress the others, so they run isolated and best-effort.
    """
    ref = ref or date.today()
    created: list[CoachEvent] = []
    for check in (_check_reengage, _check_recalibrate, _check_hrv_watch):
        try:
            event = check(db, ref)
        except Exception as exc:  # noqa: BLE001 - one bad trigger must not sink the rest
            logger.warning("Trigger %s failed: %s", check.__name__, exc)
            continue
        if event is not None:
            created.append(event)
    return created
