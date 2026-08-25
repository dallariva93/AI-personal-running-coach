"""Deterministic week rebalancer (Fase E — plan architecture review).

When the athlete moves a session, a good coach *reshapes* the week rather than
merely warning "two hard days in a row". This pure function restores ≥48 h
spacing between quality sessions by relocating a hard session onto a nearby
easy/rest day, never touching a locked day (the one the athlete just placed,
completed sessions, the goal race). It preserves the week's session mix exactly —
it only permutes days — so volume and composition are untouched.

Pure: day→type map in, list of swaps + human notes out. The caller applies the
same swaps to the persisted week.
"""

from __future__ import annotations

_HARD = {"tempo", "intervals", "race", "gara"}
# Days that can receive a relocated hard session.
_RECEIVER = {"easy", "rest", "cross", "strides", "recovery"}
_DAY = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"]
_MAX_PASSES = 4  # a 7-day week can't need more; also guards against loops


def _first_adjacent_hard(day_types: dict[int, str]) -> tuple[int, int] | None:
    for d in range(6):
        if (day_types.get(d) or "").lower() in _HARD and (
            day_types.get(d + 1) or ""
        ).lower() in _HARD:
            return d, d + 1
    return None


def _find_receiver(
    day_types: dict[int, str], locked: set[int], mover: int
) -> int | None:
    """A non-adjacent-to-any-hard day that can take the ``mover``'s hard session."""
    for t in range(7):
        if t == mover or t in locked:
            continue
        if (day_types.get(t) or "").lower() not in _RECEIVER:
            continue
        # Placing a hard session on t must not create a new adjacency.
        left = (day_types.get(t - 1) or "").lower() if t - 1 >= 0 else ""
        right = (day_types.get(t + 1) or "").lower() if t + 1 <= 6 else ""
        if left in _HARD or right in _HARD:
            continue
        return t
    return None


def rebalance_week(
    day_types: dict[int, str], locked: set[int] | None = None
) -> tuple[list[tuple[int, int]], list[str]]:
    """Return (swaps, notes) that separate back-to-back quality days.

    ``swaps`` is a list of ``(day_a, day_b)`` whose sessions exchange days. Apply
    them in order. ``notes`` describe each reshape for the athlete. An empty
    result means the week was already well spaced (or nothing could be moved).
    """
    dt = {d: (t or "").lower() for d, t in day_types.items()}
    locked = set(locked or set())
    swaps: list[tuple[int, int]] = []
    notes: list[str] = []

    for _ in range(_MAX_PASSES):
        conflict = _first_adjacent_hard(dt)
        if conflict is None:
            break
        a, b = conflict
        # Prefer moving the day the athlete did NOT just anchor.
        mover = b if b not in locked else (a if a not in locked else None)
        if mover is None:
            break  # both days are locked — leave it for a warning
        receiver = _find_receiver(dt, locked, mover)
        if receiver is None:
            break  # nowhere safe to put it — leave it for a warning
        moved_type = dt[mover]
        dt[mover], dt[receiver] = dt[receiver], dt[mover]
        swaps.append((mover, receiver))
        notes.append(
            f"Ribilanciata la settimana: {moved_type} spostata a "
            f"{_DAY[receiver]} per lasciare 48h tra le sedute intense."
        )
    return swaps, notes
