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

from app.collection.synthesize import synthesize
from app.config import Settings, get_settings
from app.schemas import RunSummary

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
        except Exception:
            client = Garmin(self.settings.garmin_email, self.settings.garmin_password)
            client.login()
            try:
                client.garth.dump(token_store)
            except Exception:
                pass  # token caching is best-effort
        self._client = client
        return client

    def get_recent_runs(self, limit: int = 10) -> list[RunSummary]:
        client = self._login()
        activities = client.get_activities(0, max(limit * 3, limit))
        runs = [synthesize(a) for a in activities if _is_running(a)]
        runs.sort(key=lambda r: r.date, reverse=True)
        return runs[:limit]


def get_source(settings: Settings | None = None) -> ActivitySource:
    """Return the configured source: Garmin if credentials exist, else demo."""
    settings = settings or get_settings()
    if settings.garmin_enabled:
        return GarminSource(settings)
    return DemoSource()
