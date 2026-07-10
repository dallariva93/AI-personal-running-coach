"""Enforce the chat-agreed weekly structure on a generated plan.

The pre-plan chat ends with an agreed weekly skeleton (``week_structure`` in the
runner context, or at minimum ``fixed_sessions``). Generation is a *separate*
model call, so nothing guarantees its output matches what the athlete saw and
confirmed in chat — and when the AI call fails, the offline template fallback
ignores the chat entirely. This module closes that gap deterministically:
given the generated plan and the runner-context JSON, it reshapes every week so
the agreed days carry the agreed session types (and paces), swapping sessions
when possible and mutating them when not.

Pure function: dict in, dict out, no I/O. Weeks that contain the goal race are
left untouched (race week has its own structure).
"""

from __future__ import annotations

import json
import re
from typing import Any

# A pace token like "5:45/km" or a range "4:15-4:20/km" (any dash, optional
# spaces around "/"). Used to reconcile the generator's prose with the enforced
# structured pace.
_PACE_TOKEN_RE = re.compile(r"\d{1,2}:\d{2}(?:\s*[–-]\s*\d{1,2}:\d{2})?\s*/\s*km")

# Steady-pace session types: one target pace describes the whole run, so it's
# safe to normalize the description's pace to match. Intervals are excluded —
# their descriptions legitimately list several paces (work + recovery).
_STEADY_TYPES = {"easy", "long", "tempo"}


def _apply_agreed_pace(session: dict, pace: str, stype: str) -> None:
    """Set ``target_pace`` and, for steady-pace sessions, make the description's
    embedded pace match it.

    The generator (a separate model call) writes a free-text ``description`` with
    its own pace, which can contradict the pace agreed in chat and enforced into
    ``target_pace`` — the athlete then sees "5:45/km" on the chip but "5:01/km"
    in the description. Rewriting the pace tokens keeps the two in sync.
    """
    session["target_pace"] = pace
    if stype in _STEADY_TYPES:
        desc = session.get("description")
        if isinstance(desc, str) and _PACE_TOKEN_RE.search(desc):
            session["description"] = _PACE_TOKEN_RE.sub(pace, desc)

# Day-name → day_of_week (0=Mon). Accepts Italian/English names and integers.
_DAY_MAP = {
    "lun": 0, "lunedi": 0, "lunedì": 0, "mon": 0, "monday": 0,
    "mar": 1, "martedi": 1, "martedì": 1, "tue": 1, "tuesday": 1,
    "mer": 2, "mercoledi": 2, "mercoledì": 2, "wed": 2, "wednesday": 2,
    "gio": 3, "giovedi": 3, "giovedì": 3, "thu": 3, "thursday": 3,
    "ven": 4, "venerdi": 4, "venerdì": 4, "fri": 4, "friday": 4,
    "sab": 5, "sabato": 5, "sat": 5, "saturday": 5,
    "dom": 6, "domenica": 6, "sun": 6, "sunday": 6,
}

# Session-type synonyms → canonical plan types.
_TYPE_MAP = {
    "easy": "easy", "facile": "easy", "recovery": "easy", "recupero": "easy",
    "long": "long", "lungo": "long",
    "tempo": "tempo", "soglia": "tempo", "threshold": "tempo", "medio": "tempo",
    "intervals": "intervals", "intervalli": "intervals", "ripetute": "intervals",
    "rest": "rest", "riposo": "rest",
    "race": "race", "gara": "race", "race_pace": "race",
    "cross": "cross", "strides": "strides", "allunghi": "strides",
}

_DEFAULT_TITLES = {
    "easy": "Corsa facile",
    "long": "Lungo",
    "tempo": "Tempo",
    "intervals": "Ripetute",
    "rest": "Riposo",
    "race": "Gara",
    "cross": "Cross-training",
    "strides": "Allunghi",
}

_DAY_NAMES = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"]


def _to_dow(value: Any) -> int | None:
    if isinstance(value, int) and 0 <= value <= 6:
        return value
    if isinstance(value, str):
        return _DAY_MAP.get(value.strip().lower())
    return None


