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
# Yazio's own mobile client id; the API rejects the token request without it.
CLIENT_ID = "1_4hiybetvfksgw40o0sog4okw4wsgcokwso4openwcwc0w8ldxq"
CLIENT_SECRET = "6rwct1nmy4wkkgm0ksgw8s804bgcskw0o0c84wo88sgc4gw0ws"

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


def _default_request(
    method: str, url: str, *, data: Any = None, params: Any = None, token: str | None = None
) -> dict | None:
    """The real HTTP call. Injectable everywhere above, so tests stay offline."""
    import requests

    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = requests.request(
        method, url, data=data, params=params, headers=headers, timeout=TIMEOUT_S
    )
    response.raise_for_status()
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
    request = request or _default_request
    payload = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "password",
        "username": username,
        "password": password,
    }
    try:
        data = request("POST", TOKEN_URL, data=payload)
    except Exception as exc:  # noqa: BLE001 - surfaced to the caller as a domain error
        raise CollectionError(f"Login Yazio fallito: {exc}") from exc
    return _token_pair(data, "login")


def refresh(refresh_token: str, *, request: Any = None) -> dict[str, Any]:
    """Trade a refresh token for a fresh pair, so the password is never reused."""
    request = request or _default_request
    payload = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    try:
        data = request("POST", TOKEN_URL, data=payload)
    except Exception as exc:  # noqa: BLE001
        raise CollectionError(f"Refresh del token Yazio fallito: {exc}") from exc
    return _token_pair(data, "refresh")


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
            "GET", f"{BASE_URL}/user/consumed-items", params={"date": day_str}, token=token
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
    # The totals live either at the top level or under a "summary"/"totals" key
    # depending on the endpoint variant.
    totals = data
    for key in ("summary", "totals", "nutrients"):
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
    """First present numeric value among ``keys`` (dotted keys are traversed)."""
    for key in keys:
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
