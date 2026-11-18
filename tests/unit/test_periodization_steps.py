"""Unit: the structured steps the engine emits alongside the prose.

The engine has always computed the repetitions, their distance and the recovery
and then spent them on a description string. These tests pin the structure that
now carries the same numbers — it is what reaches the watch.
"""

from __future__ import annotations

from app.processing.periodization import (
    TOL_EASY_S,
    TOL_QUALITY_S,
    _spec_render,
)

_PACES = {"easy": "5:30/km", "long": "5:45/km", "tempo": "4:15/km",
          "intervals": "3:45/km"}


def _render(stype: str, km: float = 12.0, goal: str = "10k") -> dict:
    return _spec_render(stype, 1, km, _PACES, goal)


def test_intervals_carryTheirRepetitionStructure():
    """The numbers that used to exist only inside an Italian sentence."""
    steps = _render("intervals")["steps"]
    repeat = next(s for s in steps if s["kind"] == "repeat")

    assert repeat["times"] == 6
    assert repeat["steps"][0]["distance_km"] == 1.0
    assert repeat["steps"][0]["pace"] == "3:45/km"
    assert repeat["steps"][1]["duration_min"] == 2


def test_intervals_matchTheirOwnDescription():
    """Structure and prose describe the same session, or one of them is lying."""
    spec = _render("intervals")
    repeat = next(s for s in spec["steps"] if s["kind"] == "repeat")

    assert f"{repeat['times']}×" in spec["description"]


def test_qualityIsHeldTighterThanEasyRunning():
    """Easy running is a zone; a repetition is a target."""
    intervals = _render("intervals")["steps"]
    rep = next(s for s in intervals if s["kind"] == "repeat")["steps"][0]
    warmup = next(s for s in intervals if s["kind"] == "warmup")

    assert rep["tolerance_s"] == TOL_QUALITY_S
    assert warmup["tolerance_s"] == TOL_EASY_S
    assert rep["tolerance_s"] < warmup["tolerance_s"]


def test_easyAndLong_areASingleWideStep():
    for stype in ("easy", "long"):
        steps = _render(stype)["steps"]
        assert len(steps) == 1
        assert steps[0]["tolerance_s"] == TOL_EASY_S


def test_recoveryHasNoPace():
    """Run by feel: a target on a recovery jog is noise."""
    repeat = next(s for s in _render("intervals")["steps"] if s["kind"] == "repeat")

    assert "pace" not in repeat["steps"][1]


def test_stridesHaveNoPaceTarget():
    """100 m accelerations cannot be held to a pace window."""
    steps = _render("strides", km=8.0)["steps"]
    repeat = next(s for s in steps if s["kind"] == "repeat")

    assert "pace" not in repeat["steps"][0]


def test_restAndCrossHaveNoSteps():
    """Nothing to put on a watch, and nothing pretending otherwise."""
    for stype in ("rest", "cross", "race"):
        assert _render(stype)["steps"] is None
