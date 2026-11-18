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
    request = _responder(_summary(), capture=calls)

    day = yazio.fetch_day("acc", date(2026, 8, 20), request=request)

    assert day == {
        "date": "2026-08-20",
        "energy_kcal": 1911.0,
        "energy_goal_kcal": 2784.0,
        "protein_g": 98.1,
        "carbs_g": 119.4,
        "fat_g": 89.4,
        "water_ml": None,
    }
    assert calls[0]["params"] == {"date": "2026-08-20"}
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


def _summary(
    *,
    breakfast: tuple[float, float, float, float] = (360, 9.4, 19.36, 33.08),
    lunch: tuple[float, float, float, float] = (1551, 110, 70, 65),
    dinner: tuple[float, float, float, float] = (0, 0, 0, 0),
    snack: tuple[float, float, float, float] = (0, 0, 0, 0),
    water: float = 0,
    unit_energy: str = "kcal",
) -> dict:
    """A real /user/widgets/daily-summary payload, trimmed to what we read.

    Note `goals`: same key names as the meals, but the day's *targets*. It is
    here on purpose — the tests below check we never read it as intake.
    """

    def _n(t):
        return {
            "nutrients": {
                "energy.energy": t[0],
                "nutrient.carb": t[1],
                "nutrient.fat": t[2],
                "nutrient.protein": t[3],
            }
        }

    return {
        "activity_energy": 1084,
        "steps": 20020,
        "water_intake": water,
        "goals": {
            "energy.energy": 2784,
            "water": 2000,
            "nutrient.protein": 103.66,
            "nutrient.fat": 45.70,
            "nutrient.carb": 207.32,
        },
        "units": {"unit_energy": unit_energy, "unit_mass": "kg"},
        "meals": {
            "breakfast": _n(breakfast),
            "lunch": _n(lunch),
            "dinner": _n(dinner),
            "snack": _n(snack),
        },
    }


def test_parseDay_sumsTheMeals():
    """The summary carries no totals: they are the sum across meals."""
    parsed = yazio.parse_day(_summary(), "2026-08-20")

    assert parsed is not None
    assert parsed["energy_kcal"] == 1911.0  # 360 + 1551
    assert parsed["protein_g"] == 98.1  # 33.08 + 65
    assert parsed["carbs_g"] == 119.4  # 9.4 + 110
    assert parsed["fat_g"] == 89.4  # 19.36 + 70


def test_parseDay_neverReadsGoalsAsIntake():
    """The one that would produce a plausible, wrong number.

    `goals` sits beside the meals with identical key names and holds the day's
    *targets*. Reading it turns "ate 1911" into "ate 2784" — and nothing about
    the result looks broken, which is exactly why it would survive review.
    """
    parsed = yazio.parse_day(_summary(), "2026-08-20")

    assert parsed is not None
    assert parsed["energy_kcal"] != 2784
    assert parsed["protein_g"] != 103.7
    assert parsed["carbs_g"] != 207.3


def test_parseDay_goalsAloneAreNotADay():
    """A payload with targets but no meals must not yield a row of goals."""
    payload = _summary()
    payload.pop("meals")

    assert yazio.parse_day(payload, "2026-08-20") is None


def test_parseDay_allMealsAtZero_isAnUnloggedDay():
    """Zero everywhere means "did not log", not "fasted"."""
    parsed = yazio.parse_day(
        _summary(breakfast=(0, 0, 0, 0), lunch=(0, 0, 0, 0)), "2026-08-20"
    )

    assert parsed is None


def test_parseDay_partialDay_keepsWhatWasLogged():
    """Only breakfast logged is real data about a partial log."""
    parsed = yazio.parse_day(_summary(lunch=(0, 0, 0, 0)), "2026-08-20")

    assert parsed is not None
    assert parsed["energy_kcal"] == 360.0


def test_parseDay_usesTheDeclaredEnergyUnit():
    """The payload states its unit; that beats guessing from magnitude."""
    parsed = yazio.parse_day(
        _summary(breakfast=(4184, 0, 0, 0), lunch=(0, 0, 0, 0), unit_energy="kJ"),
        "2026-08-20",
    )

    assert parsed is not None
    assert parsed["energy_kcal"] == pytest.approx(1000, abs=1)


def test_parseDay_kcalIsNotConvertedEvenWhenLarge():
    """A declared-kcal day stays kcal, however big — no magnitude guessing."""
    parsed = yazio.parse_day(
        _summary(breakfast=(12000, 0, 0, 0), lunch=(0, 0, 0, 0)), "2026-08-20"
    )

    assert parsed is not None
    assert parsed["energy_kcal"] == 12000.0


def test_parseDay_waterZero_isNotStoredAsAMeasurement():
    """The field is always present; 0 is indistinguishable from "not tracked"."""
    assert yazio.parse_day(_summary(water=0), "2026-08-20")["water_ml"] is None
    assert yazio.parse_day(_summary(water=1500), "2026-08-20")["water_ml"] == 1500


