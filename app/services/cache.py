"""In-process response cache for the hot read endpoints (Roadmap Q5).

``/api/mobile/overview`` and ``/api/activities/heatmap`` recompute everything on
every call — training metrics, PRs, badges, snapshot, race prediction and the
daily decision, all over the full activity history. None of that changes
between two reads with no write in between, so we cache the built payload and
serve it verbatim until the underlying data actually changes.

**Version-based invalidation, one central hook.** A module-level *generation*
counter is bumped by a single SQLAlchemy ``after_flush`` listener whenever any
ORM insert/update/delete is flushed — no invalidation calls scattered across
the write endpoints. The cache version is ``(generation, today)``; ``today`` is
part of it because the daily decision is computed for ``date.today()`` and must
refresh at midnight even with no writes.

*Why a generation counter and not the ``(max(Activity.id), count, …)``
fingerprint originally sketched:* that fingerprint is blind to in-place row
updates that leave id/count untouched — an RPE or notes edit, a same-day
re-check-in, a plan session's execution status, an adaptive plan tweak — and
would serve a stale overview after any of them. The ``after_flush`` counter
catches every mutation for free.

**Single-worker only.** The cache lives in this process (our deployment runs
uvicorn with one worker). With multiple workers each keeps its own counter, so
a write served by one worker would not invalidate another worker's cache →
stale reads. A multi-worker deploy must move this to a shared store (e.g.
Redis) and derive the version from a DB fingerprint instead. Documented here,
not solved.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any, TypeVar

from sqlalchemy import event
from sqlalchemy.orm import Session

T = TypeVar("T")

# Bumped on every flush that carries real changes; part of the cache version.
_generation = 0
# key -> (version, payload)
_store: dict[str, tuple[tuple[int, str], Any]] = {}
_listener_registered = False


def _on_flush(session: Session, _flush_context: Any) -> None:
    """Bump the generation whenever a flush carries inserts/updates/deletes.

    Reads never flush, so a plain GET does not move the counter and the next
    identical GET is a cache hit. A rolled-back transaction over-bumps (the
    cache invalidates needlessly) — correctness is preserved, we just recompute
    once more than strictly necessary.
    """
    if session.new or session.dirty or session.deleted:
        global _generation
        _generation += 1


def _ensure_listener() -> None:
    """Register the flush listener exactly once (survives engine resets)."""
    global _listener_registered
    if _listener_registered:
        return
    # Listen on the Session *class* so it applies to every session the app
    # opens, across test engine resets, without re-registering.
    event.listen(Session, "after_flush", _on_flush)
    _listener_registered = True


def current_version() -> tuple[int, str]:
    """The version any cached payload is tagged with right now."""
    return (_generation, date.today().isoformat())


def get_or_compute(key: str, compute: Callable[[], T]) -> T:
    """Return the cached payload for ``key`` if still current, else recompute.

    ``compute`` is only invoked on a miss (first call, or after any write /
    a new day). Its result is stored under the current version and returned.
    """
    version = current_version()
    hit = _store.get(key)
    if hit is not None and hit[0] == version:
        return hit[1]
    payload = compute()
    _store[key] = (version, payload)
    return payload


def invalidate_all() -> None:
    """Drop everything and move the version forward.

    Used by tests between databases (each gets a fresh engine but this module
    is a process global) and available as a manual escape hatch.
    """
    global _generation
    _store.clear()
    _generation += 1


_ensure_listener()
