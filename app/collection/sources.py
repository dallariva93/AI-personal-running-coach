"""Activity data sources.

Two implementations behind a tiny ``ActivitySource`` protocol:

* :class:`GarminSource` — live data via the unofficial ``python-garminconnect``.
* :class:`DemoSource` — bundled JSON fixtures so the whole app runs with zero
  credentials (development, CI, first-run demo).

``get_source()`` picks the right one based on configuration.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from app.collection.synthesize import (
    extract_altitude_profile,
    extract_details_enrichment,
    extract_gps_from_details,
    extract_hr_zones_from_timezones,
    extract_splits,
    extract_weather,
    garmin_sport,
    synthesize,
    synthesize_cross_training,
)
from app.config import Settings, get_settings
from app.exceptions import CollectionError
from app.logging_config import get_logger
from app.schemas import RunSummary
from app.utils import retry_call

logger = get_logger("app.collection")

_DEMO_DATA = Path(__file__).resolve().parent.parent.parent / "data" / "demo_activities.json"
_DEMO_CROSS = Path(__file__).resolve().parent.parent.parent / "data" / "demo_cross_training.json"


class ActivitySource(Protocol):
    """Anything that can return a list of synthesised runs."""

    def get_recent_runs(
        self, limit: int = 10, skip_gps_for: set[str] | None = None
    ) -> list[RunSummary]: ...

    def get_recent_cross_training(self, limit: int = 20) -> list[RunSummary]:
        """Return recent cross-training (bike/swim/strength) activities."""
        ...


def _is_running(activity: dict[str, Any]) -> bool:
    type_field = activity.get("activityType", {})
    type_key = type_field.get("typeKey", "") if isinstance(type_field, dict) else str(type_field)
    return "running" in type_key.lower()


class DemoSource:
    """Returns bundled sample runs. Always available, no network, no cost."""

    def __init__(
        self, path: Path | str = _DEMO_DATA, cross_path: Path | str = _DEMO_CROSS
    ) -> None:
        self.path = Path(path)
        self.cross_path = Path(cross_path)

    def get_recent_runs(
        self, limit: int = 10, skip_gps_for: set[str] | None = None
    ) -> list[RunSummary]:
        if not self.path.exists():
            return []
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        runs = [synthesize(a) for a in raw if _is_running(a)]
        runs.sort(key=lambda r: r.date, reverse=True)
        return runs[:limit]

    def get_recent_cross_training(self, limit: int = 20) -> list[RunSummary]:
        if not self.cross_path.exists():
            return []
        raw = json.loads(self.cross_path.read_text(encoding="utf-8"))
        out: list[RunSummary] = []
        for activity in raw:
            sport = garmin_sport(activity)
            if sport is None:
                continue
            out.append(synthesize_cross_training(activity, sport))
        out.sort(key=lambda r: r.date, reverse=True)
        return out[:limit]


class GarminSource:
    """Live Garmin Connect source using ``python-garminconnect``.

    Login tokens are cached on disk so repeated runs don't re-authenticate.
    The import is lazy so the package isn't required in demo/CI environments.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client = None

    def _login(self):
        if self._client is not None:
            return self._client
        from garminconnect import Garmin  # lazy import

        token_store = self.settings.garmin_token_store
        client = None
        # Try cached tokens first (fast path, survives 2FA).
        try:
            client = Garmin()
            client.login(token_store)
            logger.info("Garmin login via cached tokens")
        except Exception:
            logger.info("Cached Garmin tokens unavailable, logging in with credentials")
            client = Garmin(self.settings.garmin_email, self.settings.garmin_password)
            retry_call(
                client.login,
                retries=self.settings.garmin_max_retries,
                description="garmin.login",
            )
            try:
                client.garth.dump(token_store)
            except Exception:
                logger.warning("Could not persist Garmin tokens to %s", token_store)
        self._client = client
        return client

    def get_recent_runs(
        self, limit: int = 10, skip_gps_for: set[str] | None = None
    ) -> list[RunSummary]:
        running = self._fetch_running(limit)
        runs: list[RunSummary] = []
        client = self._login()
        for activity in running:
            activity_id = activity.get("activityId")
            already_has_gps = (
                skip_gps_for is not None and str(activity_id) in skip_gps_for
            )
            run = synthesize(activity)
            extras = self._fetch_enrichment(client, activity_id, skip_gps=already_has_gps)
            if extras:
                run = run.model_copy(update=extras)
            runs.append(run)
        return runs

    def get_recent_cross_training(self, limit: int = 20) -> list[RunSummary]:
        """Fetch recent bike/swim/strength activities from Garmin (manual sync).

        Pulls a wider activity window (cross-training is interleaved with runs)
        and keeps only the tracked cross-training disciplines. Kept deliberately
        light — just the summary fields, no per-activity detail enrichment — so
        a manual multi-sport sync stays cheap on the Garmin API.
        """
        activities = self.get_recent_activities(max(limit * 3, limit))
        out: list[RunSummary] = []
        for activity in activities:
            sport = garmin_sport(activity)
            if sport is None:
                continue
            out.append(synthesize_cross_training(activity, sport))
            if len(out) >= limit:
                break
        return out

    def get_recent_activities(self, limit: int = 10) -> list[dict[str, Any]]:
        """Return the raw Garmin activity dicts, *without* filtering by type.

        Used by the raw archival pipeline to back up every activity
        (running, cycling, swimming, strength, ...) rather than the
        running subset surfaced to the coaching layer.
        """
        try:
            client = self._login()
            activities = retry_call(
                lambda: client.get_activities(0, limit),
                retries=self.settings.garmin_max_retries,
                description="garmin.get_activities",
            )
        except Exception as exc:  # network, auth, library breakage
            logger.error("Garmin fetch failed: %s", exc)
            raise CollectionError(f"Impossibile scaricare i dati da Garmin: {exc}") from exc
        activities = [a for a in activities if isinstance(a, dict)]
        activities.sort(key=lambda a: str(a.get("startTimeLocal", "")), reverse=True)
        return activities[:limit]

    def get_activities_page(self, start: int, limit: int) -> list[dict[str, Any]]:
        """One page of raw activities, newest first, starting at offset ``start``.

        ``get_recent_activities`` only ever reads the head of the history; the
        backfill needs to walk backwards through it, which is the same Garmin
        call with a non-zero offset. Kept separate so the hot sync path keeps
        its "fetch a window and sort" behaviour unchanged.
        """
        try:
            client = self._login()
            activities = retry_call(
                lambda: client.get_activities(start, limit),
                retries=self.settings.garmin_max_retries,
                description=f"garmin.get_activities[{start}:{start + limit}]",
            )
        except Exception as exc:  # network, auth, library breakage
            logger.error("Garmin page fetch failed at offset %d: %s", start, exc)
            raise CollectionError(
                f"Impossibile scaricare la pagina {start} da Garmin: {exc}"
            ) from exc
        return [a for a in (activities or []) if isinstance(a, dict)]

    def get_activity_enrichment(self, activity_id: Any) -> dict[str, Any]:
        """Per-activity detail (splits, HR zones, weather, GPS) for one activity."""
        return self._fetch_enrichment(self._login(), activity_id, skip_gps=False)

    def get_client(self) -> Any:
        """Return the underlying logged-in client (for raw archival)."""
        return self._login()

    def _fetch_running(self, limit: int) -> list[dict[str, Any]]:
        # Fetch a larger window so the head still has ``limit`` running
        # entries after filtering out cycling/swim/strength/etc.
        activities = self.get_recent_activities(max(limit * 3, limit))
        running = [a for a in activities if _is_running(a)]
        return running[:limit]

    def _fetch_enrichment(
        self, client: Any, activity_id: Any, skip_gps: bool = False
    ) -> dict[str, Any]:
        """Fetch the per-activity fields that only live on the detail endpoints.

        The list payload from ``get_activities`` is sparse; the real metrics
        (VO2max, training load, HR zones, training effect, grade-adjusted pace,
        fastest splits, temperature, per-km splits...) live on the per-activity
        endpoints. We pull them here, falling back to dedicated endpoints only
        when the main detail payload didn't already carry the value, to keep the
        number of calls (and rate-limit pressure) down.

        Every call is best-effort: failures are logged and skipped so a
        transient 429 leaves a field unset rather than aborting the whole
        ingest.
        """
        if activity_id is None:
            return {}

        out: dict[str, Any] = {}
        details = self._safe_call(
            getattr(client, "get_activity", None), activity_id, "get_activity"
        )
        if details:
            out.update(extract_details_enrichment(details))

        # GPS track (route_polyline) and elevation profile from the full detail
        # stream — same source Garmin Connect uses for its map view.
        # Skipped when the caller knows this activity already has GPS data in
        # the DB, avoiding a costly API call per already-synced activity.
        if not skip_gps:
            detail_stream = self._safe_call(
                getattr(client, "get_activity_details", None), activity_id, "activity_details"
            )
            if detail_stream:
                gps = extract_gps_from_details(detail_stream)
                for key, val in gps.items():
                    out.setdefault(key, val)

        if "hr_zones" not in out:
            zones = extract_hr_zones_from_timezones(
                self._safe_call(
                    getattr(client, "get_activity_hr_in_timezones", None),
                    activity_id,
                    "hr_in_timezones",
                )
            )
            if zones:
                out["hr_zones"] = zones

        if "splits_km" not in out or "altitude_profile" not in out:
            splits_payload = self._safe_call(
                getattr(client, "get_activity_splits", None), activity_id, "splits"
            )
            if splits_payload:
                if "splits_km" not in out:
                    splits = extract_splits(splits_payload)
                    if splits:
                        out["splits_km"] = splits
                if "altitude_profile" not in out:
                    alt_profile = extract_altitude_profile(splits_payload)
                    if alt_profile:
                        out["altitude_profile"] = alt_profile

        if "humidity_pct" not in out:
            weather = extract_weather(
                self._safe_call(
                    getattr(client, "get_activity_weather", None), activity_id, "weather"
                )
            )
            for key, value in weather.items():
                out.setdefault(key, value)

        return out

    def _safe_call(self, fn: Any, activity_id: Any, label: str) -> Any:
        """Call a Garmin client method with retry; return ``None`` on failure."""
        if fn is None:
            return None
        try:
            return retry_call(
                lambda: fn(activity_id),
                retries=self.settings.garmin_max_retries,
                description=f"garmin.{label}({activity_id})",
            )
        except Exception as exc:  # noqa: BLE001 - one bad endpoint must not abort
            logger.warning("Enrichment %s failed for %s: %s", label, activity_id, exc)
            return None


def get_source(settings: Settings | None = None) -> ActivitySource:
    """Return the configured source: Garmin if credentials exist, else demo."""
    settings = settings or get_settings()
    if settings.garmin_enabled:
        return GarminSource(settings)
    return DemoSource()
