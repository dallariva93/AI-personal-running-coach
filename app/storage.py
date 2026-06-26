"""Object storage for raw activity archival (Tigris / S3-compatible).

A thin wrapper over an S3-compatible bucket used to archive the raw Garmin
payloads (summary JSON, per-second detail streams, splits, weather, gear,
GPX, TCX, FIT) for *every* activity, not only running ones.

The whole module is optional: ``boto3`` is imported lazily and
:func:`get_object_store` returns ``None`` when no bucket is configured, so the
app keeps running in demo/offline mode with no extra dependency installed.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from typing import TYPE_CHECKING

from app.config import Settings, get_settings
from app.logging_config import get_logger

if TYPE_CHECKING:  # pragma: no cover - typing only
    pass

logger = get_logger(__name__)


class ObjectStore:
    """Minimal put/get/exists wrapper over an S3-compatible bucket.

    ``boto3`` is imported lazily on first use so the dependency is only
    required when raw archival is actually configured and exercised.
    """

    def __init__(
        self,
        *,
        endpoint_url: str,
        region: str,
        access_key_id: str,
        secret_access_key: str,
        bucket: str,
        key_prefix: str = "",
    ) -> None:
        self.endpoint_url = endpoint_url
        self.region = region
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self.bucket = bucket
        self.key_prefix = key_prefix.strip("/")
        self._client = None

    @property
    def client(self):  # noqa: ANN201 - boto3 client is untyped here
        if self._client is None:
            import boto3  # lazy: only needed when archival runs

            self._client = boto3.client(
                "s3",
                endpoint_url=self.endpoint_url or None,
                region_name=self.region or None,
                aws_access_key_id=self.access_key_id or None,
                aws_secret_access_key=self.secret_access_key or None,
            )
        return self._client

    def full_key(self, *parts: str) -> str:
        """Join ``key_prefix`` and the given parts into one object key."""
        pieces = [self.key_prefix, *parts] if self.key_prefix else list(parts)
        return "/".join(p.strip("/") for p in pieces if p)

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:  # noqa: BLE001 - any error means "treat as absent"
            return False

    def put(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Upload ``data`` under ``key`` and return the key."""
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
        return key

    def get(self, key: str) -> bytes:
        resp = self.client.get_object(Bucket=self.bucket, Key=key)
        return resp["Body"].read()


def checksum(data: bytes) -> str:
    """SHA-256 hex digest of ``data`` (used to dedupe / verify archived bytes)."""
    return hashlib.sha256(data).hexdigest()


@lru_cache(maxsize=1)
def get_object_store(settings: Settings | None = None) -> ObjectStore | None:
    """Return a configured :class:`ObjectStore`, or ``None`` when disabled.

    Cached so the boto3 client is reused across ingest calls. The cache is
    keyed on the (singleton) settings instance; call ``get_object_store.cache_clear()``
    in tests that flip the S3 environment.
    """
    settings = settings or get_settings()
    if not settings.s3_enabled:
        logger.debug("Object store disabled: S3 bucket not fully configured")
        return None
    return ObjectStore(
        endpoint_url=settings.s3_endpoint_url,
        region=settings.s3_region,
        access_key_id=settings.s3_access_key_id,
        secret_access_key=settings.s3_secret_access_key,
        bucket=settings.s3_bucket,
        key_prefix=settings.s3_key_prefix,
    )
