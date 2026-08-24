"""Unit: the Yazio client.

Yazio has no public API contract — the endpoints are reverse-engineered and can
change without notice. So the property worth testing is not "does it parse the
happy path", it is **what happens when the shape changes**: a renamed field must
produce a missing value, never a wrong one. A day silently parsed as 0 kcal
would tell the coach the athlete ate nothing, which is a far more dangerous
answer than "no data".

Every test injects its own ``request``: nothing here touches the network.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.collection import yazio
from app.exceptions import CollectionError


def _responder(payload, *, capture: list | None = None):
    def _request(method, url, *, data=None, params=None, token=None):
        if capture is not None:
            capture.append({"method": method, "url": url, "data": data,
                            "params": params, "token": token})
        if isinstance(payload, Exception):
            raise payload
        return payload

    return _request


# ── login / refresh ──────────────────────────────────────────────────────────


def test_login_returnsTokenPair_andSendsPasswordGrant():
    calls: list = []
    request = _responder(
        {"access_token": "acc", "refresh_token": "ref", "expires_in": 3600},
        capture=calls,
    )

    tokens = yazio.login("me@example.com", "hunter2", request=request)

    assert tokens == {"access_token": "acc", "refresh_token": "ref", "expires_in": 3600}
    assert calls[0]["method"] == "POST"
    assert calls[0]["data"]["grant_type"] == "password"
    assert calls[0]["data"]["username"] == "me@example.com"


def test_login_withBadCredentials_raises():
    """The one Yazio call that must fail loudly: someone is waiting for it."""
    request = _responder(RuntimeError("401 Unauthorized"))

    with pytest.raises(CollectionError):
        yazio.login("me@example.com", "wrong", request=request)


def test_login_withoutAccessToken_raises():
    """A 200 with an unexpected body is still a failed login."""
    with pytest.raises(CollectionError):
        yazio.login("me@example.com", "pw", request=_responder({"ok": True}))


def test_refresh_usesRefreshGrant_andNeverThePassword():
    calls: list = []
    request = _responder(
        {"access_token": "acc2", "refresh_token": "ref2", "expires_in": 7200},
        capture=calls,
    )

    tokens = yazio.refresh("ref", request=request)

    assert tokens["access_token"] == "acc2"
    assert calls[0]["data"]["grant_type"] == "refresh_token"
    assert "password" not in calls[0]["data"]


def test_refresh_withoutNewRefreshToken_returnsNone():
    """Some refreshes reuse the old token; the caller must keep the previous one."""
    request = _responder({"access_token": "acc2", "expires_in": 3600})

    assert yazio.refresh("ref", request=request)["refresh_token"] is None


# ── fetch / parse ────────────────────────────────────────────────────────────


def test_fetchDay_returnsTotals_andPassesTheDate():
    calls: list = []
    request = _responder(
        {"energy": 2450, "protein": 120.4, "carb": 300.2, "fat": 70.1},
        capture=calls,
    )

    day = yazio.fetch_day("acc", date(2026, 6, 22), request=request)

    assert day == {
        "date": "2026-06-22",
        "energy_kcal": 2450.0,
        "protein_g": 120.4,
        "carbs_g": 300.2,
        "fat_g": 70.1,
        "water_ml": None,
    }
    assert calls[0]["params"] == {"date": "2026-06-22"}
    assert calls[0]["token"] == "acc"


def test_fetchDay_whenApiFails_returnsNone():
    """One unreachable day is a gap in the diary, not an error to propagate."""
    request = _responder(RuntimeError("503"))

    assert yazio.fetch_day("acc", "2026-06-22", request=request) is None


def test_parseDay_readsNestedTotals():
    """The totals live under a summary key in some payload variants."""
    parsed = yazio.parse_day(
        {"summary": {"energy": 2000, "protein": 100, "carb": 250, "fat": 60}},
        "2026-06-22",
    )

    assert parsed is not None
    assert parsed["energy_kcal"] == 2000.0
    assert parsed["protein_g"] == 100.0


def test_parseDay_withUnknownShape_returnsNone():
    """A renamed schema must read as "no data", never as a day of zero calories."""
    assert yazio.parse_day({"totale_calorie": 2000}, "2026-06-22") is None
    assert yazio.parse_day({}, "2026-06-22") is None
    assert yazio.parse_day(None, "2026-06-22") is None
    assert yazio.parse_day([1, 2, 3], "2026-06-22") is None


def test_parseDay_withPartialData_keepsWhatItHas():
    """A day logged only at breakfast is real data about a partial log."""
    parsed = yazio.parse_day({"energy": 500}, "2026-06-22")

    assert parsed is not None
    assert parsed["energy_kcal"] == 500.0
    assert parsed["protein_g"] is None


def test_parseDay_convertsKilojoules():
    """Yazio returns kJ in some payloads; 10 460 kJ is 2 500 kcal, not 10 460."""
    parsed = yazio.parse_day({"energy": 10460, "protein": 100}, "2026-06-22")

    assert parsed is not None
    assert parsed["energy_kcal"] == pytest.approx(2500, abs=1)


def test_parseDay_doesNotConvertPlausibleKcal():
    """A big-but-real 3 500 kcal day must stay 3 500."""
    parsed = yazio.parse_day({"energy": 3500}, "2026-06-22")

    assert parsed is not None
    assert parsed["energy_kcal"] == 3500.0


def test_parseDay_ignoresNonNumericValues():
    parsed = yazio.parse_day({"energy": "n/d", "protein": 100}, "2026-06-22")

    assert parsed is not None
    assert parsed["energy_kcal"] is None
    assert parsed["protein_g"] == 100.0


def test_parseDay_unknownShape_logsTheFieldsItDidGet(caplog):
    """A silent rename must leave a trail: otherwise it looks like an empty diary.

    Only the keys are logged — what someone ate is not diagnostic data.
    """
    yazio._shape_warned = False  # the warning fires once per process

    with caplog.at_level("WARNING"):
        assert yazio.parse_day({"kilojoule": 8000, "eiweiss": 100}, "2026-06-22") is None

    assert "kilojoule" in caplog.text
    assert "8000" not in caplog.text  # values stay out of the logs


def test_parseDay_unknownShape_warnsOnlyOnce(caplog):
    """A 90-day import must not log the same diagnosis ninety times."""
    yazio._shape_warned = False

    with caplog.at_level("WARNING"):
        for _ in range(5):
            yazio.parse_day({"kilojoule": 8000}, "2026-06-22")

    assert caplog.text.count("non riconosciuto") == 1
