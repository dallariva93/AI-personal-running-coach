"""Yazio orchestration: token lifecycle + daily nutrition import.

Glue between the low-level :mod:`app.collection.yazio` client and our database,
mirroring :mod:`app.services.strava_sync`:

1. **Token lifecycle** — the password is used once at connect time, then only
   the refresh token keeps the session alive. Tokens are encrypted at rest.
2. **Import** — one aggregate row per day, re-runnable in batches and never
   destructive: a day that comes back empty leaves whatever we already had.

Everything is best-effort by design. Nutrition is context, not a dependency:
the app must keep working, with a coach that simply says nothing about fuelling,
when Yazio is down, disconnected, or has changed its unofficial API again.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collection import yazio
from app.db.models import NutritionDay, YazioAccount
from app.exceptions import CollectionError
from app.logging_config import get_logger

logger = get_logger("app.services.yazio_sync")

# Courtesy pause between day requests — an unofficial API deserves gentler
# treatment than a documented one.
THROTTLE_S = 0.3
# How far back a plain `sync_nutrition()` looks: enough to catch days logged
# late, short enough to stay a cheap nightly call.
DEFAULT_LOOKBACK_DAYS = 7


# ── account / token lifecycle ────────────────────────────────────────────────


def get_account(session: Session) -> YazioAccount | None:
    """The connected Yazio account (single-athlete app → one row)."""
    return session.scalars(select(YazioAccount).limit(1)).first()


def is_connected(session: Session) -> bool:
    return get_account(session) is not None


def _save_tokens(
    session: Session, tokens: dict[str, Any], *, username: str | None = None
) -> YazioAccount:
    account = get_account(session)
    if account is None:
        account = YazioAccount()
        session.add(account)

    account.access_token = tokens["access_token"]
    if tokens.get("refresh_token"):
        account.refresh_token = tokens["refresh_token"]
    elif not account._refresh_token:  # noqa: SLF001 - first save must have one
        raise CollectionError("Yazio non ha restituito un refresh token.")
    account.expires_at = int(time.time()) + int(tokens.get("expires_in") or 3600)
    if username:
        account.username = username
    session.flush()
    return account


def connect_account(
    session: Session, username: str, password: str, *, request: Any = None
) -> YazioAccount:
    """Log in once and store the resulting tokens. The password stops here.

    Raises :class:`CollectionError` on bad credentials — the user is waiting to
    know whether the connection worked, so this is the one Yazio path that must
    fail loudly.
    """
    tokens = yazio.login(username, password, request=request)
    account = _save_tokens(session, tokens, username=username)
    session.commit()
    logger.info("Yazio collegato come %s", username)
    return account


def disconnect_account(session: Session) -> bool:
    """Drop the tokens, keep the imported history.

    Deliberately asymmetric: revoking access should not destroy months of
    nutrition data that is already ours and still useful to the coach.
    """
    account = get_account(session)
    if account is None:
        return False
    session.delete(account)
    session.commit()
    return True


def valid_access_token(
    session: Session, account: YazioAccount, *, request: Any = None
) -> str:
    """A non-expired access token, refreshed lazily just before it is needed."""
    if account.expires_at - yazio.REFRESH_SKEW_S > int(time.time()):
        return account.access_token
    logger.info("Refresh del token Yazio")
    tokens = yazio.refresh(account.refresh_token, request=request)
    _save_tokens(session, tokens)
    session.commit()
    return account.access_token


# ── import ───────────────────────────────────────────────────────────────────


@dataclass
class NutritionSyncResult:
    """What an import run did."""

    considered: int = 0
    saved: int = 0
    empty: int = 0
    # Distinct from `empty` on purpose: a diary with nothing logged and an API
    # rejecting every call are opposite problems that used to report the same
    # number.
    failed: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "considered": self.considered,
            "saved": self.saved,
            "empty": self.empty,
            "failed": self.failed,
            "errors": self.errors,
        }


def upsert_day(session: Session, payload: dict[str, Any]) -> NutritionDay:
    """Insert or update one day of totals, keyed on the date."""
    day_str = str(payload["date"])
    row = session.scalars(
        select(NutritionDay).where(NutritionDay.date == day_str)
    ).first()
    if row is None:
        row = NutritionDay(date=day_str)
        session.add(row)
    row.energy_kcal = payload.get("energy_kcal")
    row.protein_g = payload.get("protein_g")
    row.carbs_g = payload.get("carbs_g")
    row.fat_g = payload.get("fat_g")
    row.water_ml = payload.get("water_ml")
    row.synced_at = datetime.now(UTC)
    return row


def sync_nutrition(
    session: Session,
    *,
    start: date | None = None,
    end: date | None = None,
    days: int = DEFAULT_LOOKBACK_DAYS,
    throttle_s: float = THROTTLE_S,
    request: Any = None,
    progress: Callable[[str], None] | None = None,
) -> NutritionSyncResult:
    """Import a window of days from Yazio.

    Defaults to the last ``days`` days, which is what a nightly run wants: it
    re-reads recent dates on purpose, because a diary entry added two days late
    is normal and a one-shot import would miss it forever.
    """
    result = NutritionSyncResult()
    account = get_account(session)
    if account is None:
        _emit(progress, "Yazio non collegato.")
        return result

    end = end or date.today()
    start = start or (end - timedelta(days=days - 1))
    if start > end:
        start, end = end, start

    try:
        token = valid_access_token(session, account, request=request)
    except CollectionError as exc:
        # An expired refresh token means the user must reconnect; that is worth
        # reporting, not worth crashing the caller (often the ingest pipeline).
        result.errors.append(str(exc))
        logger.warning("Token Yazio non rinnovabile: %s", exc)
        return result

    total = (end - start).days + 1
    _emit(progress, f"Importo {total} giorni di alimentazione da Yazio…")

    day = start
    while day <= end:
        result.considered += 1
        try:
            payload = yazio.fetch_day(token, day, request=request)
        except Exception as exc:  # noqa: BLE001 - one bad day must not stop the rest
            result.failed += 1
            # Only the first few: ninety identical rejections say nothing ninety
            # times, and the caller reads this in a terminal.
            if len(result.errors) < 3:
                result.errors.append(f"{day.isoformat()}: {exc}")
        else:
            if payload is None:
                result.empty += 1
            else:
                upsert_day(session, payload)
                result.saved += 1
                if result.saved % 25 == 0:
                    session.commit()
                    _emit(progress, f"…{result.saved}/{total} salvati")
        day += timedelta(days=1)
        if day <= end:
            time.sleep(throttle_s)

    session.commit()
    logger.info("Sync nutrizione: %s", result.as_dict())
    return result


def try_sync_nutrition(session: Session, **kwargs: Any) -> NutritionSyncResult:
    """Best-effort wrapper for the ingest pipeline.

    Nutrition must never be able to fail a run import: the run is the data we
    cannot re-fetch on the next pass, the nutrition is.
    """
    try:
        return sync_nutrition(session, **kwargs)
    except Exception as exc:  # noqa: BLE001 - nutrition is never worth a failure
        logger.warning("Sync nutrizione saltato: %s", exc)
        return NutritionSyncResult(errors=[str(exc)])


def recent_nutrition(
    session: Session, start: date | str, end: date | str
) -> list[NutritionDay]:
    """Stored days in ``[start, end]``, oldest first."""
    start_s = start.isoformat() if isinstance(start, date) else str(start)
    end_s = end.isoformat() if isinstance(end, date) else str(end)
    return list(
        session.scalars(
            select(NutritionDay)
            .where(NutritionDay.date >= start_s, NutritionDay.date <= end_s)
            .order_by(NutritionDay.date)
        ).all()
    )


def _emit(progress: Callable[[str], None] | None, message: str) -> None:
    if progress is not None:
        progress(message)
    else:
        logger.info(message)
