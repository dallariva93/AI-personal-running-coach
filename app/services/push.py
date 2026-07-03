"""FCM HTTP v1 push delivery (Roadmap A3).

Sends a push notification to every registered device token via Firebase Cloud
Messaging HTTP v1. The service-account JSON path comes from
``FCM_CREDENTIALS_PATH``; when it is unset the module is a no-op (the
NotificationSyncWorker polling on the device continues to cover delivery).

Design notes:
- Fire-and-forget: callers wrap invocations in try/except so a push failure
  never breaks the coaching pipeline or the DB transaction.
- The OAuth2 access token is cached in-process with a safety margin so we
  sign at most one JWT per hour.
- Retries: up to 2 attempts with exponential backoff on transient HTTP errors
  (5xx, 429, network timeouts).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Device
from app.logging_config import get_logger

logger = get_logger(__name__)

_FCM_ENDPOINT = "https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
_OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
_OAUTH_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
_MAX_RETRIES = 2
_RETRY_BASE_DELAY = 0.5  # seconds

# In-process token cache: (access_token, expiry_epoch).
_token_cache: tuple[str, float] | None = None


def _b64url(data: bytes) -> str:
    import base64

    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _load_service_account(path: str) -> dict:
    raw = Path(path).read_bytes()
    data = json.loads(raw)
    if "private_key" not in data or "client_email" not in data or "project_id" not in data:
        raise ValueError(
            "FCM service-account JSON is missing required fields "
            "(private_key, client_email, project_id)"
        )
    return data


def _sign_jwt(private_key_pem: str, client_email: str) -> str:
    header = {"alg": "RS256", "typ": "JWT"}
    now = int(time.time())
    payload = {
        "iss": client_email,
        "scope": _OAUTH_SCOPE,
        "aud": _OAUTH_TOKEN_URL,
        "iat": now,
        "exp": now + 3600,
    }
    header_b64 = _b64url(json.dumps(header, separators=(",", ":")).encode())
    payload_b64 = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")

    private_key = serialization.load_pem_private_key(
        private_key_pem.encode("utf-8"), password=None
    )
    signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    return f"{header_b64}.{payload_b64}.{_b64url(signature)}"


def _get_access_token(sa: dict) -> str:
    global _token_cache
    if _token_cache is not None:
        token, expiry = _token_cache
        if time.time() < expiry - 60:
            return token

    jwt = _sign_jwt(sa["private_key"], sa["client_email"])
    resp = httpx.post(
        _OAUTH_TOKEN_URL,
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": jwt,
        },
        timeout=10,
    )
    resp.raise_for_status()
    body = resp.json()
    token = body["access_token"]
    expires_in = int(body.get("expires_in", 3600))
    _token_cache = (token, time.time() + expires_in)
    return token


def _all_tokens(db: Session) -> list[str]:
    rows = db.scalars(select(Device.fcm_token)).all()
    return list(rows)


def _build_fcm_message(
    token: str,
    title: str,
    body: str,
    android_priority: str,
    data: dict | None = None,
) -> dict:
    """Assemble the FCM v1 message body (pure — unit-tested).

    ``data`` (e.g. ``{"deep_link": "debrief", "activity_id": "12"}``) is passed
    through as string key/values so the app can deep-link on notification tap
    (A4). Empty/absent data yields a plain notification, unchanged from before.
    """
    message: dict = {
        "token": token,
        "notification": {"title": title, "body": body},
        "android": {"priority": android_priority},
    }
    if data:
        message["data"] = {k: str(v) for k, v in data.items() if v is not None}
    return {"message": message}


def send_to_all(
    db: Session,
    title: str,
    body: str,
    priority: str = "medium",
    data: dict | None = None,
) -> int:
    """Best-effort push to every registered device. Returns the count of
    successful sends. Never raises — logs and returns 0 on failure.

    ``priority`` maps to FCM Android priority: ``high`` → ``HIGH``, anything
    else → ``NORMAL``. ``data`` carries an optional deep-link payload (A4).
    """
    settings = get_settings()
    if not settings.fcm_enabled:
        logger.debug("FCM not configured — skipping push (polling covers delivery)")
        return 0

    tokens = _all_tokens(db)
    if not tokens:
        logger.debug("No registered devices — skipping push")
        return 0

    try:
        sa = _load_service_account(settings.fcm_credentials_path)
    except Exception:
        logger.exception("Failed to load FCM service-account credentials")
        return 0

    android_priority = "HIGH" if priority == "high" else "NORMAL"
    sent = 0
    for token in tokens:
        if _send_one(sa, token, title, body, android_priority, data):
            sent += 1
    return sent


def _send_one(
    sa: dict, token: str, title: str, body: str, android_priority: str,
    data: dict | None = None,
) -> bool:
    endpoint = _FCM_ENDPOINT.format(project_id=sa["project_id"])
    message = _build_fcm_message(token, title, body, android_priority, data)

    for attempt in range(_MAX_RETRIES + 1):
        try:
            access_token = _get_access_token(sa)
            resp = httpx.post(
                endpoint,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                content=json.dumps(message),
                timeout=10,
            )
            if resp.status_code == 200:
                return True
            if resp.status_code in (400, 401, 403):
                logger.error(
                    "FCM rejected message (token may be invalid): %s %s",
                    resp.status_code,
                    resp.text[:200],
                )
                return False
            if resp.status_code < 500 and resp.status_code != 429:
                logger.error("FCM non-retryable error %s: %s", resp.status_code, resp.text[:200])
                return False
        except (httpx.TimeoutException, httpx.NetworkError):
            logger.warning("FCM network error (attempt %d)", attempt + 1)
        except Exception:
            logger.exception("FCM send failed (attempt %d)", attempt + 1)
            return False

        if attempt < _MAX_RETRIES:
            time.sleep(_RETRY_BASE_DELAY * (2**attempt))

    return False


def reset_token_cache() -> None:
    """Clear the in-process OAuth2 token cache (for tests)."""
    global _token_cache
    _token_cache = None
