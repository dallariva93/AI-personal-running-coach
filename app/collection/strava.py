"""Strava integration: OAuth 2.0, REST client, webhooks and activity mapping.

Strava is an opt-in *event-driven* source. Unlike the Garmin source (which we
poll), Strava pushes a webhook to us whenever an athlete creates an activity;
we then pull the full activity via the REST API and map it to a
:class:`~app.schemas.RunSummary`.

This module is the low-level, side-effect-light client plus the pure
``activity → RunSummary`` mapping. The orchestration (token storage, the
durable webhook inbox, the worker) lives in :mod:`app.services.strava_sync`.

Docs: https://developers.strava.com/docs/
"""

from __future__ import annotations

import json as _json
from typing import Any

import requests

from app.collection.synthesize import (
    _LUNGO_MIN_DISTANCE_KM,
    _TRAIL_MIN_ELEVATION_M,
    _format_pace,
    _match_name_hint,
    _num,
)
from app.config import Settings, get_settings
from app.exceptions import CollectionError
from app.logging_config import get_logger
from app.schemas import RunSummary
from app.utils import retry_call

logger = get_logger("app.collection.strava")

STRAVA_OAUTH_AUTHORIZE = "https://www.strava.com/oauth/authorize"
STRAVA_OAUTH_TOKEN = "https://www.strava.com/oauth/token"
STRAVA_API_BASE = "https://www.strava.com/api/v3"
# read activity data, including private activities (needed for full history).
DEFAULT_SCOPE = "read,activity:read_all"
_HTTP_TIMEOUT = 30


# ── encoded polyline ─────────────────────────────────────────────────────────


