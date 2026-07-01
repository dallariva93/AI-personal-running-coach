"""Adaptive plan after sync (World-Class Roadmap #8).

After every new activity or check-in the plan should react to how the athlete is
actually responding — not stay a static PDF. This service folds the live signals
(injury risk, readiness, form, acute load) into the next few days of the active
multi-week plan: it scales upcoming volume and, when the athlete is compromised,
eases the intensity of imminent quality sessions.

Idempotent by design: the *original* prescription is captured once into the
``base_*`` columns, and every run recomputes ``target_distance_km`` /
``session_type`` from that base times the current factor. Re-running after each
sync therefore converges instead of compounding, and the change is fully
reversible (when signals recover, the base is restored).

Only future, not-yet-completed sessions within a short horizon are touched, so
past sessions and long-range structure are never rewritten.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import TrainingPlan, TrainingPlanSession
from app.logging_config import get_logger
from app.processing import adapt_plan, compute_metrics
from app.processing.decision import _HARD_TYPES, _REST_TYPES
from app.schemas import TrainingMetrics
from app.services.checkin import latest_checkin
from app.services.event_service import log_event, signal_list
from app.services.ingest import _all_summaries
from app.services.profile import get_profile

logger = get_logger("app.services.adaptive_plan")

# How many days ahead the adapter is allowed to reshape.
_HORIZON_DAYS = 7


def _should_ease(m: TrainingMetrics) -> bool:
    """True when live signals warrant pulling intensity back on quality days."""
    if m.injury_level == "high":
        return True
    if m.readiness_state == "red":
        return True
    if m.tsb is not None and m.tsb <= -25:
        return True
    if m.acwr is not None and m.acwr >= 1.5:
        return True
    return False


def _session_date(start: date, week_number: int, day_of_week: int) -> date:
    """Absolute date of a session given the plan start (week 1, Monday-anchored)."""
    return start + timedelta(days=(week_number - 1) * 7 + day_of_week)


def adapt_plan_after_sync(db: Session, ref: date | None = None) -> dict:
    """Reshape the active plan's next few days from live signals. Idempotent.

    Returns a small summary: ``{"adjusted": n, "factor": f, "notes": [...]}``.
    A no-op (no active plan) returns ``{"adjusted": 0}``.
    """
    ref = ref or date.today()
    plan = db.scalar(select(TrainingPlan).where(TrainingPlan.status == "active"))
    if plan is None:
        return {"adjusted": 0, "factor": 1.0, "notes": []}

    try:
        start = date.fromisoformat(plan.start_date)
    except (ValueError, TypeError):
        return {"adjusted": 0, "factor": 1.0, "notes": []}

    summaries = _all_summaries(db)
    profile = get_profile(db)
    checkin = latest_checkin(db)
    metrics = compute_metrics(summaries, ref=ref, profile=profile, checkin=checkin)

    factor, notes = adapt_plan(metrics)
    ease = _should_ease(metrics)
    horizon_end = ref + timedelta(days=_HORIZON_DAYS)
    signals = signal_list(metrics)

    adjusted = 0
    for week in plan.weeks:
        for sess in week.sessions:
            sess_date = _session_date(start, week.week_number, sess.day_of_week)
            # Only reshape upcoming, not-yet-done sessions in the horizon window.
            if sess_date < ref or sess_date > horizon_end or sess.completed:
                continue
            if (sess.session_type or "").lower() in _REST_TYPES:
                continue
            change = _adjust_session(sess, factor, ease)
            if change is not None:
                adjusted += 1
                _log_adaptation(db, change, signals, sess_date)

    db.flush()
    if adjusted:
        logger.info("Adaptive plan: %d session(s) adjusted (factor %.2f)", adjusted, factor)
    return {"adjusted": adjusted, "factor": factor, "notes": notes}


def _adjust_session(
    sess: TrainingPlanSession, factor: float, ease: bool
) -> dict | None:
    """Apply the volume factor and (optional) intensity ease from the base.

    Idempotent. Returns a change record ``{title, before_km, after_km,
    before_type, after_type, session_id}`` when something changed, else ``None``.
    """
    # Capture the untouched original once.
    if sess.base_target_distance_km is None and sess.target_distance_km is not None:
        sess.base_target_distance_km = sess.target_distance_km
    if sess.base_session_type is None:
        sess.base_session_type = sess.session_type

    before_km = sess.target_distance_km
    before_type = sess.session_type
    changed = False
    note_parts: list[str] = []

    # Volume: always derived from the captured base, so runs don't compound.
    if sess.base_target_distance_km is not None:
        new_km = round(sess.base_target_distance_km * factor, 1)
        if new_km != sess.target_distance_km:
            sess.target_distance_km = new_km
            changed = True
        if factor < 1.0:
            note_parts.append(f"volume {int(round((1 - factor) * 100))}% ridotto")

    # Intensity: ease imminent quality work; restore it when signals recover.
    base_type = (sess.base_session_type or "").lower()
    if ease and base_type in _HARD_TYPES:
        if sess.session_type != "easy":
            sess.session_type = "easy"
            changed = True
        note_parts.append("qualità alleggerita per recupero")
    elif not ease and sess.base_session_type and sess.session_type != sess.base_session_type:
        # Restore the original intensity now that the athlete has recovered.
        sess.session_type = sess.base_session_type
        changed = True

    new_note = "; ".join(note_parts) if note_parts else None
    if new_note != sess.adjustment_note:
        sess.adjustment_note = new_note
        changed = True

    if not changed:
        return None
    return {
        "session_id": sess.id,
        "title": sess.title,
        "before_km": before_km,
        "after_km": sess.target_distance_km,
        "before_type": before_type,
        "after_type": sess.session_type,
    }


def _log_adaptation(
    db: Session, change: dict, signals: list[str], sess_date: date
) -> None:
    """Write an audit event for one adapted session, notifiable if significant."""
    title = change["title"] or "Seduta"
    b_km, a_km = change["before_km"], change["after_km"]
    b_type, a_type = change["before_type"], change["after_type"]
    why = (" perché " + ", ".join(signals)) if signals else ""

    type_changed = (b_type or "") != (a_type or "")
    km_delta = (
        abs((a_km or 0) - (b_km or 0)) / b_km if (b_km and a_km is not None) else 0.0
    )

    if type_changed and (a_type or "") == "easy":
        headline = f"{title}: qualità alleggerita"
        detail = f"Il coach ha alleggerito {title} (da {b_type} a facile){why}."
    elif type_changed:
        headline = f"{title}: intensità ripristinata"
        detail = (
            f"Il coach ha ripristinato l'intensità di {title} ({a_type}): "
            "segnali in miglioramento."
        )
    elif a_km is not None and b_km is not None and a_km < b_km:
        headline = f"{title} ridotto a {a_km:g} km"
        detail = f"Il coach ha ridotto {title} da {b_km:g} a {a_km:g} km{why}."
    elif a_km is not None and b_km is not None and a_km > b_km:
        headline = f"{title} riportato a {a_km:g} km"
        detail = f"Il coach ha riportato {title} a {a_km:g} km: segnali in miglioramento."
    else:
        headline = f"{title}: piano aggiornato"
        detail = f"Il coach ha aggiornato {title}{why}."

    significant = type_changed or km_delta >= 0.15
    log_event(
        db,
        date_str=sess_date.isoformat(),
        event_type="plan_adapted",
        title=headline,
        detail=detail,
        signals=signals,
        before={"distance_km": b_km, "session_type": b_type},
        after={"distance_km": a_km, "session_type": a_type},
        plan_session_id=change["session_id"],
        notifiable=significant,
        dedupe_key=f"{sess_date.isoformat()}:adapt:{change['session_id']}:{a_km}:{a_type}",
    )
