"""Translate a planned session into a Garmin Connect workout.

Pure translation: no I/O, no network, no database — the same rule the
``processing`` modules follow. That matters more here than usual, because this
is the code deciding what appears on a watch and gets run for real, so it has to
be exhaustively testable offline.

The input is our own neutral step format, which the periodization engine emits
alongside the description::

    [{"kind": "warmup", "distance_km": 2.5, "pace": "5:30/km"},
     {"kind": "repeat", "times": 6, "steps": [
         {"kind": "interval", "distance_km": 1.0, "pace": "3:45/km"},
         {"kind": "recovery", "duration_min": 2}]},
     {"kind": "cooldown", "distance_km": 2.0, "pace": "5:30/km"}]

Paces become a *range*, never a single value: a watch alerting on an exact
figure beeps continuously, and the target is a zone anyway.
"""

from __future__ import annotations

from typing import Any

from app.logging_config import get_logger

logger = get_logger("app.collection.garmin_workouts")

# Garmin's own ids. They are part of the wire format, not something we choose.
_SPORT_RUNNING = {"sportTypeId": 1, "sportTypeKey": "running"}
_STEP_TYPES = {
    "warmup": {"stepTypeId": 1, "stepTypeKey": "warmup"},
    "cooldown": {"stepTypeId": 2, "stepTypeKey": "cooldown"},
    "interval": {"stepTypeId": 3, "stepTypeKey": "interval"},
    "recovery": {"stepTypeId": 4, "stepTypeKey": "recovery"},
    "rest": {"stepTypeId": 5, "stepTypeKey": "rest"},
    "repeat": {"stepTypeId": 6, "stepTypeKey": "repeat"},
}
_END_DISTANCE = {"conditionTypeId": 3, "conditionTypeKey": "distance"}
_END_TIME = {"conditionTypeId": 2, "conditionTypeKey": "time"}
_END_ITERATIONS = {"conditionTypeId": 7, "conditionTypeKey": "iterations"}
_END_LAP_BUTTON = {"conditionTypeId": 1, "conditionTypeKey": "lap.button"}
_TARGET_SPEED = {"workoutTargetTypeId": 5, "workoutTargetTypeKey": "pace.zone"}
_TARGET_NONE = {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target"}

# How wide the pace window around the prescribed pace is, in seconds per km.
# Tight enough to still mean something, loose enough that a hill or a corner
# does not set the watch beeping.
PACE_TOLERANCE_S = 8


class WorkoutBuildError(ValueError):
    """The session cannot be expressed as a workout. Never guessed around."""


def pace_to_mps(pace: str | None) -> float | None:
    """"5:30/km" → metres per second. ``None`` when unparseable.

    Garmin speaks speed, the plan speaks pace, and the conversion is the one
    place a silent mistake would put a wrong target on the watch.
    """
    if not pace:
        return None
    text = str(pace).replace("/km", "").strip()
    try:
        minutes, seconds = text.split(":")
        total_s = int(minutes) * 60 + int(seconds)
    except (ValueError, AttributeError):
        return None
    if total_s <= 0:
        return None
    return 1000.0 / total_s


def _speed_range(pace: str | None) -> tuple[float, float] | None:
    """A (slow, fast) speed window in m/s around ``pace``."""
    seconds = _pace_seconds(pace)
    if seconds is None:
        return None
    slow = 1000.0 / (seconds + PACE_TOLERANCE_S)
    fast = 1000.0 / max(1, seconds - PACE_TOLERANCE_S)
    return round(slow, 3), round(fast, 3)


def _pace_seconds(pace: str | None) -> int | None:
    if not pace:
        return None
    text = str(pace).replace("/km", "").strip()
    try:
        minutes, seconds = text.split(":")
        total = int(minutes) * 60 + int(seconds)
    except (ValueError, AttributeError):
        return None
    return total if total > 0 else None


def _executable(kind: str, order: int, step: dict[str, Any]) -> Any:
    """One concrete step: how it ends, and what to aim for while it lasts."""
    from garminconnect.workout import ExecutableStep

    distance_km = step.get("distance_km")
    duration_min = step.get("duration_min")

    if distance_km:
        end, value = _END_DISTANCE, float(distance_km) * 1000.0
    elif duration_min:
        end, value = _END_TIME, float(duration_min) * 60.0
    else:
        # Neither given: end on the lap button rather than inventing a length.
        end, value = _END_LAP_BUTTON, None

    fields: dict[str, Any] = {
        "stepOrder": order,
        "stepType": _STEP_TYPES.get(kind, _STEP_TYPES["interval"]),
        "endCondition": end,
        "endConditionValue": value,
    }

    speeds = _speed_range(step.get("pace"))
    if speeds:
        fields["targetType"] = _TARGET_SPEED
        fields["targetValueOne"] = speeds[0]
        fields["targetValueTwo"] = speeds[1]
    else:
        # No pace given is a deliberate "run this by feel" (a stride, a
        # recovery jog), not a gap to fill with a guess.
        fields["targetType"] = _TARGET_NONE

    return ExecutableStep(**fields)


def _repeat(step: dict[str, Any], order: int) -> Any:
    from garminconnect.workout import RepeatGroup

    children = step.get("steps") or []
    if not children:
        raise WorkoutBuildError("Un blocco 'repeat' senza step interni.")
    times = int(step.get("times") or 0)
    if times < 1:
        raise WorkoutBuildError("Un blocco 'repeat' senza numero di ripetizioni.")

    inner = [
        _executable(child.get("kind", "interval"), order + 1 + i, child)
        for i, child in enumerate(children)
    ]
    return RepeatGroup(
        stepOrder=order,
        stepType=_STEP_TYPES["repeat"],
        numberOfIterations=times,
        workoutSteps=inner,
        endCondition=_END_ITERATIONS,
        endConditionValue=float(times),
    )


def build_workout(name: str, steps: list[dict[str, Any]], *, duration_min: float | None = None):
    """Build a ``RunningWorkout`` from our neutral step list.

    Raises :class:`WorkoutBuildError` when the session cannot be expressed —
    which is the right outcome: a workout that reaches the watch subtly wrong is
    worse than one that never gets there, because the athlete runs it.
    """
    from garminconnect.workout import RunningWorkout, WorkoutSegment

    if not steps:
        raise WorkoutBuildError("Nessuno step: la seduta non ha una struttura.")

    built: list[Any] = []
    order = 1
    for step in steps:
        if not isinstance(step, dict):
            raise WorkoutBuildError(f"Step non valido: {step!r}")
        kind = str(step.get("kind") or "interval")
        if kind == "repeat":
            group = _repeat(step, order)
            built.append(group)
            # A repeat consumes its own order plus one per child step.
            order += 1 + len(group.workoutSteps)
        else:
            built.append(_executable(kind, order, step))
            order += 1

    fields: dict[str, Any] = {
        "workoutName": name[:80],
        "workoutSegments": [
            WorkoutSegment(segmentOrder=1, sportType=_SPORT_RUNNING, workoutSteps=built)
        ],
    }
    # Garmin requires an estimate. Zero would be a claim, so when the plan has
    # no duration we derive one from the steps — it only drives the figure shown
    # next to the workout name, never what the watch enforces.
    fields["estimatedDurationInSecs"] = (
        int(duration_min * 60) if duration_min else estimate_seconds(steps)
    )
    return RunningWorkout(**fields)


# Used only to estimate a duration for display, when a distance step carries no
# pace of its own. Never used as a target.
_FALLBACK_PACE_S = 360


def estimate_seconds(steps: list[dict[str, Any]] | None) -> int:
    """Roughly how long the session takes, from its own structure."""
    total = 0.0
    for step in steps or []:
        if not isinstance(step, dict):
            continue
        if step.get("kind") == "repeat":
            total += int(step.get("times") or 0) * estimate_seconds(step.get("steps"))
            continue
        if step.get("duration_min"):
            total += float(step["duration_min"]) * 60
        elif step.get("distance_km"):
            pace = _pace_seconds(step.get("pace")) or _FALLBACK_PACE_S
            total += float(step["distance_km"]) * pace
    return int(total)


def describe_steps(steps: list[dict[str, Any]] | None) -> list[str]:
    """A human-readable rendering of what would land on the watch.

    This is what the athlete confirms against, so it is deliberately built from
    the *same* structure the workout is built from: if the two ever disagreed,
    the preview would be reassuring and wrong.
    """
    if not steps:
        return []
    out: list[str] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        kind = str(step.get("kind") or "interval")
        if kind == "repeat":
            inner = "; ".join(describe_steps(step.get("steps") or []))
            out.append(f"{int(step.get('times') or 0)}× ({inner})")
        else:
            out.append(f"{_LABELS.get(kind, kind)} {_extent(step)}{_target(step)}")
    return out


_LABELS = {
    "warmup": "riscaldamento",
    "cooldown": "defaticamento",
    "interval": "corsa",
    "recovery": "recupero",
    "rest": "pausa",
}


def _extent(step: dict[str, Any]) -> str:
    if step.get("distance_km"):
        return f"{float(step['distance_km']):g} km"
    if step.get("duration_min"):
        return f"{float(step['duration_min']):g} min"
    return "fino al giro (lap)"


def _target(step: dict[str, Any]) -> str:
    seconds = _pace_seconds(step.get("pace"))
    if seconds is None:
        return " (a sensazione)"
    return f" @ {_mmss(seconds - PACE_TOLERANCE_S)}–{_mmss(seconds + PACE_TOLERANCE_S)}/km"


def _mmss(seconds: int) -> str:
    minutes, rest = divmod(max(1, int(seconds)), 60)
    return f"{minutes}:{rest:02d}"