def decode_polyline(encoded: str) -> list[list[float]]:
    """Decode a Google-encoded polyline string into ``[[lat, lon], ...]``.

    Strava returns the route as a Google-encoded polyline (precision 5).
    This is the same format Garmin's ``geoPolylineDTO`` would give us decoded;
    we round to 6 decimals to match our GPS storage convention.
    """
    if not encoded:
        return []
    points: list[list[float]] = []
    index = 0
    lat = 0
    lon = 0
    length = len(encoded)
    while index < length:
        for is_lon in (False, True):
            shift = 0
            result = 0
            while True:
                if index >= length:
                    return points
                byte = ord(encoded[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            delta = ~(result >> 1) if (result & 1) else (result >> 1)
            if is_lon:
                lon += delta
            else:
                lat += delta
        points.append([round(lat / 1e5, 6), round(lon / 1e5, 6)])
    return points


# ── activity → RunSummary ────────────────────────────────────────────────────


def _strava_splits(activity: dict[str, Any]) -> list[str] | None:
    """Per-km pace strings from Strava's ``splits_metric``."""
    raw = activity.get("splits_metric")
    if not isinstance(raw, list) or not raw:
        return None
    out: list[str] = []
    for split in raw:
        if not isinstance(split, dict):
            continue
        dist = _num(split.get("distance"))
        dur = _num(split.get("moving_time") or split.get("elapsed_time"))
        pace = _format_pace(dist or 0.0, dur or 0.0)
        if pace:
            out.append(pace)
    return out or None


def _infer_strava_type(activity: dict[str, Any]) -> str:
    """Classify a Strava run into our taxonomy.

    Priority: athlete-set name keyword → Strava ``workout_type`` flag →
    trail terrain → distance (long run) → default easy. Mirrors the spirit of
    the Garmin classifier but uses the signals Strava exposes.
    """
    name_hint = _match_name_hint(str(activity.get("name", "")))
    if name_hint is not None:
        return name_hint

    # Strava run workout_type: 1=race, 2=long run, 3=workout(intervals/tempo).
    workout_type = activity.get("workout_type")
    if workout_type == 1:
        return "gara"
    if workout_type == 2:
        return "lungo"
    if workout_type == 3:
        return "intervalli"

    sport = str(activity.get("sport_type") or activity.get("type") or "").lower()
    elevation = _num(activity.get("total_elevation_gain"))
    if "trail" in sport or (elevation is not None and elevation >= _TRAIL_MIN_ELEVATION_M):
        return "trail"

    distance_km = (_num(activity.get("distance")) or 0.0) / 1000.0
    if distance_km >= _LUNGO_MIN_DISTANCE_KM:
        return "lungo"

    return "easy"


# ── multi-sport (Feature 24) ─────────────────────────────────────────────────
#
# Strava's ``sport_type`` (preferred) / ``type`` (legacy) collapsed into our
# disciplines. Running maps to ``run`` (handled by the standard run pipeline);
# the three cross-training disciplines are tracked but kept out of running load.
_STRAVA_SPORT_MAP = {
    "ride": "bike",
    "mountainbikeride": "bike",
    "gravelride": "bike",
    "virtualride": "bike",
    "ebikeride": "bike",
    "velomobile": "bike",
    "handcycle": "bike",
    "swim": "swim",
    "weighttraining": "strength",
    "workout": "strength",
    "crossfit": "strength",
    "elliptical": "strength",
    "yoga": "strength",
    "pilates": "strength",
    "stairstepper": "strength",
}


def strava_sport(activity: dict[str, Any]) -> str | None:
    """Return our sport label for a Strava activity.

    Returns ``"run"`` for any running activity, one of the cross-training
    disciplines for bike/swim/strength, or ``None`` for unsupported types.
    """
    sport = str(activity.get("sport_type") or activity.get("type") or "").lower()
    if "run" in sport:
        return "run"
    return _STRAVA_SPORT_MAP.get(sport)


def synthesize_cross_training_strava(activity: dict[str, Any], sport: str) -> RunSummary:
    """Map a Strava cross-training activity to a :class:`RunSummary`.

    Like :func:`synthesize_cross_training` for Garmin: no running workout
    classification, ``activity_type`` mirrors the sport, distance degrades to 0
    for strength work, sport-agnostic fields (HR, duration, elevation) kept.
    """
    distance_m = _num(activity.get("distance")) or 0.0
    moving_s = _num(activity.get("moving_time")) or 0.0
    elapsed_s = _num(activity.get("elapsed_time")) or moving_s
    duration_min = round((moving_s or elapsed_s) / 60.0, 1)

    start_local = str(activity.get("start_date_local") or activity.get("start_date") or "")
    date = start_local[:10] if start_local else ""

    avg_hr = _num(activity.get("average_heartrate"))
    max_hr = _num(activity.get("max_heartrate"))

    route_polyline = None
    map_field = activity.get("map")
    if isinstance(map_field, dict):
        encoded = map_field.get("polyline") or map_field.get("summary_polyline")
        if encoded:
            pts = decode_polyline(str(encoded))
            if len(pts) >= 2:
                route_polyline = _json.dumps(pts)

    return RunSummary(
        strava_activity_id=str(activity.get("id")) if activity.get("id") else None,
        date=date,
        sport=sport,
        activity_type=sport,
        duration_min=duration_min,
        distance_km=round(distance_m / 1000.0, 2),
        avg_pace=_format_pace(distance_m, moving_s or elapsed_s) if sport == "swim" else None,
        avg_hr=round(avg_hr) if avg_hr else None,
        max_hr=round(max_hr) if max_hr else None,
        elevation_gain_m=_num(activity.get("total_elevation_gain")),
        notes=activity.get("description") or None,
        route_polyline=route_polyline,
    )


def synthesize_strava(activity: dict[str, Any]) -> RunSummary:
    """Map a Strava detailed-activity payload to a :class:`RunSummary`.

    Defensive throughout: Strava omits many fields for activities recorded
    without the relevant sensor (no HR strap → no ``average_heartrate``), so
    every optional field degrades to ``None``.
    """
    distance_m = _num(activity.get("distance")) or 0.0
    moving_s = _num(activity.get("moving_time")) or 0.0
    elapsed_s = _num(activity.get("elapsed_time")) or moving_s
    duration_min = round((moving_s or elapsed_s) / 60.0, 1)

    start_local = str(activity.get("start_date_local") or activity.get("start_date") or "")
    date = start_local[:10] if start_local else ""

    avg_hr = _num(activity.get("average_heartrate"))
    max_hr = _num(activity.get("max_heartrate"))

    # Strava reports running cadence per leg (rpm); double it for steps/min.
    cadence = _num(activity.get("average_cadence"))
    avg_cadence = round(cadence * 2) if cadence else None

    route_polyline = None
    map_field = activity.get("map")
    if isinstance(map_field, dict):
        encoded = map_field.get("polyline") or map_field.get("summary_polyline")
        if encoded:
            pts = decode_polyline(str(encoded))
            if len(pts) >= 2:
                route_polyline = _json.dumps(pts)

    perceived = activity.get("perceived_exertion")
    rpe = None
    if perceived is not None:
        try:
            rpe = max(1, min(10, round(float(perceived))))
        except (TypeError, ValueError):
            rpe = None

    return RunSummary(
        strava_activity_id=str(activity.get("id")) if activity.get("id") else None,
        date=date,
        activity_type=_infer_strava_type(activity),
        duration_min=duration_min,
        distance_km=round(distance_m / 1000.0, 2),
        avg_pace=_format_pace(distance_m, moving_s or elapsed_s),
        avg_hr=round(avg_hr) if avg_hr else None,
        max_hr=round(max_hr) if max_hr else None,
        elevation_gain_m=_num(activity.get("total_elevation_gain")),
        avg_cadence=avg_cadence,
        rpe=rpe,
        notes=activity.get("description") or None,
        splits_km=_strava_splits(activity),
        route_polyline=route_polyline,
    )


# ── REST client ──────────────────────────────────────────────────────────────


class StravaClient:
    """Thin Strava REST client. Raises :class:`CollectionError` on failure."""

    def __init__(
        self, settings: Settings | None = None, session: requests.Session | None = None
    ) -> None:
        self.settings = settings or get_settings()
        self._http = session or requests.Session()

    # -- OAuth (app-level, no user token) -----------------------------------

    def exchange_code(self, code: str) -> dict[str, Any]:
        """Exchange an authorization ``code`` for access + refresh tokens."""
        return self._token_request(
            {
                "code": code,
                "grant_type": "authorization_code",
            }
        )

    def refresh_token(self, refresh_token: str) -> dict[str, Any]:
        """Exchange a refresh token for a fresh access token."""
        return self._token_request(
            {
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            }
        )

    def _token_request(self, extra: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "client_id": self.settings.strava_client_id,
            "client_secret": self.settings.strava_client_secret,
            **extra,
        }
        try:
            resp = retry_call(
                lambda: self._http.post(
                    STRAVA_OAUTH_TOKEN, data=payload, timeout=_HTTP_TIMEOUT
                ),
                retries=2,
                description="strava.token",
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # noqa: BLE001
            raise CollectionError(f"Strava token request failed: {exc}") from exc

    # -- Activities (user token) --------------------------------------------

    def get_activity(self, access_token: str, activity_id: int | str) -> dict[str, Any]:
        return self._api_get(access_token, f"/activities/{activity_id}")

    def list_activities(
        self, access_token: str, per_page: int = 30, page: int = 1
    ) -> list[dict[str, Any]]:
        data = self._api_get(
            access_token,
            "/athlete/activities",
            params={"per_page": per_page, "page": page},
        )
        return data if isinstance(data, list) else []

    def _api_get(
        self, access_token: str, path: str, params: dict[str, Any] | None = None
    ) -> Any:
        headers = {"Authorization": f"Bearer {access_token}"}
        url = f"{STRAVA_API_BASE}{path}"
        try:
            resp = retry_call(
                lambda: self._http.get(
                    url, headers=headers, params=params, timeout=_HTTP_TIMEOUT
                ),
                retries=2,
                description=f"strava.get({path})",
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # noqa: BLE001
            raise CollectionError(f"Strava API GET {path} failed: {exc}") from exc

    # -- Push subscriptions (app-level) -------------------------------------

    def create_subscription(self, callback_url: str, verify_token: str) -> dict[str, Any]:
        payload = {
            "client_id": self.settings.strava_client_id,
            "client_secret": self.settings.strava_client_secret,
            "callback_url": callback_url,
            "verify_token": verify_token,
        }
        try:
            resp = self._http.post(
                f"{STRAVA_API_BASE}/push_subscriptions", data=payload, timeout=_HTTP_TIMEOUT
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # noqa: BLE001
            raise CollectionError(f"Strava subscription create failed: {exc}") from exc

    def view_subscriptions(self) -> list[dict[str, Any]]:
        params = {
            "client_id": self.settings.strava_client_id,
            "client_secret": self.settings.strava_client_secret,
        }
        try:
            resp = self._http.get(
                f"{STRAVA_API_BASE}/push_subscriptions", params=params, timeout=_HTTP_TIMEOUT
            )
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, list) else []
        except Exception as exc:  # noqa: BLE001
            logger.warning("Strava subscription view failed: %s", exc)
            return []

    def delete_subscription(self, subscription_id: int) -> None:
        params = {
            "client_id": self.settings.strava_client_id,
            "client_secret": self.settings.strava_client_secret,
        }
        try:
            resp = self._http.delete(
                f"{STRAVA_API_BASE}/push_subscriptions/{subscription_id}",
                params=params,
                timeout=_HTTP_TIMEOUT,
            )
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            raise CollectionError(f"Strava subscription delete failed: {exc}") from exc


def build_authorize_url(
    client_id: str, redirect_uri: str, scope: str = DEFAULT_SCOPE, state: str = ""
) -> str:
    """Build the Strava OAuth consent URL to redirect the athlete to."""
    from urllib.parse import urlencode

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "approval_prompt": "auto",
        "scope": scope,
    }
    if state:
        params["state"] = state
    return f"{STRAVA_OAUTH_AUTHORIZE}?{urlencode(params)}"
