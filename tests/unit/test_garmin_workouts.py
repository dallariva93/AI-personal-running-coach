"""Unit: turning a planned session into a Garmin workout.

This is the code that decides what appears on a watch and gets **run**, so the
bar is different from the rest of the app: a session that arrives subtly wrong
is not a bad number on a screen, it is an interval workout done at the wrong
pace. Everything here is a pure function, tested exhaustively offline.
"""

from __future__ import annotations

import pytest

from app.collection.garmin_workouts import (
    PACE_TOLERANCE_S,
    WorkoutBuildError,
    build_workout,
    describe_steps,
    pace_to_mps,
)

_INTERVALS = [
    {"kind": "warmup", "distance_km": 2.5, "pace": "5:30/km", "tolerance_s": 25},
    {"kind": "repeat", "times": 6, "steps": [
        {"kind": "interval", "distance_km": 1.0, "pace": "3:45/km", "tolerance_s": 6},
        {"kind": "recovery", "duration_min": 2},
    ]},
    {"kind": "cooldown", "distance_km": 2.0, "pace": "5:30/km", "tolerance_s": 25},
]


def _steps(workout) -> list:
    return workout.to_dict()["workoutSegments"][0]["workoutSteps"]


# ── pace conversion ──────────────────────────────────────────────────────────


def test_paceToMps_converts():
    """Garmin speaks speed, the plan speaks pace: the one silent-error spot."""
    assert pace_to_mps("5:00/km") == pytest.approx(1000 / 300)
    assert pace_to_mps("3:45") == pytest.approx(1000 / 225)


def test_paceToMps_rejectsNonsense():
    for bad in [None, "", "abc", "0:00", "-1:00/km", "5.30"]:
        assert pace_to_mps(bad) is None


# ── structure ────────────────────────────────────────────────────────────────


def test_build_producesWarmupRepeatCooldown():
    steps = _steps(build_workout("Ripetute", _INTERVALS))

    assert [s["stepType"]["stepTypeKey"] for s in steps] == [
        "warmup", "repeat", "cooldown",
    ]
    repeat = steps[1]
    assert repeat["numberOfIterations"] == 6
    assert len(repeat["workoutSteps"]) == 2


def test_build_distanceStepsAreInMetres():
    """km in the plan, metres on the wire — an off-by-1000 here is a 2.5 m warmup."""
    steps = _steps(build_workout("Ripetute", _INTERVALS))

    assert steps[0]["endCondition"]["conditionTypeKey"] == "distance"
    assert steps[0]["endConditionValue"] == 2500.0


def test_build_durationStepsAreInSeconds():
    repeat = _steps(build_workout("Ripetute", _INTERVALS))[1]
    recovery = repeat["workoutSteps"][1]

    assert recovery["endCondition"]["conditionTypeKey"] == "time"
    assert recovery["endConditionValue"] == 120.0


def test_build_stepOrderIsContinuousAcrossRepeats():
    """Garmin numbers every step, children included; a clash breaks the workout."""
    steps = _steps(build_workout("Ripetute", _INTERVALS))
    orders = [steps[0]["stepOrder"], steps[1]["stepOrder"]]
    orders += [c["stepOrder"] for c in steps[1]["workoutSteps"]]
    orders.append(steps[2]["stepOrder"])

    assert orders == sorted(orders)
    assert len(set(orders)) == len(orders)


# ── targets ──────────────────────────────────────────────────────────────────


def test_build_targetsPaceNotSpeed():
    """Garmin reads the numeric id and ignores the key string.

    Pairing id 5 (speed.zone) with the key "pace.zone" produced workouts that
    showed km/h on the watch: the numbers sent are the same either way, so
    nothing looked broken until the athlete was standing there reading speed.
    """
    step = _steps(build_workout("X", [{"kind": "interval", "distance_km": 1,
                                       "pace": "4:00/km"}]))[0]

    assert step["targetType"] == {
        "workoutTargetTypeId": 6,  # confirmed by reading a workout back
        "workoutTargetTypeKey": "pace.zone",
    }


def test_build_paceTargetIdIsConfigurable(monkeypatch):
    """A vendor taxonomy we cannot query from here: a secret, not a deploy."""
    from app.config import get_settings

    monkeypatch.setenv("GARMIN_PACE_TARGET_ID", "7")
    get_settings.cache_clear()
    try:
        step = _steps(build_workout("X", [{"kind": "interval", "distance_km": 1,
                                           "pace": "4:00/km"}]))[0]
        assert step["targetType"]["workoutTargetTypeId"] == 7
    finally:
        get_settings.cache_clear()