def _canonical_type(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return _TYPE_MAP.get(value.strip().lower())


def parse_week_structure(runner_context: str | None) -> list[dict]:
    """Extract the agreed weekly skeleton from the runner-context JSON.

    Prefers ``week_structure`` (the full agreed week); falls back to
    ``fixed_sessions`` (only the immovable commitments). Entries that can't be
    mapped to a valid day/type are skipped. Returns normalized entries:
    ``{"dow": int, "type": str, "pace": str|None, "distance_km": float|None,
    "note": str|None}``.
    """
    if not runner_context:
        return []
    try:
        ctx = json.loads(runner_context)
    except (ValueError, TypeError):
        return []
    if not isinstance(ctx, dict):
        return []

    raw = ctx.get("week_structure") or ctx.get("fixed_sessions") or []
    if not isinstance(raw, list):
        return []

    out: list[dict] = []
    seen_days: set[int] = set()
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        dow = _to_dow(entry.get("day"))
        stype = _canonical_type(entry.get("type"))
        if dow is None or stype is None or dow in seen_days:
            continue
        seen_days.add(dow)
        distance = entry.get("distance_km")
        try:
            distance = float(distance) if distance is not None else None
        except (TypeError, ValueError):
            distance = None
        out.append(
            {
                "dow": dow,
                "type": stype,
                "pace": entry.get("pace") or None,
                "distance_km": distance,
                "note": entry.get("note") or None,
            }
        )
    return out


def enforce_week_structure(
    plan_data: dict, runner_context: str | None
) -> tuple[dict, list[str]]:
    """Reshape the generated plan so agreed days carry the agreed sessions.

    For each entry of the agreed structure, in every week (except weeks that
    already contain the goal race):

    * matching type on the agreed day → keep it (apply the agreed pace if given);
    * the type exists elsewhere in the week → swap the two sessions' days, so
      volumes and descriptions built by the generator are preserved;
    * the type is absent → rewrite the session on that day to the agreed type.

    Returns ``(plan_data, notes)`` where notes describe every change made — the
    caller can log them for the audit trail. No structure agreed → no changes.
    """
    structure = parse_week_structure(runner_context)
    if not structure or not isinstance(plan_data.get("weeks"), list):
        return plan_data, []

    notes: list[str] = []
    for week in plan_data["weeks"]:
        sessions = week.get("sessions")
        if not isinstance(sessions, list) or not sessions:
            continue
        # The goal-race week keeps its own structure (taper/race day).
        if any(
            _canonical_type(s.get("session_type")) == "race"
            for s in sessions
            if isinstance(s, dict)
        ):
            continue

        by_day = {
            s.get("day_of_week"): s for s in sessions if isinstance(s, dict)
        }
        locked: set[int] = set()

        for entry in structure:
            dow, want = entry["dow"], entry["type"]
            current = by_day.get(dow)
            if current is None:
                continue

            if _canonical_type(current.get("session_type")) == want:
                if entry["pace"] and want not in ("rest", "cross"):
                    _apply_agreed_pace(current, entry["pace"], want)
                locked.add(dow)
                continue

            # Try to swap with a same-type session elsewhere in the week.
            donor = next(
                (
                    s
                    for d, s in by_day.items()
                    if d not in locked
                    and d != dow
                    and _canonical_type(s.get("session_type")) == want
                ),
                None,
            )
            week_no = week.get("week_number", "?")
            if donor is not None:
                donor_day = donor["day_of_week"]
                donor["day_of_week"], current["day_of_week"] = dow, donor_day
                by_day[dow], by_day[donor_day] = donor, current
                if entry["pace"] and want not in ("rest", "cross"):
                    _apply_agreed_pace(donor, entry["pace"], want)
                notes.append(
                    f"settimana {week_no}: {want} spostata a "
                    f"{_DAY_NAMES[dow]} (era {_DAY_NAMES[donor_day]})"
                )
            else:
                # Rewrite the session in place to the agreed type.
                current["session_type"] = want
                current["title"] = entry["note"] or _DEFAULT_TITLES.get(want, want)
                if want == "rest":
                    current["target_distance_km"] = None
                    current["target_pace"] = None
                    current["target_duration_min"] = None
                    current["description"] = "Recupero completo"
                else:
                    if entry["distance_km"] is not None:
                        current["target_distance_km"] = entry["distance_km"]
                    if entry["pace"]:
                        _apply_agreed_pace(current, entry["pace"], want)
                notes.append(
                    f"settimana {week_no}: {_DAY_NAMES[dow]} impostato a {want}"
                )
            locked.add(dow)

        week["sessions"] = sorted(
            sessions, key=lambda s: s.get("day_of_week", 0)
        )

    return plan_data, notes
