"""At-rest encryption of stored secrets with Fernet (Roadmap A10).

Threat model: the SQLite file (or a Litestream backup of it on S3) leaks.
Secrets stored through this module stay unreadable because the Fernet key
lives *outside* the database — in the ``DATA_ENCRYPTION_KEY`` env var, or in a
key file next to the DB that Litestream does not replicate.

Scope, deliberately: OAuth tokens (Strava) only. Health data (HRV, check-ins,
activities) remains plaintext because every metric computation queries it;
row-level encryption would force decrypt-all-in-Python on each request. The
full at-rest story (SQLCipher / encrypted volume) is planned with the
multi-user migration (G4) — see docs/SECURITY.md.

Encrypted values carry an ``enc:`` prefix so they are self-describing:
``decrypt_secret`` passes legacy plaintext through unchanged, which makes the
data migration idempotent and the getters robust on half-migrated rows.
"""

from __future__ import annotations

from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings
from app.logging_config import get_logger

logger = get_logger("app.security")

_PREFIX = "enc:"
# Fernet instances cached per key string, so tests that swap the key via env
# get a fresh instance instead of a stale module singleton.
_fernet_cache: dict[str, Fernet] = {}


def _resolve_key() -> str:
    """Return the Fernet key: env first, else key file (created on first use).

    Generating a key at bootstrap keeps the app runnable with zero
    configuration (a hard project constraint), at the cost that the key then
    lives on the same volume as the DB — still off the Litestream replica, but
    a full-volume attacker gets both. The warning tells the operator to move
    it to the environment.
    """
    settings = get_settings()
    if settings.data_encryption_key:
        return settings.data_encryption_key.strip()

    key_file = Path(settings.data_encryption_key_file).expanduser()
    if key_file.exists():
        return key_file.read_text(encoding="utf-8").strip()

    key = Fernet.generate_key().decode("ascii")
    key_file.parent.mkdir(parents=True, exist_ok=True)
    key_file.write_text(key + "\n", encoding="utf-8")
    key_file.chmod(0o600)
    logger.warning(
        "DATA_ENCRYPTION_KEY non impostata: chiave generata in %s. In produzione "
        "spostala in una variabile d'ambiente (fly secrets set DATA_ENCRYPTION_KEY=...) "
        "e conserva una copia: senza chiave i token cifrati sono irrecuperabili.",
        key_file,
    )
    return key


def _fernet() -> Fernet:
    key = _resolve_key()
    f = _fernet_cache.get(key)
    if f is None:
        f = Fernet(key.encode("ascii"))
        _fernet_cache[key] = f
    return f


def is_encrypted(value: str | None) -> bool:
    return bool(value) and value.startswith(_PREFIX)


def encrypt_secret(value: str) -> str:
    """Encrypt ``value`` for storage. Idempotent on already-encrypted input."""
    if is_encrypted(value):
        return value
    return _PREFIX + _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str | None) -> str | None:
    """Decrypt a stored value; legacy plaintext passes through unchanged.

    A value that *has* the prefix but does not decrypt (wrong/lost key) raises:
    silently returning ciphertext would leak it to the Strava API as a bearer
    token and produce baffling 401s far from the real cause.
    """
    if value is None or not is_encrypted(value):
        return value
    try:
        return _fernet().decrypt(value[len(_PREFIX):].encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError(
            "Impossibile decifrare un segreto: DATA_ENCRYPTION_KEY assente o "
            "diversa da quella usata per cifrare. Ripristina la chiave originale "
            "o riconnetti l'account Strava."
        ) from exc