def test_build_paceBecomesARange_notAPoint():
    """A watch alerting on an exact figure beeps the whole session."""
    steps = _steps(build_workout("Ripetute", _INTERVALS))
    work = steps[1]["workoutSteps"][0]

    assert work["targetType"]["workoutTargetTypeKey"] == "pace.zone"
    slow, fast = work["targetValueOne"], work["targetValueTwo"]
    assert slow < fast
    # The window is the prescribed pace ± this step's own tolerance, as speed.
    assert slow == pytest.approx(1000 / (225 + 6), rel=1e-3)
    assert fast == pytest.approx(1000 / (225 - 6), rel=1e-3)


def test_build_toleranceIsPerStep_notOnePolicyForEverything():
    """A repetition wants precision; the warmup around it does not.

    One fixed width cannot serve both: ±8 s is sensible on a 1 km rep and far
    too tight on easy running, where it makes the watch complain at every rise —
    which teaches the athlete to ignore the alert, including when it matters.
    """
    steps = _steps(build_workout("Ripetute", _INTERVALS))
    warmup = steps[0]
    rep = steps[1]["workoutSteps"][0]

    def _width(step):
        return 1000 / step["targetValueOne"] - 1000 / step["targetValueTwo"]

    assert _width(warmup) == pytest.approx(50, abs=1)  # ±25 s
    assert _width(rep) == pytest.approx(12, abs=1)  # ±6 s
    assert _width(warmup) > _width(rep)


def test_build_withoutTolerance_usesTheDefault():
    step = _steps(build_workout("X", [{"kind": "interval", "distance_km": 1,
                                       "pace": "5:00/km"}]))[0]

    assert step["targetValueOne"] == pytest.approx(
        1000 / (300 + PACE_TOLERANCE_S), rel=1e-3
    )


def test_build_malformedTolerance_fallsBackInsteadOfCrashing():
    for bad in ["molto", None, -5]:
        step = _steps(build_workout("X", [{"kind": "interval", "distance_km": 1,
                                           "pace": "5:00/km", "tolerance_s": bad}]))[0]
        assert step["targetValueOne"] > 0


def test_build_noPaceMeansNoTarget_notAGuess():
    """A recovery jog has no prescribed pace; inventing one would be worse."""
    recovery = _steps(build_workout("Ripetute", _INTERVALS))[1]["workoutSteps"][1]

    assert recovery["targetType"]["workoutTargetTypeKey"] == "no.target"
    assert "targetValueOne" not in recovery


def test_build_stepWithoutExtentEndsOnTheLapButton():
    """Neither distance nor time given: end on the lap press, never a made-up length."""
    step = _steps(build_workout("Libero", [{"kind": "interval"}]))[0]

    assert step["endCondition"]["conditionTypeKey"] == "lap.button"
    assert step.get("endConditionValue") is None


# ── refusals ─────────────────────────────────────────────────────────────────


def test_build_withoutSteps_refuses():
    """No structure means no workout — never a plausible default one."""
    with pytest.raises(WorkoutBuildError):
        build_workout("Vuoto", [])


def test_build_repeatWithoutIterations_refuses():
    with pytest.raises(WorkoutBuildError):
        build_workout("Rotto", [{"kind": "repeat", "steps": [{"distance_km": 1}]}])


def test_build_repeatWithoutChildren_refuses():
    with pytest.raises(WorkoutBuildError):
        build_workout("Rotto", [{"kind": "repeat", "times": 4, "steps": []}])


def test_build_malformedStep_refuses():
    with pytest.raises(WorkoutBuildError):
        build_workout("Rotto", ["non un dict"])


# ── the preview the athlete confirms against ─────────────────────────────────


def test_describe_matchesWhatIsBuilt():
    """The preview is what gets approved: it must read the same structure."""
    lines = describe_steps(_INTERVALS)

    assert lines[0].startswith("riscaldamento 2.5 km @")
    assert lines[1].startswith("6× (")
    assert "1 km @" in lines[1]
    assert "recupero 2 min (a sensazione)" in lines[1]
    assert lines[2].startswith("defaticamento 2 km @")


def test_describe_showsThePaceWindow():
    """The athlete sees the range the watch will actually enforce."""
    line = describe_steps([{"kind": "interval", "distance_km": 1, "pace": "3:45/km"}])[0]

    assert "3:37–3:53/km" in line


def test_describe_showsTheStepsOwnWindow():
    """The preview must show the real width, not the default one."""
    line = describe_steps(
        [{"kind": "interval", "distance_km": 8, "pace": "5:30/km", "tolerance_s": 25}]
    )[0]

    assert "5:05–5:55/km" in line


def test_describe_emptyIsEmpty():
    assert describe_steps(None) == []
    assert describe_steps([]) == []
