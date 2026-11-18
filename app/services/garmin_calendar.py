"""Read what is scheduled in the Garmin calendar — the coach's prescription.

The athlete's sessions are prescribed by a human coach, who places them in the
Garmin calendar every week. That calendar is therefore the source of truth for
*what was asked*, the same way the activity history is the source of truth for
*what was run*. Reading both is what lets the analysis compare the two.

Garmin keeps two views of it, and they do not always agree:

* ``/calendar-service/year/{y}/month/{m0}`` — the visible calendar. Workouts
  copied into the athlete's library and given a date show up here.
* ``/workout-service/schedule/workoutScheduleByPeriod`` — every scheduled
  workout in a date range, adaptive and Garmin Coach plans included. The pinned
  client library (0.3.2) has no method for it, so it is called through the
  generic ``connectapi``.

Both are read and merged; neither is trusted to be complete on its own.

Everything is defensive in the usual way for an unofficial API: an item whose
shape is not recognised is reported as such, and a pace that converts to
something no human runs is shown as the raw value with a flag rather than as a
plausible wrong number.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.logging_config import get_logger

logger = get_logger("app.services.garmin_calendar")

SCHEDULE_BY_PERIOD_PATH = "/workout-service/schedule/workoutScheduleByPeriod"
# A pace outside this window (seconds per km) is not a running pace: the unit
# assumption is wrong somewhere, and the number must not be shown as if it were.
_PLAUSIBLE_PACE_S = (120, 900)

_LABELS = {
    "warmup": "riscaldamento",
    "cooldown": "defaticamento",
    "interval": "corsa",
    "recovery": "recupero",
    "rest": "pausa",
    "other": "step",
}


# ── reading the calendar ─────────────────────────────────────────────────────


def _months(start: date, end: date) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _day(raw: dict[str, Any]) -> date | None:
    for key in ("date", "calendarDate", "scheduledDate", "startDate"):
        value = raw.get(key)
        if value:
            try:
                return date.fromisoformat(str(value)[:10])
            except ValueError:
                continue
    return None


def _normalise(raw: Any, source: str) -> dict[str, Any] | None:
    """One calendar entry in a flat shape, or ``None`` if it is not a workout."""
    if not isinstance(raw, dict):
        return None
    embedded = raw.get("workout") if isinstance(raw.get("workout"), dict) else {}
    when = _day(raw)
    if when is None:
        return None
    workout_id = raw.get("workoutId") or embedded.get("workoutId")
    title = raw.get("title") or raw.get("workoutName") or embedded.get("workoutName")
    if not (workout_id or title):
        return None
    return {
        "date": when,
        "title": str(title or "Allenamento"),
        "workout_id": str(workout_id) if workout_id else None,
        "sport": (
            (embedded.get("sportType") or {}).get("sportTypeKey")
            or raw.get("sportTypeKey")
        ),
        "source": source,
        # The by-period view sometimes carries the whole workout; when it does,
        # there is no need to fetch it again.
        "_workout": embedded if embedded.get("workoutSegments") else None,
    }


def read_calendar(client: Any, start: date, end: date) -> dict[str, Any]:
    """Scheduled workouts between ``start`` and ``end``, from both views.

    Returns ``{"items": [...], "errors": [...], "raw": {...}}``. ``raw`` keeps
    the untouched payloads, for the times a shape needs to be looked at.
    """
    items: dict[tuple[str, str], dict[str, Any]] = {}
    errors: list[str] = []
    raw: dict[str, Any] = {"calendar": [], "by_period": None}

    for year, month in _months(start, end):
        try:
            payload = client.get_scheduled_workouts(year, month)
        except Exception as exc:  # noqa: BLE001 - one view failing is not fatal
            errors.append(f"calendario {year}-{month:02d}: {exc}")
            continue
        raw["calendar"].append(payload)
        for entry in (payload or {}).get("calendarItems") or []:
            if not isinstance(entry, dict) or entry.get("itemType") != "workout":
                continue
            item = _normalise(entry, "calendar")
            if item and start <= item["date"] <= end:
                items[(item["date"].isoformat(), item["workout_id"] or item["title"])] = item

    try:
        rows = client.connectapi(
            SCHEDULE_BY_PERIOD_PATH,
            params={"startDate": start.isoformat(), "endDate": end.isoformat()},
        )
        raw["by_period"] = rows
        if isinstance(rows, dict):
            rows = rows.get("workoutScheduleList") or rows.get("items") or []
        for entry in rows or []:
            item = _normalise(entry, "by_period")
            if item and start <= item["date"] <= end:
                key = (item["date"].isoformat(), item["workout_id"] or item["title"])
                # The visible calendar wins on conflict; by-period only adds.
                items.setdefault(key, item)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"programmazione per periodo: {exc}")

    ordered = sorted(items.values(), key=lambda i: (i["date"], i["title"]))
    return {"items": ordered, "errors": errors, "raw": raw}


# ── describing a Garmin workout ──────────────────────────────────────────────


def describe_garmin_workout(workout: dict[str, Any] | None) -> dict[str, Any]:
    """A Garmin workout as readable steps plus its own notes and estimates.

    The coach's description and per-step notes are kept: a title like "6km FMV"
    means something precise to the coach and the athlete, and the notes are
    often where that meaning is written down.
    """
    if not isinstance(workout, dict):
        return {"steps": [], "warnings": ["Allenamento non leggibile."]}
    warnings: list[str] = []
    steps: list[str] = []
    for segment in workout.get("workoutSegments") or []:
        if isinstance(segment, dict):
            steps += _describe_steps(segment.get("workoutSteps") or [], warnings)
    distance = workout.get("estimatedDistanceInMeters")
    duration = workout.get("estimatedDurationInSecs")
    return {
        "name": workout.get("workoutName"),
        "notes": (workout.get("description") or "").strip() or None,
        "steps": steps,
        "estimated_km": round(float(distance) / 1000, 1) if distance else None,
        "estimated_min": round(float(duration) / 60) if duration else None,
        "warnings": warnings,
    }


def _describe_steps(steps: list[Any], warnings: list[str]) -> list[str]:
    out: list[str] = []
    ordered = sorted(
        (s for s in steps if isinstance(s, dict)), key=lambda s: s.get("stepOrder") or 0
    )
    for step in ordered:
        kind = ((step.get("stepType") or {}).get("stepTypeKey") or "").lower()
        if step.get("type") == "RepeatGroupDTO" or kind == "repeat":
            times = step.get("numberOfIterations") or step.get("endConditionValue") or 0
            inner = "; ".join(_describe_steps(step.get("workoutSteps") or [], warnings))
            out.append(f"{int(times)}× ({inner})")
            continue
        line = f"{_LABELS.get(kind, kind or 'step')} {_extent(step)}{_target(step, warnings)}"
        note = (step.get("description") or "").strip()
        out.append(f"{line} — {note}" if note else line)
    return out


def _extent(step: dict[str, Any]) -> str:
    condition = ((step.get("endCondition") or {}).get("conditionTypeKey") or "").lower()
    value = step.get("endConditionValue")
    if condition == "distance" and value:
        metres = float(value)
        return f"{metres / 1000:g} km" if metres >= 1000 else f"{metres:g} m"
    if condition == "time" and value:
        seconds = int(float(value))
        if seconds % 60 == 0:
            return f"{seconds // 60} min"
        return f"{seconds // 60}:{seconds % 60:02d} min"
    if condition == "lap.button":
        return "fino al giro (lap)"
    return condition or "durata libera"


def _target(step: dict[str, Any], warnings: list[str]) -> str:
    target = ((step.get("targetType") or {}).get("workoutTargetTypeKey") or "").lower()
    one, two = step.get("targetValueOne"), step.get("targetValueTwo")
    zone = step.get("zoneNumber")

    if target in ("pace.zone", "speed.zone") and one and two:
        paces = sorted(1000.0 / float(v) for v in (one, two) if float(v) > 0)
        if len(paces) == 2 and all(
            _PLAUSIBLE_PACE_S[0] <= p <= _PLAUSIBLE_PACE_S[1] for p in paces
        ):
            return f" @ {_mmss(paces[0])}–{_mmss(paces[1])}/km"
        # Never a plausible wrong number: show what Garmin sent and say so.
        warnings.append(
            f"Target di passo con valori inattesi ({one}, {two}): mostrati grezzi."
        )
        return f" @ target {target} {one}–{two} (valori grezzi)"
    if target == "heart.rate.zone":
        if zone:
            return f" @ FC zona {zone}"
        if one and two:
            return f" @ FC {int(float(one))}–{int(float(two))} bpm"
    if target == "cadence" and one and two:
        return f" @ cadenza {int(float(one))}–{int(float(two))}"
    if target == "power.zone" and one and two:
        return f" @ potenza {int(float(one))}–{int(float(two))} W"
    return ""


def _mmss(seconds: float) -> str:
    minutes, rest = divmod(int(round(seconds)), 60)
    return f"{minutes}:{rest:02d}"


def default_window(today: date | None = None) -> tuple[date, date]:
    """Last week (to compare with what was run) and the next two."""
    today = today or date.today()
    return today - timedelta(days=7), today + timedelta(days=13)
