"""Unit: reading the coach's prescriptions out of the Garmin calendar.

The calendar is where the athlete's coach puts the week's sessions, so it is
the source of truth for what was *asked*. The properties worth pinning are the
ones that would otherwise fail quietly: a workout in only one of Garmin's two
calendar views, an item that is not a workout, and a pace target whose units
are not what we assume — which must never come out as a plausible wrong pace.
"""

from __future__ import annotations

from datetime import date

from app.services.garmin_calendar import (
    describe_garmin_workout,
    read_calendar,
)


def _step(order, kind, condition=None, value=None, target=None, one=None, two=None,
          **extra):
    step = {
        "type": "ExecutableStepDTO",
        "stepOrder": order,
        "stepType": {"stepTypeKey": kind},
        "endCondition": {"conditionTypeKey": condition} if condition else None,
        "endConditionValue": value,
        "targetType": {"workoutTargetTypeKey": target or "no.target"},
    }
    if one is not None:
        step["targetValueOne"], step["targetValueTwo"] = one, two
    step.update(extra)
    return step


# The shape Garmin returned when a pace-targeted workout was read back.
FMV = {
    "workoutId": 555,
    "workoutName": "6km FMV (Edited)",
    "description": "Fondo medio: costante, senza strappi",
    "estimatedDistanceInMeters": 8000,
    "workoutSegments": [{
        "workoutSteps": [
            _step(1, "warmup", "distance", 1000.0),
            _step(2, "interval", "distance", 6000.0, "pace.zone",
                  1000 / 290, 1000 / 280),  # 4:40–4:50/km
            _step(3, "cooldown", "lap.button"),
        ],
    }],
}


class FakeCalendar:
    def __init__(self, month=None, by_period=None, fail_period=False):
        self.month = month or {"calendarItems": []}
        self.by_period = by_period or []
        self.fail_period = fail_period
        self.month_calls: list = []

    def get_scheduled_workouts(self, year, month):
        self.month_calls.append((year, month))
        return self.month

    def connectapi(self, path, params=None):
        if self.fail_period:
            raise RuntimeError("404")
        return self.by_period


# ── describing a workout ─────────────────────────────────────────────────────


def test_describe_rendersStepsWithPaceRange():
    out = describe_garmin_workout(FMV)

    assert out["steps"] == [
        "riscaldamento 1 km",
        "corsa 6 km @ 4:40–4:50/km",
        "defaticamento fino al giro (lap)",
    ]
    assert out["estimated_km"] == 8.0


def test_describe_keepsTheCoachsNotes():
    """"6km FMV" means something to the coach; the notes are where it is written."""
    assert describe_garmin_workout(FMV)["notes"] == "Fondo medio: costante, senza strappi"


def test_describe_readsRepeatsAndStepNotes():
    workout = {"workoutSegments": [{"workoutSteps": [{
        "type": "RepeatGroupDTO",
        "stepOrder": 1,
        "stepType": {"stepTypeKey": "repeat"},
        "numberOfIterations": 5,
        "workoutSteps": [
            _step(2, "interval", "distance", 400.0, "pace.zone", 1000 / 215, 1000 / 205,
                  description="in progressione"),
            _step(3, "recovery", "time", 90.0),
        ],
    }]}]}

    assert describe_garmin_workout(workout)["steps"] == [
        "5× (corsa 400 m @ 3:25–3:35/km — in progressione; recupero 1:30 min)"
    ]


def test_describe_readsHeartRateTargets():
    workout = {"workoutSegments": [{"workoutSteps": [
        _step(1, "interval", "time", 2400.0, "heart.rate.zone", zoneNumber=2),
        _step(2, "interval", "time", 600.0, "heart.rate.zone", 150, 160),
    ]}]}

    assert describe_garmin_workout(workout)["steps"] == [
        "corsa 40 min @ FC zona 2",
        "corsa 10 min @ FC 150–160 bpm",
    ]


def test_describe_implausiblePace_isShownRawAndFlagged():
    """If the units are not what we assume, say so — never a plausible wrong pace."""
    workout = {"workoutSegments": [{"workoutSteps": [
        _step(1, "interval", "distance", 1000.0, "pace.zone", 280, 290),
    ]}]}

    out = describe_garmin_workout(workout)

    assert "valori grezzi" in out["steps"][0]
    assert out["warnings"]


def test_describe_speedTargetIsShownAsPace():
    """Workouts sent before the target-type fix carry speed.zone; still a run."""
    workout = {"workoutSegments": [{"workoutSteps": [
        _step(1, "interval", "distance", 1000.0, "speed.zone", 1000 / 300, 1000 / 290),
    ]}]}

    assert describe_garmin_workout(workout)["steps"] == ["corsa 1 km @ 4:50–5:00/km"]


def test_describe_unreadable_saysSo():
    assert describe_garmin_workout(None)["warnings"]


# ── reading the calendar ─────────────────────────────────────────────────────


def test_read_keepsOnlyWorkoutsInRange():
    client = FakeCalendar(month={"calendarItems": [
        {"itemType": "workout", "title": "6km FMV (Edited)", "date": "2026-11-12",
         "workoutId": 555},
        {"itemType": "activity", "title": "Corsa", "date": "2026-11-10"},
        {"itemType": "workout", "title": "Fuori range", "date": "2026-11-30",
         "workoutId": 9},
    ]})

    out = read_calendar(client, date(2026, 11, 9), date(2026, 11, 15))

    assert [i["title"] for i in out["items"]] == ["6km FMV (Edited)"]
    assert out["items"][0]["workout_id"] == "555"


def test_read_mergesBothViews_withoutDuplicates():
    """A coach workout may sit in one view, the other, or both."""
    client = FakeCalendar(
        month={"calendarItems": [
            {"itemType": "workout", "title": "6km FMV", "date": "2026-11-12",
             "workoutId": 555},
        ]},
        by_period=[
            {"date": "2026-11-12", "workout": {"workoutId": 555, "workoutName": "6km FMV"}},
            {"date": "2026-11-14", "workout": {"workoutId": 777, "workoutName": "Lungo",
                                               "workoutSegments": [{"workoutSteps": []}]}},
        ],
    )

    out = read_calendar(client, date(2026, 11, 9), date(2026, 11, 15))

    assert [(i["date"].isoformat(), i["title"]) for i in out["items"]] == [
        ("2026-11-12", "6km FMV"),
        ("2026-11-14", "Lungo"),
    ]
    # The by-period view carried the whole workout: no second fetch needed.
    assert out["items"][1]["_workout"] is not None


def test_read_spansMonths():
    client = FakeCalendar()

    read_calendar(client, date(2026, 11, 25), date(2026, 12, 5))

    assert client.month_calls == [(2026, 11), (2026, 12)]


def test_read_oneViewFailing_keepsTheOther():
    client = FakeCalendar(
        month={"calendarItems": [
            {"itemType": "workout", "title": "6km FMV", "date": "2026-11-12",
             "workoutId": 555},
        ]},
        fail_period=True,
    )

    out = read_calendar(client, date(2026, 11, 9), date(2026, 11, 15))

    assert len(out["items"]) == 1
    assert out["errors"]
