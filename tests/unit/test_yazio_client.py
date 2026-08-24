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


@pytest.fixture(autouse=True)
def _client_identity(monkeypatch):
    """Yazio's app-level client pair, which login() now requires.

    Placeholders: every request here is injected, so these only need to exist.
    """
    from app.config import get_settings

    monkeypatch.setenv("YAZIO_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("YAZIO_CLIENT_SECRET", "test-client-secret")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _responder(payload, *, capture: list | None = None):
    def _request(method, url, *, data=None, json=None, params=None, token=None):
        if capture is not None:
            # `body` is whichever encoding was used: the token endpoint is
            # tried as JSON first, everything else sends plain params.
            capture.append({"method": method, "url": url, "body": json or data,
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
    assert calls[0]["body"]["grant_type"] == "password"
    assert calls[0]["body"]["username"] == "me@example.com"


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
    assert calls[0]["body"]["grant_type"] == "refresh_token"
    assert "password" not in calls[0]["body"]


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


def test_fetchDay_whenApiFails_raises():
    """A failed call must not masquerade as an empty day.

    They used to collapse into the same None, so an import where every request
    was rejected reported "90 giorni vuoti" — identical to a genuinely empty
    diary, and impossible to tell apart from outside.
    """
    request = _responder(RuntimeError("503"))

    with pytest.raises(RuntimeError):
        yazio.fetch_day("acc", "2026-06-22", request=request)


def test_fetchDay_withNothingLogged_returnsNone():
    """An unlogged day is still None — that part was right."""
    assert yazio.fetch_day("acc", "2026-06-22", request=_responder({})) is None


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


# ── encoding negotiation / error surfacing ───────────────────────────────────


def _http(status: int, body: str = ""):
    from app.collection.yazio import YazioHTTPError

    return YazioHTTPError(status, body)


def _encoding_recorder(fail_on: set[str]):
    """Fake token endpoint that rejects the encodings named in ``fail_on``."""
    seen: list[str] = []

    def _request(method, url, *, data=None, json=None, params=None, token=None):
        encoding = "json" if json is not None else "form"
        seen.append(encoding)
        if encoding in fail_on:
            raise _http(400, '{"error":"invalid_request"}')
        return {"access_token": "acc", "refresh_token": "ref", "expires_in": 3600}

    _request.seen = seen  # type: ignore[attr-defined]
    return _request


def test_login_triesJsonFirst():
    """v15 is a JSON API; form encoding is only the fallback."""
    request = _encoding_recorder(fail_on=set())

    yazio.login("me@example.com", "pw", request=request)

    assert request.seen == ["json"]  # type: ignore[attr-defined]


def test_login_whenJsonIsRejected_retriesAsForm():
    """A bare 400 means "I couldn't read this" — worth trying the other encoding."""
    request = _encoding_recorder(fail_on={"json"})

    tokens = yazio.login("me@example.com", "pw", request=request)

    assert tokens["access_token"] == "acc"
    assert request.seen == ["json", "form"]  # type: ignore[attr-defined]


def test_login_on401_doesNotRetry():
    """401 is a real answer: the password is wrong, and re-encoding hides it."""
    seen: list[str] = []

    def _request(method, url, *, data=None, json=None, params=None, token=None):
        seen.append("json" if json is not None else "form")
        raise _http(401, '{"error":"invalid_grant"}')

    with pytest.raises(CollectionError) as err:
        yazio.login("me@example.com", "wrong", request=_request)

    assert seen == ["json"]
    assert "invalid_grant" in str(err.value)


def test_login_errorCarriesTheServerBody():
    """The body is where the server says *why*; a bare status code is useless."""

    def _request(method, url, *, data=None, json=None, params=None, token=None):
        raise _http(400, '{"error":"invalid_client","error_description":"unknown"}')

    with pytest.raises(CollectionError) as err:
        yazio.login("me@example.com", "pw", request=_request)

    assert "invalid_client" in str(err.value)


def test_login_errorNeverLeaksThePassword():
    """The message goes to logs and to a terminal someone may screenshot."""

    def _request(method, url, *, data=None, json=None, params=None, token=None):
        # Worst case: a server that echoes the request back in its error.
        raise _http(400, str(json or data))

    with pytest.raises(CollectionError) as err:
        yazio.login("me@example.com", "sup3r-s3cret", request=_request)

    assert "sup3r-s3cret" not in str(err.value)


# ── daily-summary shape ──────────────────────────────────────────────────────


def test_fetchDay_usesTheAggregatedEndpoint():
    """/user/consumed-items returns the individual meals; we want the totals."""
    calls: list = []
    request = _responder({"energy": 2000}, capture=calls)

    yazio.fetch_day("acc", "2026-06-22", request=request)

    assert calls[0]["url"].endswith("/user/widgets/daily-summary")


def test_parseDay_readsYazioDottedKeys():
    """Yazio's keys contain literal dots: {"nutrient.protein": 120} is ONE key.

    Traversing on the dot would look for a "nutrient" object that isn't there
    and report a fully logged day as empty.
    """
    parsed = yazio.parse_day(
        {
            "nutrients": {
                "energy.energy": 2450.0,
                "nutrient.protein": 120.4,
                "nutrient.carb": 300.2,
                "nutrient.fat": 70.1,
            }
        },
        "2026-06-22",
    )

    assert parsed is not None
    assert parsed["energy_kcal"] == 2450.0
    assert parsed["protein_g"] == 120.4
    assert parsed["carbs_g"] == 300.2
    assert parsed["fat_g"] == 70.1


def test_parseDay_stillReadsGenuinelyNestedKeys():
    """The nested variant must keep working — the literal key is tried first."""
    parsed = yazio.parse_day({"energy": {"energy": 2000}}, "2026-06-22")

    assert parsed is not None
    assert parsed["energy_kcal"] == 2000.0


# ── client identity ──────────────────────────────────────────────────────────


def test_clientIdentity_comesFromSettings(monkeypatch):
    """Yazio rotates the app-level pair; a rotation must not need a deploy."""
    from app.config import get_settings

    monkeypatch.setenv("YAZIO_CLIENT_ID", "id-from-secret")
    monkeypatch.setenv("YAZIO_CLIENT_SECRET", "secret-from-secret")
    get_settings.cache_clear()
    calls: list = []
    request = _responder(
        {"access_token": "a", "refresh_token": "r", "expires_in": 60}, capture=calls
    )

    yazio.login("me@example.com", "pw", request=request)

    assert calls[0]["body"]["client_id"] == "id-from-secret"
    assert calls[0]["body"]["client_secret"] == "secret-from-secret"
    get_settings.cache_clear()


def test_invalidClientError_isSurfacedVerbatim():
    """"Invalid client" means the app-level pair, not the user's password —
    and only the server's own wording makes that distinction visible."""

    def _request(method, url, *, data=None, json=None, params=None, token=None):
        raise _http(400, '[{"property_path":"","message":"Invalid client"}]')

    with pytest.raises(CollectionError) as err:
        yazio.login("me@example.com", "pw", request=_request)

    assert "Invalid client" in str(err.value)


def test_missingClientIdentity_failsWithTheFixInTheMessage(monkeypatch):
    """If the pair is ever blanked — a future rotation, say — say which one it is.

    Sending empty strings would earn "Invalid client" from Yazio: the exact
    message a *stale* pair produces, for a completely different cause.
    """
    from app.config import get_settings

    monkeypatch.setenv("YAZIO_CLIENT_ID", "")
    monkeypatch.setenv("YAZIO_CLIENT_SECRET", "")
    monkeypatch.setattr(yazio, "_DEFAULT_CLIENT_ID", "")
    monkeypatch.setattr(yazio, "_DEFAULT_CLIENT_SECRET", "")
    get_settings.cache_clear()

    with pytest.raises(CollectionError) as err:
        yazio.login("me@example.com", "pw", request=_responder({}))

    assert "YAZIO_CLIENT_ID" in str(err.value)
    get_settings.cache_clear()


def test_defaultClientIdentity_isPresent(monkeypatch):
    """Without a secret set, the built-in pair must still work.

    The empty-default version of this shipped once and turned every login into
    "Invalid client" — the same message a *stale* pair produces, which is the
    hard-to-diagnose one.
    """
    from app.config import get_settings

    monkeypatch.delenv("YAZIO_CLIENT_ID", raising=False)
    monkeypatch.delenv("YAZIO_CLIENT_SECRET", raising=False)
    get_settings.cache_clear()

    client_id, client_secret = yazio._client_identity()

    assert client_id.startswith("1_")
    assert len(client_secret) > 20
    get_settings.cache_clear()
