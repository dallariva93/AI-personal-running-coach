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

from app.collection.synthesize import extract_details_enrichment, synthesize
from app.config import Settings, get_settings
from app.exceptions import CollectionError
from app.logging_config import get_logger
from app.schemas import RunSummary
from app.utils import retry_call

logger = get_logger("app.collection")

_DEMO_DATA = Path(__file__).resolve().parent.parent.parent / "data" / "demo_activities.json"


class ActivitySource(Protocol):
    """Anything that can return a list of synthesised runs."""

    def get_recent_runs(self, limit: int = 10) -> list[RunSummary]: ...


def _is_running(activity: dict[str, Any]) -> bool:
    type_field = activity.get("activityType", {})
    type_key = type_field.get("typeKey", "") if isinstance(type_field, dict) else str(type_field)
    return "running" in type_key.lower()


class DemoSource:
    """Returns bundled sample runs. Always available, no network, no cost."""

    def __init__(self, path: Path | str = _DEMO_DATA) -> None:
        self.path = Path(path)

    def get_recent_runs(self, limit: int = 10) -> list[RunSummary]:
        if not self.path.exists():
            return []
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        runs = [synthesize(a) for a in raw if _is_running(a)]
        runs.sort(key=lambda r: r.date, reverse=True)
        return runs[:limit]


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

    def get_recent_runs(self, limit: int = 10) -> list[RunSummary]:
        try:
            client = self._login()
            activities = retry_call(
                lambda: client.get_activities(0, max(limit * 3, limit)),
                retries=self.settings.garmin_max_retries,
                description="garmin.get_activities",
            )
        except Exception as exc:  # network, auth, library breakage
            logger.error("Garmin fetch failed: %s", exc)
            raise CollectionError(f"Impossibile scaricare i dati da Garmin: {exc}") from exc
        running = [a for a in activities if _is_running(a)]
        running.sort(key=lambda a: str(a.get("startTimeLocal", "")), reverse=True)
        running = running[:limit]
        runs: list[RunSummary] = []
        for activity in running:
            run = synthesize(activity)
            extras = self._fetch_enrichment(client, activity.get("activityId"))
            if extras:
                run = run.model_copy(update=extras)
            runs.append(run)
        return runs

    def _fetch_enrichment(self, client: Any, activity_id: Any) -> dict[str, Any]:
        """Fetch the per-activity fields that only live on the details endpoint.

        Currently: user-entered RPE and stamina drop. One extra API call per
        activity; rate-limit failures are swallowed (warning logged) so a
        transient 429 leaves those fields unset rather than aborting the
        whole ingest.
        """
        if activity_id is None:
            return {}
        try:
            details = retry_call(
                lambda: client.get_activity(activity_id),
                retries=self.settings.garmin_max_retries,
                description=f"garmin.get_activity({activity_id})",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Details enrich failed for %s: %s", activity_id, exc)
            return {}
        return extract_details_enrichment(details or {})


def get_source(settings: Settings | None = None) -> ActivitySource:
    """Return the configured source: Garmin if credentials exist, else demo."""
    settings = settings or get_settings()
    if settings.garmin_enabled:
        return GarminSource(settings)
    return DemoSource()
