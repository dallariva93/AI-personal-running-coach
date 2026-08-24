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
from app.db.models import NutritionDay, NutritionItem, YazioAccount, YazioProduct
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
    items_saved: int = 0
    products_resolved: int = 0
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
            "items_saved": self.items_saved,
            "products_resolved": self.products_resolved,
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
    row.energy_goal_kcal = payload.get("energy_goal_kcal")
    row.synced_at = datetime.now(UTC)
    return row


def sync_nutrition(
    session: Session,
    *,
    start: date | None = None,
    end: date | None = None,
    days: int = DEFAULT_LOOKBACK_DAYS,
    throttle_s: float = THROTTLE_S,
    with_items: bool = True,
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
    # Per-run product-name memo, on top of the cache table: a backfill sees the
    # same foods over and over.
    cache: dict[str, str | None] = {}

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
                # Only for days that actually have totals: no totals means
                # nothing was logged, so the second request would come back
                # empty. Halves the calls on a long backfill.
                if with_items:
                    try:
                        sync_items_for_day(
                            session, token, day, result, cache=cache, request=request
                        )
                    except Exception as exc:  # noqa: BLE001 - detail is optional
                        # The day's totals are already saved; losing the item
                        # list is a smaller loss than losing the day.
                        logger.warning("Diario Yazio del %s non importato: %s", day, exc)
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


# ── the item-by-item diary ───────────────────────────────────────────────────


def _product_name(
    session: Session,
    token: str,
    product_id: str,
    *,
    cache: dict[str, str | None],
    request: Any = None,
) -> tuple[str | None, bool]:
    """Resolve a product id to a name. Returns ``(name, was_fetched)``.

    Three layers, cheapest first: this run's dict, the cache table, then Yazio.
    Products repeat heavily across days, so after the first backfill this is
    almost always a local hit.
    """
    if product_id in cache:
        return cache[product_id], False

    row = session.scalars(
        select(YazioProduct).where(YazioProduct.product_id == product_id)
    ).first()
    if row is not None:
        cache[product_id] = row.name
        return row.name, False

    try:
        product = yazio.fetch_product(token, product_id, request=request)
    except Exception as exc:  # noqa: BLE001 - an unnamed item is still an item
        logger.warning("Prodotto Yazio %s non risolto: %s", product_id, exc)
        cache[product_id] = None
        return None, False

    if product is None:
        cache[product_id] = None
        return None, True

    session.add(
        YazioProduct(
            product_id=product_id,
            name=product["name"][:255],
            producer=(product.get("producer") or None),
        )
    )
    session.flush()
    cache[product_id] = product["name"]
    return product["name"], True


def upsert_item(session: Session, payload: dict[str, Any]) -> NutritionItem:
    """Insert or update one diary entry, keyed on Yazio's own entry id."""
    row = session.scalars(
        select(NutritionItem).where(NutritionItem.yazio_id == payload["yazio_id"])
    ).first()
    if row is None:
        row = NutritionItem(yazio_id=payload["yazio_id"])
        session.add(row)
    row.date = payload["date"]
    row.meal = payload.get("meal")
    row.name = (payload.get("name") or None) and str(payload["name"])[:500]
    row.product_id = payload.get("product_id")
    row.amount = payload.get("amount")
    row.serving = payload.get("serving")
    row.energy_kcal = payload.get("energy_kcal")
    row.synced_at = datetime.now(UTC)
    return row


def sync_items_for_day(
    session: Session,
    token: str,
    day: date,
    result: NutritionSyncResult,
    *,
    cache: dict[str, str | None],
    request: Any = None,
) -> None:
    """Import one day's diary entries, resolving product names as needed.

    Deletes the day's stored entries that Yazio no longer reports: a meal
    removed in the app must disappear here too, or the log slowly fills with
    food that was never eaten.
    """
    entries = yazio.fetch_consumed(token, day, request=request)
    day_str = day.isoformat()

    seen: set[str] = set()
    for entry in entries:
        if entry.get("product_id") and not entry.get("name"):
            name, fetched = _product_name(
                session, token, entry["product_id"], cache=cache, request=request
            )
            entry["name"] = name
            if fetched:
                result.products_resolved += 1
        upsert_item(session, entry)
        seen.add(entry["yazio_id"])
        result.items_saved += 1

    stale = session.scalars(
        select(NutritionItem).where(NutritionItem.date == day_str)
    ).all()
    for row in stale:
        if row.yazio_id not in seen:
            session.delete(row)


def food_log(session: Session, day: date | str) -> list[NutritionItem]:
    """The stored diary entries for one day."""
    day_str = day.isoformat() if isinstance(day, date) else str(day)
    return list(
        session.scalars(
            select(NutritionItem)
            .where(NutritionItem.date == day_str)
            .order_by(NutritionItem.meal, NutritionItem.id)
        ).all()
    )
