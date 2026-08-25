"""Push a planned week to the Garmin Connect calendar, on request.

The one place in this app where the coach writes into the outside world, so the
shape of the flow matters more than its size:

* **Only when asked.** Nothing here runs on a schedule or as a side effect of a
  sync. An export happens because the athlete asked for one.
* **One week at a time.** The plan re-adapts after every sync, so exporting
  months ahead would fill the watch with sessions the plan no longer prescribes.
* **Preview, then confirm.** :func:`preview_week` renders exactly what would
  land on the watch and returns a code; :func:`push_week` refuses to do anything
  without it. The code is derived from the week's *content*, so if the plan
  changes in between — which it does, on its own — the old code stops working
  and the athlete sees the new version before it is sent.

The reason for the ceremony is not the risk of a leaked URL. It is that a
workout on a watch gets **run**: a session that arrives subtly wrong is not a
bad number on a screen, it is an interval session done at the wrong pace.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collection.garmin_workouts import (
    WorkoutBuildError,
    build_workout,
    describe_steps,
)
from app.db.models import TrainingPlan, TrainingPlanSession, TrainingPlanWeek
from app.exceptions import CollectionError
from app.logging_config import get_logger

logger = get_logger("app.services.garmin_export")

# Session types that are not a run to put on a watch.
_NOT_A_WORKOUT = {"rest", "cross", "race"}
# How long a confirmation code stays usable. Long enough to read the preview and
# answer, short enough that a code left in an old chat is inert.
CODE_TTL_S = 1800


@dataclass
class ExportResult:
    """What a push actually did."""

    pushed: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "pushed": self.pushed,
            "updated": self.updated,
            "skipped": self.skipped,
            "errors": self.errors,
        }


# ── selecting the week ───────────────────────────────────────────────────────


def _active_plan(session: Session) -> TrainingPlan:
    plan = session.scalars(
        select(TrainingPlan).where(TrainingPlan.status == "active").limit(1)
    ).first()
    if plan is None:
        raise CollectionError("Nessun piano attivo da esportare.")
    return plan


def _week(session: Session, plan: TrainingPlan, week_number: int) -> TrainingPlanWeek:
    week = session.scalars(
        select(TrainingPlanWeek).where(
            TrainingPlanWeek.plan_id == plan.id,
            TrainingPlanWeek.week_number == week_number,
        )
    ).first()
    if week is None:
        raise CollectionError(f"La settimana {week_number} non esiste in questo piano.")
    return week


def current_week_number(plan: TrainingPlan, ref: date | None = None) -> int:
    """Which week of the plan ``ref`` falls in (1-based, clamped to the plan)."""
    ref = ref or date.today()
    try:
        start = date.fromisoformat(plan.start_date)
    except (TypeError, ValueError):
        return 1
    delta_weeks = (ref - start).days // 7
    return max(1, min(int(plan.weeks_total or 1), delta_weeks + 1))


def session_date(plan: TrainingPlan, week_number: int, day_of_week: int) -> str | None:
    """The calendar date a session falls on."""
    try:
        start = date.fromisoformat(plan.start_date)
    except (TypeError, ValueError):
        return None
    # Plans start on the Monday of their first week.
    monday = start - timedelta(days=start.weekday())
    return (monday + timedelta(weeks=week_number - 1, days=day_of_week)).isoformat()


# ── preview + confirmation code ──────────────────────────────────────────────


def _exportable(session_row: TrainingPlanSession) -> bool:
    return session_row.session_type not in _NOT_A_WORKOUT and bool(session_row.steps)


def _week_fingerprint(entries: list[dict[str, Any]]) -> str:
    """A stable hash of exactly what would be sent."""
    payload = json.dumps(entries, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _code_for(fingerprint: str, bucket: int) -> str:
    """A short code bound to this content and this time window.

    Derived from the deployment's own key material, so it cannot be guessed
    from the preview; bound to the fingerprint, so a plan that adapts between
    preview and push invalidates it rather than silently sending the old week.
    """
    from app.security.crypto import _resolve_key

    mac = hmac.new(
        str(_resolve_key()).encode("utf-8"),
        f"{fingerprint}:{bucket}".encode(),
        hashlib.sha256,
    )
    return mac.hexdigest()[:6].upper()


def _bucket(now: float | None = None) -> int:
    return int((now or time.time()) // CODE_TTL_S)


def preview_week(
    session: Session, week_number: int | None = None, ref: date | None = None
) -> dict[str, Any]:
    """Render the week as it would appear on the watch, plus a confirm code."""
    plan = _active_plan(session)
    number = week_number or current_week_number(plan, ref)
    week = _week(session, plan, number)

    rows = session.scalars(
        select(TrainingPlanSession)
        .where(TrainingPlanSession.week_id == week.id)
        .order_by(TrainingPlanSession.day_of_week)
    ).all()

    entries: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for row in rows:
        item = {
            "session_id": row.id,
            "date": session_date(plan, number, row.day_of_week),
            "type": row.session_type,
            "title": row.title,
            "steps": describe_steps(row.steps),
            "already_on_garmin": bool(row.garmin_workout_id),
        }
        if _exportable(row):
            entries.append(item)
        else:
            item["reason"] = (
                "Non è una seduta di corsa da orologio."
                if row.session_type in _NOT_A_WORKOUT
                else "Nessuna struttura: questa seduta è precedente agli step "
                "strutturati e va rigenerata per poter essere esportata."
            )
            skipped.append(item)

    fingerprint = _week_fingerprint(entries)
    return {
        "week_number": number,
        "phase": week.phase,
        "sessions_to_push": entries,
        "not_exported": skipped,
        "confirm_code": _code_for(fingerprint, _bucket()) if entries else None,
        "expires_in_minutes": CODE_TTL_S // 60,
    }


def verify_code(session: Session, week_number: int, code: str, ref: date | None = None) -> bool:
    """True when ``code`` matches this week *as it is right now*."""
    if not code:
        return False
    preview = preview_week(session, week_number, ref=ref)
    fingerprint = _week_fingerprint(preview["sessions_to_push"])
    now = _bucket()
    candidates = {_code_for(fingerprint, now), _code_for(fingerprint, now - 1)}
    return any(hmac.compare_digest(code.strip().upper(), c) for c in candidates)


# ── the push ─────────────────────────────────────────────────────────────────


def push_week(
    session: Session,
    week_number: int,
    confirm_code: str,
    *,
    client: Any = None,
    ref: date | None = None,
) -> ExportResult:
    """Upload and schedule the week's sessions. Requires a valid confirm code.

    Refuses rather than guesses at every step: an unconfirmed push, a session
    without structure, a workout that will not build. What reaches the calendar
    is only ever what the preview showed.
    """
    if not verify_code(session, week_number, confirm_code, ref=ref):
        raise CollectionError(
            "Codice di conferma non valido o scaduto. Se il piano è cambiato da "
            "quando l'hai visto, il codice smette di funzionare apposta: "
            "richiedi di nuovo l'anteprima e controlla la settimana aggiornata."
        )

    plan = _active_plan(session)
    week = _week(session, plan, week_number)
    rows = session.scalars(
        select(TrainingPlanSession)
        .where(TrainingPlanSession.week_id == week.id)
        .order_by(TrainingPlanSession.day_of_week)
    ).all()

    client = client or _garmin_client()
    result = ExportResult()

    for row in rows:
        if not _exportable(row):
            result.skipped += 1
            continue
        when = session_date(plan, week_number, row.day_of_week)
        if when is None:
            result.skipped += 1
            continue

        try:
            workout = build_workout(
                f"{row.title} — S{week_number}",
                row.steps,
                duration_min=row.target_duration_min,
            )
        except WorkoutBuildError as exc:
            # Better a session missing from the watch than one that is there and
            # wrong: this one gets run.
            result.errors.append(f"{when} {row.title}: {exc}")
            result.skipped += 1
            continue

        try:
            was_present = bool(row.garmin_workout_id)
            if was_present:
                # Replace rather than edit: the plan may have changed the shape
                # of the session, not just its numbers.
                _remove(client, row)
            created = client.upload_running_workout(workout)
            workout_id = str(
                created.get("workoutId") or created.get("workoutIdString") or ""
            )
            if not workout_id:
                raise CollectionError("Garmin non ha restituito un workoutId.")
            client.schedule_workout(workout_id, when)
            row.garmin_workout_id = workout_id
            row.garmin_scheduled_date = when
            if was_present:
                result.updated += 1
            else:
                result.pushed += 1
        except Exception as exc:  # noqa: BLE001 - one session must not stop the week
            result.errors.append(f"{when} {row.title}: {exc}")

    session.commit()
    logger.info("Export Garmin settimana %s: %s", week_number, result.as_dict())
    return result


def _remove(client: Any, row: TrainingPlanSession) -> None:
    """Withdraw a previously pushed workout, best-effort.

    Failing to delete the old copy must not stop the new one from going out —
    a duplicate in the calendar is a nuisance, a missing session is a lost day.
    """
    try:
        client.delete_workout(row.garmin_workout_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Workout Garmin %s non rimosso: %s", row.garmin_workout_id, exc)
    row.garmin_workout_id = None
    row.garmin_scheduled_date = None


def _garmin_client() -> Any:
    """The authenticated Garmin client, reusing the source's cached login."""
    from app.collection.sources import GarminSource

    source = GarminSource()
    return source._login()  # noqa: SLF001 - same package, deliberate reuse
