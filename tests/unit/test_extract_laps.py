"""Unit: real laps from the Garmin splits payload.

``extract_splits`` flattens the same payload into per-kilometre pace strings,
which erases what an interval session actually is: a 500 m repetition and the
200 m jog after it both disappear into "the third kilometre". These tests pin
the behaviour that keeps a session readable.
"""

from __future__ import annotations

from app.collection.synthesize import extract_laps, extract_splits


def _lap(distance: float, duration: float, intensity: str | None = None, **kw) -> dict:
    lap = {"distance": distance, "duration": duration, **kw}
    if intensity:
        lap["intensityType"] = intensity
    return lap


def _interval_session() -> dict:
    """Warm-up, 3×500 m with 200 m jogs, cool-down — as Garmin sends it."""
    laps = [_lap(2000.0, 660.0, "WARMUP")]
    for _ in range(3):
        laps.append(_lap(500.0, 105.0, "INTERVAL", averageHR=168))
        laps.append(_lap(200.0, 90.0, "RECOVERY", averageHR=140))
    laps.append(_lap(1500.0, 510.0, "COOLDOWN"))
    return {"lapDTOs": laps}


def test_extractLaps_keepsEveryRepetitionAndRecovery():
    laps = extract_laps(_interval_session())

    assert len(laps) == 8  # 1 warm-up + 3 reps + 3 recoveries + 1 cool-down
    reps = [x for x in laps if x.get("role") == "work"]
    recoveries = [x for x in laps if x.get("role") == "recovery"]
    assert len(reps) == 3
    assert len(recoveries) == 3
    assert all(r["distance_m"] == 500 for r in reps)
    assert all(r["distance_m"] == 200 for r in recoveries)


def test_extractLaps_shortRecoveriesSurviveWhereSplitsDropThem():
    """The 200 m jogs are exactly what the per-km view throws away."""
    payload = _interval_session()

    laps = extract_laps(payload)
    splits = extract_splits(payload)

    assert any(x["distance_m"] == 200 for x in laps)
    # extract_splits skips laps under 300 m, so the recoveries are simply gone
    # and what remains carries no distance at all.
    assert len(splits) == 5
    assert all(isinstance(s, str) for s in splits)


def test_extractLaps_computesPacePerLap():
    laps = extract_laps({"lapDTOs": [_lap(500.0, 105.0)]})

    # 105 s over 500 m = 3:30/km
    assert laps[0]["pace"] == "3:30/km"
    assert laps[0]["duration_sec"] == 105


def test_extractLaps_carriesHeartRateAndElevationWhenPresent():
    laps = extract_laps({
        "lapDTOs": [_lap(1000.0, 300.0, averageHR=155, maxHR=170, elevationGain=12.4)]
    })

    assert laps[0]["avg_hr"] == 155
    assert laps[0]["max_hr"] == 170
    assert laps[0]["elevation_gain_m"] == 12


def test_extractLaps_freeRun_leavesRoleUnsetRatherThanGuessing():
    """Without Garmin's own intensity there is nothing to classify.

    Labelling laps "work"/"recovery" from pace alone would be a guess dressed
    up as data — the coach can read the numbers itself.
    """
    laps = extract_laps({"lapDTOs": [_lap(1000.0, 330.0), _lap(1000.0, 325.0)]})

    assert len(laps) == 2
    assert all("role" not in lap for lap in laps)


def test_extractLaps_numbersLapsInOrder():
    laps = extract_laps({"lapDTOs": [_lap(1000.0, 300.0) for _ in range(4)]})

    assert [lap["index"] for lap in laps] == [1, 2, 3, 4]


def test_extractLaps_unknownIntensity_isIgnoredNotInvented():
    laps = extract_laps({"lapDTOs": [_lap(400.0, 90.0, "SOMETHING_NEW")]})

    assert "role" not in laps[0]


def test_extractLaps_partialLap_isKeptWithWhatItHas():
    """A lap with a duration but no distance is still a lap."""
    laps = extract_laps({"lapDTOs": [{"duration": 120.0}]})

    assert laps[0]["duration_sec"] == 120
    assert laps[0]["distance_m"] is None
    assert "pace" not in laps[0]


def test_extractLaps_emptyLapIsSkipped():
    laps = extract_laps({"lapDTOs": [{}, _lap(1000.0, 300.0)]})

    assert len(laps) == 1


def test_extractLaps_malformedPayload_returnsNone():
    assert extract_laps(None) is None
    assert extract_laps({}) is None
    assert extract_laps({"lapDTOs": "non-una-lista"}) is None
    assert extract_laps({"lapDTOs": []}) is None
