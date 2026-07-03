"""API-token rotation (Roadmap A10).

``POST /api/auth/rotate`` mints a new bearer token and stores its **SHA-256
hash** in ``sync_state`` — never the token itself, so a leaked DB (the very
threat A10 addresses) cannot leak the credential. Once a rotated hash exists
it *overrides* ``settings.api_token``: the old env token stops working
immediately, and the new token is shown exactly once in the rotate response.

To recover from a lost rotated token: delete the ``api_token_hash`` row from
``sync_state`` (or run the right-to-erasure endpoint, which wipes the table) —
auth then falls back to the ``API_TOKEN`` env var.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import SyncState
from app.logging_config import get_logger

logger = get_logger("app.services.auth")

_HASH_KEY = "api_token_hash"

# Per-process cache so AuthMiddleware doesn't hit the DB on every request.
# `_loaded` distinguishes "not loaded yet" from "loaded, no override".
_cached_hash: str | None = None
_loaded = False


def reset_cache() -> None:
    """Forget the cached hash (tests switching DBs; after erasure)."""
    global _cached_hash, _loaded
    _cached_hash = None
    _loaded = False


def _sha256(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _load_hash() -> str | None:
    """Read the rotated-token hash from sync_state, tolerating a missing table
    (first bootstrap runs before init_db has necessarily created it)."""
    from app.db.database import get_session_factory

    try:
        db = get_session_factory()()
        try:
            row = db.get(SyncState, _HASH_KEY)
            return row.value if row else None
        finally:
            db.close()
    except Exception:  # noqa: BLE001 - no table yet → no override
        return None


def _active_hash() -> str | None:
    global _cached_hash, _loaded
    if not _loaded:
        _cached_hash = _load_hash()
        _loaded = True
    return _cached_hash


def verify_api_token(presented: str, settings: Settings) -> bool:
    """True if ``presented`` is the currently valid API token.

    A rotated token (hash in sync_state) takes precedence and *replaces* the
    env token; with no rotation on record, the env token applies. Both paths
    compare in constant time.
    """
    stored_hash = _active_hash()
    if stored_hash is not None:
        return hmac.compare_digest(_sha256(presented), stored_hash)
    return hmac.compare_digest(presented, settings.api_token)


def rotate_api_token(db: Session) -> str:
    """Mint a new API token, persist only its hash, return it (shown once)."""
    global _cached_hash, _loaded
    token = secrets.token_urlsafe(32)
    digest = _sha256(token)
    row = db.get(SyncState, _HASH_KEY)
    if row is None:
        db.add(SyncState(key=_HASH_KEY, value=digest))
    else:
        row.value = digest
    db.flush()
    _cached_hash = digest
    _loaded = True
    logger.info("API token ruotato: il token precedente non è più valido.")
    return token
