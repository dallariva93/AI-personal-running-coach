"""Fetch and archive the *raw* Garmin payloads for one activity.

Where :mod:`app.collection.synthesize` distils a Garmin activity into the
compact :class:`~app.schemas.RunSummary`, this module keeps the full fidelity:
it pulls every endpoint Garmin exposes for an activity (summary, per-second
detail streams, splits, weather, gear, training-effect zones, GPX/TCX/FIT
downloads) and hands the bytes to an :class:`~app.storage.ObjectStore`.

Everything here is best-effort: any endpoint that the installed
``garminconnect`` version does not support, or that fails for a given
activity, is skipped with a warning rather than aborting the archive.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from app.logging_config import get_logger
from app.storage import ObjectStore, checksum

logger = get_logger(__name__)


@dataclass(frozen=True)
class RawAsset:
    """A single archived payload, ready to be recorded in ``raw_activity_assets``."""

    activity_id: str
    activity_type_key: str | None
    kind: str
    s3_key: str
    content_type: str
    size_bytes: int
    sha256: str | None


# JSON endpoints: kind -> client method name. Each returns a JSON-serialisable
# object that we store pretty-printed as ``<kind>.json``.
_JSON_KINDS: dict[str, str] = {
    "summary": "get_activity",
    "details": "get_activity_details",
    "splits": "get_activity_splits",
    "typed_splits": "get_activity_typed_splits",
    "split_summaries": "get_activity_split_summaries",
    "weather": "get_activity_weather",
    "hr_in_timezones": "get_activity_hr_in_timezones",
    "power_in_timezones": "get_activity_power_in_timezones",
    "exercise_sets": "get_activity_exercise_sets",
    "gear": "get_activity_gear",
}

# Binary downloads via ``download_activity(id, dl_fmt=...)``:
# kind -> (ActivityDownloadFormat attribute, extension, content type).
_DOWNLOAD_KINDS: dict[str, tuple[str, str, str]] = {
    "gpx": ("GPX", "gpx", "application/gpx+xml"),
    "tcx": ("TCX", "tcx", "application/vnd.garmin.tcx+xml"),
    "original_fit_zip": ("ORIGINAL", "zip", "application/zip"),
}


class GarminRawFetcher:
    """Archive every raw payload for an activity into an object store."""

    def __init__(self, client: Any, store: ObjectStore, key_prefix: str = "") -> None:
        self.client = client
        self.store = store
        self.key_prefix = key_prefix.strip("/")

    def fetch_all(
        self,
        activity_id: str,
        activity_type_key: str | None = None,
        already_archived_kinds: Iterable[str] = (),
    ) -> list[RawAsset]:
        """Archive all not-yet-stored kinds for ``activity_id``.

        ``already_archived_kinds`` lets the caller skip payloads recorded on a
        previous sync so re-runs stay cheap and idempotent.
        """
        done = set(already_archived_kinds)
        assets: list[RawAsset] = []

        for kind, method_name in _JSON_KINDS.items():
            if kind in done:
                continue
            asset = self._archive_json(activity_id, activity_type_key, kind, method_name)
            if asset is not None:
                assets.append(asset)

        for kind, (fmt_attr, ext, content_type) in _DOWNLOAD_KINDS.items():
            if kind in done:
                continue
            asset = self._archive_download(
                activity_id, activity_type_key, kind, fmt_attr, ext, content_type
            )
            if asset is not None:
                assets.append(asset)

        return assets

    # -- internals ---------------------------------------------------------

    def _archive_json(
        self,
        activity_id: str,
        activity_type_key: str | None,
        kind: str,
        method_name: str,
    ) -> RawAsset | None:
        method: Callable[..., Any] | None = getattr(self.client, method_name, None)
        if method is None:
            logger.debug("Garmin client lacks %s; skipping kind=%s", method_name, kind)
            return None
        try:
            payload = method(activity_id)
        except Exception as exc:  # noqa: BLE001 - one bad endpoint must not abort
            logger.warning("Raw fetch %s for %s failed: %s", kind, activity_id, exc)
            return None
        if payload is None:
            return None
        data = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        return self._store(
            activity_id, activity_type_key, kind, f"{kind}.json", data, "application/json"
        )

    def _archive_download(
        self,
        activity_id: str,
        activity_type_key: str | None,
        kind: str,
        fmt_attr: str,
        ext: str,
        content_type: str,
    ) -> RawAsset | None:
        download = getattr(self.client, "download_activity", None)
        if download is None:
            return None
        fmt = self._download_format(fmt_attr)
        try:
            data = download(activity_id, dl_fmt=fmt) if fmt is not None else download(activity_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Raw download %s for %s failed: %s", kind, activity_id, exc)
            return None
        if not data:
            return None
        if isinstance(data, str):
            data = data.encode("utf-8")
        return self._store(
            activity_id, activity_type_key, kind, f"{kind}.{ext}", data, content_type
        )

    def _download_format(self, fmt_attr: str) -> Any:
        """Resolve ``Garmin.ActivityDownloadFormat.<fmt_attr>`` if available."""
        enum = getattr(type(self.client), "ActivityDownloadFormat", None)
        if enum is None:
            return None
        return getattr(enum, fmt_attr, None)

    def _store(
        self,
        activity_id: str,
        activity_type_key: str | None,
        kind: str,
        filename: str,
        data: bytes,
        content_type: str,
    ) -> RawAsset:
        parts = (
            [self.key_prefix, str(activity_id), filename]
            if self.key_prefix
            else [str(activity_id), filename]
        )
        key = "/".join(p.strip("/") for p in parts if p)
        self.store.put_bytes(key, data, content_type=content_type)
        return RawAsset(
            activity_id=activity_id,
            activity_type_key=activity_type_key,
            kind=kind,
            s3_key=key,
            content_type=content_type,
            size_bytes=len(data),
            sha256=checksum(data),
        )
