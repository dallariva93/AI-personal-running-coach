"""Yazio client: nutrition and body-weight data.

Nutrition closes a loop the running data alone cannot: a block that stalls
because of a carbohydrate deficit looks identical to one that stalls from too
much load, and the Digital Twin would learn "low ramp tolerance" from what is
really under-eating.

Unofficial API, like Garmin's — reverse-engineered, no vendor contract, and it
may change without notice. Everything here parses defensively so a renamed
field produces a missing value rather than a wrong one, and every call is
best-effort at the service layer above.

Authentication is OAuth2. The password is used **once**, to obtain a token
pair; from then on the refresh token keeps the session alive and the password
is never stored (see ``app/services/yazio_sync.py``).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from app.exceptions import CollectionError
from app.logging_config import get_logger

logger = get_logger("app.collection.yazio")

BASE_URL = "https://yzapi.yazio.com/v15"
TOKEN_URL = f"{BASE_URL}/oauth/token"

# The app-level client identity Yazio's own mobile client presents. Not a user
# secret — every copy of the app carries the same pair — but it *is* versioned
# by Yazio, and a stale pair is rejected with "Invalid client" before the
# credentials are even looked at. Overridable by env precisely because of that:
# when Yazio rotates them, a secret update beats a code change and a deploy.
_DEFAULT_CLIENT_ID = "1_4hiybetvfksgw40o0sog4s884kwc840wwso8go4k8c04goo4c"
_DEFAULT_CLIENT_SECRET = "6rok2m65xuskgkgogw40wkkk8sw0osg84s8cggsc4woos4s8o"


def _client_identity() -> tuple[str, str]:
    from app.config import get_settings

    settings = get_settings()
    client_id = settings.yazio_client_id or _DEFAULT_CLIENT_ID
    client_secret = settings.yazio_client_secret or _DEFAULT_CLIENT_SECRET
    if not (client_id and client_secret):
        # Fail here, with the fix in the message. Sending empty strings would
        # just earn another "Invalid client" from Yazio — the same symptom for
        # a completely different cause, which is how an afternoon disappears.
        raise CollectionError(
            "Client Yazio non configurato: imposta i secret YAZIO_CLIENT_ID e "
            "YAZIO_CLIENT_SECRET (la coppia applicativa del client Yazio, non "
            "le tue credenziali personali)."
        )
    return client_id, client_secret


# Daily totals, already aggregated by Yazio. NOT /user/consumed-items: that one
# returns the individual diary entries, which would mean summing meals here and
# carrying a payload two orders of magnitude larger for the same four numbers.
DAILY_SUMMARY_PATH = "/user/widgets/daily-summary"

TIMEOUT_S = 15.0
# Refresh this many seconds before the token actually expires, so a call never
# races the expiry.
REFRESH_SKEW_S = 120


def _num(value: Any) -> float | None:
    """Best-effort float parse — the API types numbers inconsistently."""
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


class YazioHTTPError(Exception):
    """An HTTP error that keeps the response body.

    ``raise_for_status()`` throws the body away and leaves only "400 Bad
    Request", which on an OAuth endpoint is the least informative half of the
    answer: the body is where the server says *invalid_client* vs
    *invalid_grant* vs *unsupported_grant_type*. Without it, a malformed request
    and a wrong password look identical from the outside.
    """

    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"HTTP {status}: {body}" if body else f"HTTP {status}")
        self.status = status
        self.body = body


# Enough of the body to carry an OAuth error code and its description, not so
# much that a stray HTML error page floods the logs.
_MAX_BODY_CHARS = 400


def _default_request(
    method: str,
    url: str,
    *,
    data: Any = None,
    json: Any = None,
    params: Any = None,
    token: str | None = None,
) -> dict | None:
    """The real HTTP call. Injectable everywhere above, so tests stay offline."""
    import requests

    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = requests.request(
        method,
        url,
        data=data,
        json=json,
        params=params,
        headers=headers,
        timeout=TIMEOUT_S,
    )
    if response.status_code >= 400:
        raise YazioHTTPError(response.status_code, (response.text or "")[:_MAX_BODY_CHARS])
    if not response.content:
        return None
    return response.json()


def login(username: str, password: str, *, request: Any = None) -> dict[str, Any]:
    """Exchange credentials for a token pair. Called once, at connect time.

    Returns ``{access_token, refresh_token, expires_in}``. Raises
    :class:`CollectionError` on bad credentials or an unreachable API — this is
    the one Yazio call that must *not* fail silently, because the user is
    standing there waiting to know whether the connection worked.
    """
    client_id, client_secret = _client_identity()
    return _token_request(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "password",
            "username": username,
            "password": password,
        },
        "login",
        request or _default_request,
    )


def refresh(refresh_token: str, *, request: Any = None) -> dict[str, Any]:
    """Trade a refresh token for a fresh pair, so the password is never reused."""
    client_id, client_secret = _client_identity()
    return _token_request(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        "refresh",
        request or _default_request,
    )


def _token_request(payload: dict[str, Any], what: str, request: Any) -> dict[str, Any]:
    """POST to the token endpoint, trying JSON then form encoding.

    The v15 API is JSON throughout, so that is the first attempt. The fallback
    exists because the encoding is the one thing we cannot check from here and
    a wrong guess yields a bare 400 — trying both costs one extra request on a
    call that happens once per connection, and removes a whole round trip of
    "deploy, run, read the error, guess again".
    """
    attempts = (("json", {"json": payload}), ("form", {"data": payload}))
    last: Exception | None = None
    for encoding, kwargs in attempts:
        try:
            data = request("POST", TOKEN_URL, **kwargs)
        except YazioHTTPError as exc:
            last = exc
            # 400 is "I could not read this request"; anything else (401 wrong
            # credentials, 5xx, network) is a real answer and re-encoding it
            # would only hide the cause.
            if exc.status != 400:
                break
            logger.info("Token Yazio: %s rifiutato in %s, riprovo", what, encoding)
            continue
        except Exception as exc:  # noqa: BLE001 - surfaced as a domain error
            last = exc
            break
        else:
            if encoding == "form":
                logger.info("Token Yazio ottenuto con encoding form-urlencoded.")
            return _token_pair(data, what)
    # The body we just decided to surface is written by someone else's server:
    # if it echoes the request back, the password rides along into the logs and
    # onto a terminal that gets screenshotted. Scrub before it leaves here.
    detail = _scrub(str(last), payload)
    raise CollectionError(f"{what.capitalize()} Yazio fallito: {detail}") from last


# Payload fields that must never appear in an error message or a log line.
_SECRET_FIELDS = ("password", "client_secret", "refresh_token")


def _scrub(text: str, payload: dict[str, Any]) -> str:
    for field in _SECRET_FIELDS:
        value = payload.get(field)
        if value and isinstance(value, str) and value in text:
            text = text.replace(value, "***")
    return text


def _token_pair(data: Any, what: str) -> dict[str, Any]:
    if not isinstance(data, dict) or not data.get("access_token"):
        raise CollectionError(f"Risposta di {what} Yazio senza access_token.")
    return {
        "access_token": str(data["access_token"]),
        # Some responses omit the refresh token on refresh; the caller keeps
        # the previous one in that case rather than losing the session.
        "refresh_token": str(data["refresh_token"]) if data.get("refresh_token") else None,
        "expires_in": int(_num(data.get("expires_in")) or 3600),
    }


def fetch_day(token: str, day: date | str, *, request: Any = None) -> dict[str, Any] | None:
    """One day of nutrition, already aggregated. ``None`` when unavailable.

    Yazio's daily summary carries the totals we want (energy and macros) without
    walking the individual diary entries — which is also what keeps the payload
    small enough to be worth putting in a chat context.
    """
    request = request or _default_request
    day_str = day.isoformat() if isinstance(day, date) else str(day)
    try:
        data = request(
            "GET", f"{BASE_URL}{DAILY_SUMMARY_PATH}", params={"date": day_str}, token=token
        )
    except Exception as exc:  # noqa: BLE001 - one missing day is not an error
        logger.warning("Yazio non raggiungibile per %s: %s", day_str, exc)
        return None
    return parse_day(data, day_str)


def parse_day(data: Any, day_str: str) -> dict[str, Any] | None:
    """Normalise a daily payload into our flat shape.

    Tolerant on purpose: the field names below are the ones observed today on
    an API with no contract. An unknown shape yields ``None`` (treated as "no
    data for this day"), never a half-filled row that would read as a real
    measurement of zero calories.
    """
    if not isinstance(data, dict):
        return None
    # The totals live either at the top level or under a nested key, depending
    # on the payload variant. `nutrients` is the one daily-summary actually
    # uses; the others cost nothing and cover the neighbouring shapes.
    totals = data
    for key in ("nutrients", "summary", "totals"):
        nested = data.get(key)
        if isinstance(nested, dict):
            totals = {**totals, **nested}

    energy = _first(totals, ("energy", "energy.energy", "calories", "kcal"))
    protein = _first(totals, ("protein", "nutrient.protein", "proteins"))
    carbs = _first(totals, ("carb", "carbs", "nutrient.carb", "carbohydrates"))
    fat = _first(totals, ("fat", "nutrient.fat", "fats"))

    if energy is None and protein is None and carbs is None and fat is None:
        _warn_unknown_shape(totals)
        return None

    return {
        "date": day_str,
        # Yazio stores energy in kJ in some payloads; anything above a plausible
        # daily kcal ceiling is converted rather than stored as nonsense.
        "energy_kcal": _as_kcal(energy),
        "protein_g": _round(protein),
        "carbs_g": _round(carbs),
        "fat_g": _round(fat),
        "water_ml": _round(_first(totals, ("water_intake", "water", "water_ml")), 0),
    }


# Fires at most once per process: a 90-day import would otherwise log the same
# diagnosis ninety times.
_shape_warned = False


def _warn_unknown_shape(totals: dict) -> None:
    """Log which field names *did* arrive, when none of the expected ones did.

    The whole risk of an undocumented API is a silent rename: without this, a
    changed schema is indistinguishable from an empty diary — both show up as
    "0 giorni salvati" and there is nothing to go on. Only the **keys** are
    logged, never the values: what someone ate is not diagnostic data.
    """
    global _shape_warned
    if _shape_warned or not totals:
        return
    _shape_warned = True
    logger.warning(
        "Payload Yazio non riconosciuto: nessun campo atteso (energy/protein/"
        "carb/fat) fra quelli ricevuti: %s. Probabile rinomina dei campi "
        "nell'API: vanno aggiornati i nomi in parse_day().",
        sorted(totals.keys())[:40],
    )


def _first(payload: dict, keys: tuple[str, ...]) -> float | None:
    """First present numeric value among ``keys``.

    A dotted key is tried **literally first**, then as a path. Yazio uses dots
    inside the key names themselves — ``{"nutrient.protein": 120}`` is one flat
    key, not a nested object — so a traversal-only lookup would walk into a
    ``"nutrient"`` that does not exist and report the day as empty.
    """
    for key in keys:
        value = _num(payload.get(key))
        if value is not None:
            return value
        if "." not in key:
            continue
        node: Any = payload
        for part in key.split("."):
            node = node.get(part) if isinstance(node, dict) else None
            if node is None:
                break
        value = _num(node)
        if value is not None:
            return value
    return None


# Above this a daily "energy" figure is kilojoules, not kilocalories: no diary
# realistically records 12k kcal, while 12k kJ is an ordinary day.
_KJ_THRESHOLD = 10000.0


def _as_kcal(value: float | None) -> float | None:
    if value is None:
        return None
    if value > _KJ_THRESHOLD:
        return round(value / 4.184, 1)
    return round(value, 1)


def _round(value: float | None, digits: int = 1) -> float | None:
    return None if value is None else round(value, digits)
