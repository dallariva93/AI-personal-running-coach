"""Historical backfill: walk the whole Garmin history, not just the head.

``ingest_runs`` reads the most recent N activities — enough to stay current,
useless for building a year of context. This module pages backwards through
the history so the coaching engine (and the MCP connector) can reason over
seasons instead of weeks.

Three properties matter more than speed here:

* **Idempotent.** Re-running never duplicates: ``upsert_activity`` keys on the
  Garmin id, and already-stored activities are skipped before any extra call.
* **Resumable.** Progress is checkpointed after every page, so a dropped
  connection, a rate-limit or a closed laptop costs one page, not the run.
* **Polite.** The Garmin library is unofficial. A deliberate pause between
  calls and exponential backoff on failure is what keeps the account healthy —
  a fast backfill that gets you blocked is not a fast backfill.

The work is split in two passes because their cost differs by ~100x: the
summary pass gets ~100 activities per API call, while enrichment (splits, HR
zones, weather) costs several calls *per activity*. Pass one gets a usable
history in minutes; pass two deepens it in the background.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collection.sources import GarminSource, _is_running
from app.collection.synthesize import garmin_sport, synthesize, synthesize_cross_training
from app.db.models import Activity, SyncState
from app.exceptions import CollectionError
from app.logging_config import get_logger
from app.services.ingest import upsert_activity

logger = get_logger("app.services.backfill")

# Checkpoint keys in `sync_state`.
_OFFSET_KEY = "backfill_offset"
_CUTOFF_KEY = "backfill_cutoff"

PAGE_SIZE = 100
# One second between calls. Garmin publishes no rate limit for this (unofficial)
# API, so this is a deliberately conservative human-ish pace.
THROTTLE_S = 1.0
MAX_PAGES = 500  # hard stop: 50k activities, far beyond any real history


@dataclass
class BackfillResult:
    """What a backfill run did — the summary the CLI prints."""

    pages_fetched: int = 0
    activities_seen: int = 0
    runs_imported: int = 0
    cross_training_imported: int = 0
    skipped_existing: int = 0
    enriched: int = 0
    oldest_date: str | None = None
    completed: bool = False  # True when the cutoff (or the history end) was reached
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "pages_fetched": self.pages_fetched,
            "activities_seen": self.activities_seen,
            "runs_imported": self.runs_imported,
            "cross_training_imported": self.cross_training_imported,
            "skipped_existing": self.skipped_existing,
            "enriched": self.enriched,
            "oldest_date": self.oldest_date,
            "completed": self.completed,
            "errors": self.errors,
        }


# --------------------------------------------------------------------------
# checkpointing
# --------------------------------------------------------------------------
def _get_state(session: Session, key: str) -> str | None:
    row = session.get(SyncState, key)
    return row.value if row else None


def _set_state(session: Session, key: str, value: str) -> None:
    row = session.get(SyncState, key)
    if row is None:
        session.add(SyncState(key=key, value=value))
    else:
        row.value = value
    session.flush()


def _clear_state(session: Session, *keys: str) -> None:
    for key in keys:
        row = session.get(SyncState, key)
        if row is not None:
            session.delete(row)
    session.flush()


def read_checkpoint(session: Session) -> tuple[int, str | None]:
    """Resume point as ``(offset, cutoff_iso)``; ``(0, None)`` when unset."""
    raw_offset = _get_state(session, _OFFSET_KEY)
    try:
        offset = int(raw_offset) if raw_offset else 0
    except ValueError:
        offset = 0
    return offset, _get_state(session, _CUTOFF_KEY)


def reset_checkpoint(session: Session) -> None:
    """Forget the resume point so the next run starts from the newest activity."""
    _clear_state(session, _OFFSET_KEY, _CUTOFF_KEY)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def months_ago(months: int, ref: date | None = None) -> date:
    """``months`` calendar months before ``ref`` (clamped to a valid day)."""
    ref = ref or date.today()
    year, month = ref.year, ref.month - months
    while month <= 0:
        month += 12
        year -= 1
    day = min(ref.day, [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
                        else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return date(year, month, day)


def _activity_date(activity: dict) -> date | None:
    """Local start date of a raw Garmin activity, or None if unparseable."""
    raw = activity.get("startTimeLocal") or activity.get("startTimeGMT")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(str(raw)[:10])
        except ValueError:
            return None


def _existing_garmin_ids(session: Session) -> set[str]:
    """Every Garmin id already stored — one query instead of one per activity."""
    return {
        gid
        for gid in session.scalars(
            select(Activity.garmin_activity_id).where(Activity.garmin_activity_id.is_not(None))
        ).all()
        if gid
    }


# --------------------------------------------------------------------------
# pass 1 — summaries
# --------------------------------------------------------------------------
def backfill_activities(
    session: Session,
    source: GarminSource,
    *,
    months: int = 12,
    page_size: int = PAGE_SIZE,
    throttle_s: float = THROTTLE_S,
    resume: bool = True,
    ref: date | None = None,
    progress: Callable[[str], None] | None = None,
) -> BackfillResult:
    """Page backwards through the Garmin history and store every activity.

    Stops at the first activity older than ``months``, or when the history
    runs out. Runs feed the coaching pipeline; cross-training is stored too
    (it is kept out of the running metrics downstream, not at ingest).
    """
    cutoff = months_ago(months, ref)
    result = BackfillResult()

    offset, saved_cutoff = read_checkpoint(session) if resume else (0, None)
    # A different cutoff means a different job — restart rather than resume
    # into a window the previous run was never walking.
    if resume and saved_cutoff and saved_cutoff != cutoff.isoformat():
        logger.info("Backfill cutoff changed (%s -> %s): restarting", saved_cutoff, cutoff)
        offset = 0
    if offset:
        _emit(progress, f"Riprendo dal checkpoint: offset {offset}")

    _set_state(session, _CUTOFF_KEY, cutoff.isoformat())
    known_ids = _existing_garmin_ids(session)

    for _ in range(MAX_PAGES):
        try:
            page = source.get_activities_page(offset, page_size)
        except CollectionError as exc:
            # The checkpoint is already committed: the caller can just re-run.
            result.errors.append(str(exc))
            logger.warning("Backfill stopped at offset %d: %s", offset, exc)
            break

        result.pages_fetched += 1
        if not page:
            result.completed = True
            _emit(progress, "Fine della cronologia Garmin.")
            break

        reached_cutoff = False
        for activity in page:
            result.activities_seen += 1
            activity_date = _activity_date(activity)
            if activity_date is not None:
                if result.oldest_date is None or activity_date.isoformat() < result.oldest_date:
                    result.oldest_date = activity_date.isoformat()
                if activity_date < cutoff:
                    reached_cutoff = True
                    continue

            activity_id = activity.get("activityId")
            if activity_id is not None and str(activity_id) in known_ids:
                result.skipped_existing += 1
                continue

            try:
                if _is_running(activity):
                    upsert_activity(session, synthesize(activity))
                    result.runs_imported += 1
                else:
                    sport = garmin_sport(activity)
                    if sport is None:
                        continue  # a type we deliberately don't track
                    upsert_activity(session, synthesize_cross_training(activity, sport))
                    result.cross_training_imported += 1
            except Exception as exc:  # noqa: BLE001 - one bad payload must not stop the run
                msg = f"Attività {activity_id} non importata: {exc}"
                result.errors.append(msg)
                logger.warning(msg)
                continue
            if activity_id is not None:
                known_ids.add(str(activity_id))

        offset += len(page)
        _set_state(session, _OFFSET_KEY, str(offset))
        session.commit()  # checkpoint + data land together
        _emit(
            progress,
            f"Pagina {result.pages_fetched}: {result.activities_seen} attività viste, "
            f"{result.runs_imported} corse importate (fino al {result.oldest_date}).",
        )

        if reached_cutoff:
            result.completed = True
            _emit(progress, f"Raggiunto il limite di {months} mesi ({cutoff.isoformat()}).")
            break
        if len(page) < page_size:
            result.completed = True
            _emit(progress, "Fine della cronologia Garmin.")
            break
        time.sleep(throttle_s)

    if result.completed:
        reset_checkpoint(session)
        session.commit()
    logger.info("Backfill summary pass: %s", result.as_dict())
    return result


# --------------------------------------------------------------------------
# pass 2 — enrichment
# --------------------------------------------------------------------------
def enrich_missing(
    session: Session,
    source: GarminSource,
    *,
    limit: int = 200,
    throttle_s: float = THROTTLE_S,
    progress: Callable[[str], None] | None = None,
) -> BackfillResult:
    """Fill in splits / HR zones / weather for stored runs that lack them.

    Deliberately a separate pass: this costs several API calls per activity,
    so it runs after a fast summary backfill and can be re-run in batches
    without ever redoing work (activities with splits are skipped).
    """
    result = BackfillResult()
    rows = list(
        session.scalars(
            select(Activity)
            .where(
                Activity.sport == "run",
                Activity.garmin_activity_id.is_not(None),
                Activity.splits_km.is_(None),
            )
            .order_by(Activity.date.desc())
            .limit(limit)
        ).all()
    )
    if not rows:
        result.completed = True
        _emit(progress, "Nessuna corsa da arricchire.")
        return result

    _emit(progress, f"Arricchisco {len(rows)} corse…")
    for row in rows:
        result.activities_seen += 1
        try:
            extras = source.get_activity_enrichment(row.garmin_activity_id)
        except Exception as exc:  # noqa: BLE001 - keep going through a bad activity
            msg = f"Enrichment fallito per {row.garmin_activity_id}: {exc}"
            result.errors.append(msg)
            logger.warning(msg)
            time.sleep(throttle_s)
            continue

        if extras:
            for key, value in extras.items():
                if value is not None and hasattr(row, key):
                    setattr(row, key, value)
            result.enriched += 1
        if result.enriched and result.enriched % 20 == 0:
            session.commit()
            _emit(progress, f"…{result.enriched}/{len(rows)} arricchite")
        time.sleep(throttle_s)

    session.commit()
    result.completed = True
    logger.info("Backfill enrichment pass: %s", result.as_dict())
    return result


def _emit(progress: Callable[[str], None] | None, message: str) -> None:
    if progress is not None:
        progress(message)
    else:
        logger.info(message)