def test_parseDay_withUnknownShape_returnsNone():
    """A renamed schema must read as "no data", never as a day of zero calories."""
    assert yazio.parse_day({"totale_calorie": 2000}, "2026-06-22") is None
    assert yazio.parse_day({}, "2026-06-22") is None
    assert yazio.parse_day(None, "2026-06-22") is None
    assert yazio.parse_day([1, 2, 3], "2026-06-22") is None


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


def test_parseDay_readsTheGoalWithoutMixingItIntoIntake():
    """The target comes from `goals`; the intake never does.

    Both are wanted, from adjacent blocks with identical key names — so the test
    pins them to different numbers on purpose.
    """
    parsed = yazio.parse_day(_summary(), "2026-08-20")

    assert parsed is not None
    assert parsed["energy_goal_kcal"] == 2784.0
    assert parsed["energy_kcal"] == 1911.0


def test_parseDay_withoutGoals_stillReturnsTheDay():
    """A missing target must not cost us the intake."""
    payload = _summary()
    payload.pop("goals")

    parsed = yazio.parse_day(payload, "2026-08-20")

    assert parsed is not None
    assert parsed["energy_kcal"] == 1911.0
    assert parsed["energy_goal_kcal"] is None


# ── the item-by-item diary ───────────────────────────────────────────────────


def _consumed() -> dict:
    """A real /user/consumed-items payload, from an actual day.

    Note the first three eggs: logged in the morning at amount 0, then re-logged
    properly in the evening. Keeping them would show six eggs for a breakfast
    that had three.
    """
    return {
        "products": [
            {
                "id": f"zeroed-{i}", "date": "2026-08-20 09:06:45", "daytime": "breakfast",
                "type": "product", "product_id": "9d439d10", "amount": 0,
                "serving": "egg", "serving_quantity": 0,
            }
            for i in range(3)
        ] + [
            {
                "id": f"egg-{i}", "date": "2026-08-20 19:24:41", "daytime": "breakfast",
                "type": "product", "product_id": "16fc6b10", "amount": 60,
                "serving": "egg", "serving_quantity": 1,
            }
            for i in range(3)
        ] + [
            {
                "id": "milk", "date": "2026-08-20 19:25:04", "daytime": "breakfast",
                "type": "product", "product_id": "9f73ae72", "amount": 200,
                "serving": "cup", "serving_quantity": 1,
            }
        ],
        "recipe_portions": [],
        "simple_products": [
            {
                "id": "lunch-1", "date": "2026-08-20 19:29:59", "daytime": "lunch",
                "type": "simple_product",
                "name": "Pranzo con culatello, polenta e Spritz",
                "nutrients": {
                    "energy.energy": 1551, "nutrient.protein": 65,
                    "nutrient.fat": 70, "nutrient.carb": 110,
                },
                "is_ai_generated": True,
            }
        ],
    }


def test_parseConsumed_dropsZeroedEntries():
    """Logged then set to zero: they contribute nothing and would double a meal."""
    items = yazio.parse_consumed(_consumed(), "2026-08-20")

    assert not [i for i in items if i["yazio_id"].startswith("zeroed")]
    assert len([i for i in items if i["product_id"] == "16fc6b10"]) == 3


def test_parseConsumed_takesSimpleProductsWholesale():
    """Free-text entries carry name and nutrients inline — nothing to resolve."""
    items = yazio.parse_consumed(_consumed(), "2026-08-20")
    lunch = next(i for i in items if i["yazio_id"] == "lunch-1")

    assert lunch["name"].startswith("Pranzo con culatello")
    assert lunch["energy_kcal"] == 1551
    assert lunch["meal"] == "lunch"
    assert lunch["product_id"] is None


def test_parseConsumed_leavesCatalogueProductsUnnamed():
    """A catalogue item is only a UUID here; the name is resolved separately."""
    items = yazio.parse_consumed(_consumed(), "2026-08-20")
    egg = next(i for i in items if i["yazio_id"] == "egg-0")

    assert egg["name"] is None
    assert egg["product_id"] == "16fc6b10"
    assert egg["amount"] == 60
    assert egg["serving"] == "egg"
    # No energy invented from an assumed serving size.
    assert egg["energy_kcal"] is None


def test_parseConsumed_withUnknownShape_returnsEmpty():
    assert yazio.parse_consumed(None, "2026-08-20") == []
    assert yazio.parse_consumed({}, "2026-08-20") == []
    assert yazio.parse_consumed({"products": "nope"}, "2026-08-20") == []


def test_fetchProduct_returnsTheName():
    request = _responder({"id": "16fc6b10", "name": "Uovo", "producer": "Coop"})

    assert yazio.fetch_product("acc", "16fc6b10", request=request) == {
        "product_id": "16fc6b10",
        "name": "Uovo",
        "producer": "Coop",
    }


def test_fetchProduct_withoutAName_isNone():
    """An unnamed product is no better than an unresolved one."""
    assert yazio.fetch_product("acc", "x", request=_responder({"id": "x"})) is None
