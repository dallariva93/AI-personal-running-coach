"""Integration: connecting Yazio and importing the diary.

Two things matter more than the happy path here:

* **The password must not survive the login.** It is the user's real Yazio
  password, handed to us because the API has no consent screen; the only safe
  thing to do with it is exchange it once and forget it.
* **Nutrition must never be able to break the run import.** The runs are the
  data we cannot re-fetch later; the diary is.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select

from app.db.models import NutritionDay, YazioAccount
from app.services import yazio_sync


def _api(*, days: dict[str, dict] | None = None, tokens: dict | None = None):
    """A fake Yazio: token endpoint + one payload per date."""
    days = days or {}
    tokens = tokens or {"access_token": "acc", "refresh_token": "ref", "expires_in": 3600}
    calls: list = []

    def _request(method, url, *, data=None, json=None, params=None, token=None):
        # The token endpoint is tried as JSON first; day reads send params.
        calls.append({"url": url, "body": json or data, "params": params,
                      "token": token})
        if url.endswith("/oauth/token"):
            return dict(tokens)
        return days.get((params or {}).get("date"))

    _request.calls = calls  # type: ignore[attr-defined]
    return _request


def _totals(kcal: float) -> dict:
    return {"energy": kcal, "protein": 120, "carb": 300, "fat": 70}


# ── connect ──────────────────────────────────────────────────────────────────


def test_connect_storesTokens_encrypted_andNotThePassword(session):
    api = _api()

    yazio_sync.connect_account(session, "me@example.com", "hunter2", request=api)

    account = session.scalars(select(YazioAccount)).one()
    assert account.access_token == "acc"  # decrypted through the hybrid property
    assert account.refresh_token == "ref"
    # The stored column holds ciphertext, and the password appears nowhere.
    assert account._access_token != "acc"
    assert "hunter2" not in account._access_token
    assert "hunter2" not in (account._refresh_token or "")
    assert account.username == "me@example.com"


def test_connect_setsExpiry_inTheFuture(session):
    yazio_sync.connect_account(session, "me@example.com", "pw", request=_api())

    account = yazio_sync.get_account(session)
    assert account is not None
    assert account.expires_at > 0


def test_disconnect_dropsTokens_butKeepsHistory(session):
    yazio_sync.connect_account(session, "me@example.com", "pw", request=_api())
    yazio_sync.upsert_day(session, {"date": "2026-06-22", "energy_kcal": 2400})
    session.commit()

    assert yazio_sync.disconnect_account(session) is True

    assert yazio_sync.get_account(session) is None
    # Revoking access must not destroy data that is already ours.
    assert session.scalars(select(NutritionDay)).all() != []


# ── token refresh ────────────────────────────────────────────────────────────


def test_expiredToken_isRefreshedBeforeUse(session):
    api = _api()
    yazio_sync.connect_account(session, "me@example.com", "pw", request=api)
    account = yazio_sync.get_account(session)
    assert account is not None
    account.expires_at = 0  # as if it had expired
    session.commit()
    api.calls.clear()  # type: ignore[attr-defined]
    api2 = _api(tokens={"access_token": "acc2", "refresh_token": "ref2", "expires_in": 3600})

    token = yazio_sync.valid_access_token(session, account, request=api2)

    assert token == "acc2"
    assert api2.calls[0]["body"]["grant_type"] == "refresh_token"  # type: ignore[attr-defined]


def test_validToken_isNotRefreshed(session):
    api = _api()
    yazio_sync.connect_account(session, "me@example.com", "pw", request=api)
    account = yazio_sync.get_account(session)
    assert account is not None
    api.calls.clear()  # type: ignore[attr-defined]

    assert yazio_sync.valid_access_token(session, account, request=api) == "acc"
    assert api.calls == []  # type: ignore[attr-defined]


# ── import ───────────────────────────────────────────────────────────────────


def test_sync_importsOneRowPerDay(session):
    today = date.today()
    yesterday = today - timedelta(days=1)
    api = _api(days={today.isoformat(): _totals(2400), yesterday.isoformat(): _totals(2100)})
    yazio_sync.connect_account(session, "me@example.com", "pw", request=api)

    result = yazio_sync.sync_nutrition(
        session, start=yesterday, end=today, throttle_s=0.0, request=api
    )

    assert result.saved == 2
    rows = yazio_sync.recent_nutrition(session, yesterday, today)
    assert [r.date for r in rows] == [yesterday.isoformat(), today.isoformat()]
    assert rows[0].energy_kcal == 2100
    assert rows[1].protein_g == 120


def test_sync_isIdempotent_andUpdatesInPlace(session):
    day = date.today()
    api = _api(days={day.isoformat(): _totals(2400)})
    yazio_sync.connect_account(session, "me@example.com", "pw", request=api)
    yazio_sync.sync_nutrition(session, start=day, end=day, throttle_s=0.0, request=api)

    # A day edited later in the app must overwrite, not duplicate: re-reading
    # recent dates is the whole point of the rolling window.
    api2 = _api(days={day.isoformat(): _totals(2600)})
    yazio_sync.sync_nutrition(session, start=day, end=day, throttle_s=0.0, request=api2)

    rows = session.scalars(select(NutritionDay)).all()
    assert len(rows) == 1
    assert rows[0].energy_kcal == 2600


def test_sync_withEmptyDays_savesNothing(session):
    """An unlogged day leaves no row, so it never reads as a 0 kcal day."""
    day = date.today()
    api = _api(days={})
    yazio_sync.connect_account(session, "me@example.com", "pw", request=api)

    result = yazio_sync.sync_nutrition(
        session, start=day - timedelta(days=2), end=day, throttle_s=0.0, request=api
    )

    assert result.saved == 0
    assert result.empty == 3
    assert session.scalars(select(NutritionDay)).all() == []


def test_sync_withoutAccount_isANoOp(session):
    result = yazio_sync.sync_nutrition(session, throttle_s=0.0, request=_api())

    assert result.considered == 0
    assert result.saved == 0


def test_sync_whenRefreshFails_reportsInsteadOfRaising(session):
    """An expired refresh token means "reconnect", not "crash the caller"."""
    yazio_sync.connect_account(session, "me@example.com", "pw", request=_api())
    account = yazio_sync.get_account(session)
    assert account is not None
    account.expires_at = 0
    session.commit()

    def _dead(method, url, *, data=None, json=None, params=None, token=None):
        raise RuntimeError("401 invalid_grant")

    result = yazio_sync.sync_nutrition(session, throttle_s=0.0, request=_dead)

    assert result.saved == 0
    assert result.errors


def test_sync_whenTheApiIsDown_writesNothing(session):
    """An unreachable API must never leave a row behind.

    It is now counted as `failed`, not `empty`: reading a broken API as "the
    athlete logged nothing" is what would let the coach conclude there is an
    energy deficit where there is only a network problem.
    """

    def _explode(method, url, *, data=None, json=None, params=None, token=None):
        if url.endswith("/oauth/token"):
            return {"access_token": "acc", "refresh_token": "ref", "expires_in": 3600}
        raise RuntimeError("boom")

    yazio_sync.connect_account(session, "me@example.com", "pw", request=_explode)

    result = yazio_sync.sync_nutrition(
        session, days=3, throttle_s=0.0, request=_explode
    )

    assert result.saved == 0
    assert result.failed == 3
    assert result.empty == 0
    assert session.scalars(select(NutritionDay)).all() == []


def test_trySync_swallowsEverything(session, monkeypatch):
    """The ingest pipeline calls this: it must never raise into the run path."""

    def _explode(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(yazio_sync, "sync_nutrition", _explode)

    result = yazio_sync.try_sync_nutrition(session, throttle_s=0.0)

    assert result.saved == 0
    assert result.errors


def test_ingestRuns_worksWithoutYazioConnected(session, demo_source):
    """No Yazio account → the run import is untouched."""
    from app.services.ingest import ingest_runs

    saved = ingest_runs(session, limit=3, source=demo_source)

    assert saved
    assert session.scalars(select(NutritionDay)).all() == []


def test_sync_countsFailuresApartFromEmptyDays(session):
    """The distinction that a whole afternoon hinged on.

    "90 giorni vuoti" meant either "the diary is empty" or "every request was
    rejected" — the same number for opposite problems.
    """

    def _failing(method, url, *, data=None, json=None, params=None, token=None):
        if url.endswith("/oauth/token"):
            return {"access_token": "acc", "refresh_token": "ref", "expires_in": 3600}
        raise RuntimeError("HTTP 404")

    yazio_sync.connect_account(session, "me@example.com", "pw", request=_failing)

    result = yazio_sync.sync_nutrition(
        session, days=5, throttle_s=0.0, request=_failing
    )

    assert result.failed == 5
    assert result.empty == 0
    # Only the first few errors: ninety identical ones say nothing ninety times.
    assert 0 < len(result.errors) <= 3
    assert "404" in result.errors[0]


def test_sync_emptyDaysAreNotCountedAsFailures(session):
    """The mirror case: the API answers fine, the diary just has nothing."""
    api = _api(days={})
    yazio_sync.connect_account(session, "me@example.com", "pw", request=api)

    result = yazio_sync.sync_nutrition(session, days=3, throttle_s=0.0, request=api)

    assert result.empty == 3
    assert result.failed == 0
    assert result.errors == []
