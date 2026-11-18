"""Unit: forecast windows for the next runs (SPEC get_run_windows).

One test group per acceptance criterion. Everything runs on static fixtures and
an injected clock: no network, no real time.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.collection.run_windows import (
    RunWindowsError,
    evaluate,
    fetch_hourly,
    run_windows,
)

ROME = ZoneInfo("Europe/Rome")
WED = date(2026, 11, 18)
SUN = date(2026, 11, 22)


def _raw(*days: date, wet: dict | None = None) -> dict:
    """Hourly payload as Open-Meteo returns it, dry by default.

    ``wet`` maps "YYYY-MM-DDTHH:00" to overrides, e.g. {"mm": 1.0}.
    """
    wet = wet or {}
    hourly: dict[str, list] = {
        "time": [], "precipitation": [], "precipitation_probability": [],
        "temperature_2m": [], "wind_gusts_10m": [],
    }
    for day in days:
        for h in range(24):
            stamp = f"{day.isoformat()}T{h:02d}:00"
            row = {"mm": 0.0, "prob": 0, "temp": 10.0 + h / 10, "gust": 10.0}
            row.update(wet.get(stamp, {}))
            hourly["time"].append(stamp)
            hourly["precipitation"].append(row["mm"])
            hourly["precipitation_probability"].append(row["prob"])
            hourly["temperature_2m"].append(row["temp"])
            hourly["wind_gusts_10m"].append(row["gust"])
    return {"hourly": hourly}


def _at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=ROME)


def _day(result: dict, day: date = WED) -> dict:
    return next(d for d in result["days"] if d["date"] == day.isoformat())


# ── 1. fetch ─────────────────────────────────────────────────────────────────


def test_fetch_asksForPadovaInLocalTime():
    seen: list = []

    def _get(url, params, timeout):
        seen.append((url, params, timeout))
        return _raw(WED, WED + timedelta(days=1))

    raw = fetch_hourly("2026-11-18", "2026-11-19", get=_get)

    url, params, timeout = seen[0]
    assert url == "https://api.open-meteo.com/v1/forecast"
    assert params["timezone"] == "Europe/Rome"
    assert (params["latitude"], params["longitude"]) == (45.4064, 11.8768)
    assert (params["start_date"], params["end_date"]) == ("2026-11-18", "2026-11-19")
    assert "precipitation_probability" in params["hourly"]
    assert timeout == 10.0
    assert len(raw["hourly"]["time"]) == 48
    assert raw["hourly"]["time"][0].startswith("2026-11-18")


def test_fetch_retriesOnce_thenRaises():
    calls: list = []

    def _down(url, params, timeout):
        calls.append(1)
        raise ConnectionError("unreachable")

    with pytest.raises(RunWindowsError):
        fetch_hourly("2026-11-18", "2026-11-19", get=_down)

    assert len(calls) == 2  # first attempt + one retry


def test_fetch_secondAttemptSucceeds():
    calls: list = []

    def _flaky(url, params, timeout):
        calls.append(1)
        if len(calls) == 1:
            raise ConnectionError("blip")
        return _raw(WED)

    assert fetch_hourly("2026-11-18", "2026-11-18", get=_flaky)["hourly"]


# ── 2. hour convention ───────────────────────────────────────────────────────


def test_rainAtTimestamp18_fellBeforeTheEveningWindow():
    """Timestamp 18:00 is the rain of 17–18: the 18–21 run stays dry."""
    raw = _raw(WED, wet={"2026-11-18T18:00": {"mm": 2.0, "prob": 90}})

    assert _day(evaluate(raw, _at(WED, 6)))["evening"]["status"] == "dry"


def test_rainAtTimestamp19_fallsInsideTheEveningWindow():
    raw = _raw(WED, wet={"2026-11-18T19:00": {"mm": 2.0, "prob": 90}})

    assert _day(evaluate(raw, _at(WED, 6)))["evening"]["status"] == "wet"


def test_rainAtTimestamp21_isStillInside_22IsNot():
    inside = _raw(WED, wet={"2026-11-18T21:00": {"mm": 0.5}})
    outside = _raw(WED, wet={"2026-11-18T22:00": {"mm": 0.5}})

    assert _day(evaluate(inside, _at(WED, 6)))["evening"]["status"] == "wet"
    assert _day(evaluate(outside, _at(WED, 6)))["evening"]["status"] == "dry"


# ── 3. thresholds ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("mm", "prob", "expected"),
    [
        (0.0, 45, "uncertain"),
        (0.0, 65, "wet"),
        (0.05, 20, "dry"),
        (0.1, 0, "wet"),  # the threshold itself is not dry
        (0.0, 30, "uncertain"),  # nor is 30 %
        (0.0, 60, "wet"),
    ],
)
def test_thresholds(mm, prob, expected):
    raw = _raw(WED, wet={"2026-11-18T20:00": {"mm": mm, "prob": prob}})

    assert _day(evaluate(raw, _at(WED, 6)))["evening"]["status"] == expected


def test_missingProbability_isNotEvidenceOfDry():
    """A model without probabilities must not turn "unknown" into "dry"."""
    raw = _raw(WED)
    raw["hourly"]["precipitation_probability"] = [None] * 24

    assert _day(evaluate(raw, _at(WED, 6)))["evening"]["status"] == "uncertain"


def test_strongWind_flagged_atTheGustThreshold():
    raw = _raw(WED, wet={"2026-11-18T20:00": {"gust": 40.0}})

    evening = _day(evaluate(raw, _at(WED, 6)))["evening"]
    assert evening["strong_wind"] is True
    assert evening["max_gust_kmh"] == 40


# ── 4. sunday ────────────────────────────────────────────────────────────────


def test_sundayMorningWindow_is7to9():
    morning = _day(evaluate(_raw(SUN), _at(SUN, 6)), SUN)["morning"]

    assert (morning["from"], morning["to"]) == ("07:00", "09:00")


def test_weekdayMorningWindow_is8to10():
    morning = _day(evaluate(_raw(WED), _at(WED, 6)))["morning"]

    assert (morning["from"], morning["to"]) == ("08:00", "10:00")


def test_sundayMorning_isJudgedOnItsOwnHours():
    """Rain at 10:00 (09–10) is outside Sunday's 07–09 window."""
    raw = _raw(SUN, wet={"2026-11-22T10:00": {"mm": 3.0}})

    assert _day(evaluate(raw, _at(SUN, 6)), SUN)["morning"]["status"] == "dry"


# ── 5. best ──────────────────────────────────────────────────────────────────


def test_best_eveningWhenDry():
    assert _day(evaluate(_raw(WED), _at(WED, 6)))["best"] == "evening"


def test_best_morningWhenEveningWet():
    raw = _raw(WED, wet={"2026-11-18T20:00": {"mm": 1.0}})

    assert _day(evaluate(raw, _at(WED, 6)))["best"] == "morning"


def test_best_noneWhenBothWet_withDrySlotsToOffer():
    raw = _raw(WED, wet={
        "2026-11-18T09:00": {"mm": 1.0},
        "2026-11-18T20:00": {"mm": 1.0},
    })

    day = _day(evaluate(raw, _at(WED, 6)))
    assert day["best"] == "none"
    # Wet timestamps 09 and 20 cut the day into 06–08, 09–19 and 20–22.
    assert day["dry_slots"] == ["06:00-08:00", "09:00-19:00", "20:00-22:00"]


def test_best_sundayPrefersTheMorning_whenBothAreDry():
    """On Sunday the order flips: morning first, then evening."""
    assert _day(evaluate(_raw(SUN), _at(SUN, 6)), SUN)["best"] == "morning"


def test_best_sundayFallsBackToTheEvening_whenTheMorningIsWet():
    raw = _raw(SUN, wet={"2026-11-22T08:00": {"mm": 1.0}})

    assert _day(evaluate(raw, _at(SUN, 6)), SUN)["best"] == "evening"


def test_best_sundayAfterTheMorningHasPassed_isTheEvening():
    assert _day(evaluate(_raw(SUN), _at(SUN, 12)), SUN)["best"] == "evening"


def test_drySlots_matchTheSpecExample():
    """Dry timestamps 07..11 only → the slot 06:00-11:00."""
    wet = {f"2026-11-18T{h:02d}:00": {"mm": 1.0} for h in range(12, 23)}

    assert _day(evaluate(_raw(WED, wet=wet), _at(WED, 6)))["dry_slots"] == ["06:00-11:00"]


# ── 6. passed ────────────────────────────────────────────────────────────────


def test_at1930_eveningIsOpen_morningHasPassed():
    day = _day(evaluate(_raw(WED), _at(WED, 19, 30)))

    assert day["evening"]["passed"] is False
    assert day["morning"]["passed"] is True


def test_at1930_aDryPastMorningCannotBeBest():
    raw = _raw(WED, wet={"2026-11-18T20:00": {"mm": 1.0}})

    assert _day(evaluate(raw, _at(WED, 19, 30)))["best"] == "none"


def test_tomorrowIsNeverPassed():
    result = evaluate(_raw(WED, WED + timedelta(days=1)), _at(WED, 23))

    tomorrow = _day(result, WED + timedelta(days=1))
    assert not tomorrow["evening"]["passed"] and not tomorrow["morning"]["passed"]


# ── 7. errors ────────────────────────────────────────────────────────────────


def test_unreachableHost_returnsErrorWithoutRaising():
    def _down(url, params, timeout):
        raise ConnectionError("Name or service not known")

    out = run_windows("2026-11-18", "2026-11-19", get=_down, now=_at(WED, 6))

    assert set(out) == {"error"}
    # Short: no URL, no exception chain — just enough to say why.
    assert out["error"] == "meteo non disponibile: Open-Meteo non raggiungibile"


def test_timeout_isReportedAsSuch():
    import requests

    def _slow(url, params, timeout):
        raise requests.Timeout("read timed out (very long message with the URL)")

    out = run_windows("2026-11-18", "2026-11-19", get=_slow, now=_at(WED, 6))

    assert out["error"] == "meteo non disponibile: timeout dopo 10 s"


@pytest.mark.parametrize(
    ("date_from", "date_to"),
    [("oggi", "2026-11-19"), ("2026-11-19", "2026-11-18"), ("2026-11-18", "2026-11-22")],
)
def test_badDates_returnErrorWithoutCallingTheApi(date_from, date_to):
    def _never(url, params, timeout):
        raise AssertionError("must not be called")

    assert "error" in run_windows(date_from, date_to, get=_never)


def test_fourDays_isAllowed():
    out = run_windows("2026-11-18", "2026-11-21", get=lambda *a: _raw(WED), now=_at(WED, 6))

    assert "error" not in out


def test_malformedPayload_returnsError():
    assert "error" in evaluate({"nope": 1}, _at(WED, 6))
    bad = _raw(WED)
    bad["hourly"]["precipitation"] = [0.0]  # length mismatch
    assert "error" in evaluate(bad, _at(WED, 6))


# ── output shape ─────────────────────────────────────────────────────────────


def test_output_matchesTheSpecShape():
    out = evaluate(_raw(WED), _at(WED, 6, 35))
    day = out["days"][0]

    assert out["location"] == "Padova"
    assert out["source"] == "open-meteo"
    assert out["fetched_at"] == "2026-11-18T06:35:00+01:00"
    assert day["weekday"] == "mercoledì"
    assert set(day["evening"]) == {
        "from", "to", "status", "max_mm", "max_prob", "max_gust_kmh",
        "strong_wind", "passed",
    }
    # hourly limited to 06:00–22:00 to save tokens.
    assert day["hourly"][0]["time"] == "06:00"
    assert day["hourly"][-1]["time"] == "22:00"
    assert set(day["hourly"][0]) == {"time", "mm", "prob", "temp", "gust"}
    assert day["temp_min"] == 10.0
    assert day["temp_max"] == 12.3
