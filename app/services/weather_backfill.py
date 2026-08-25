"""Fill in the weather Garmin never recorded.

Most watches report no temperature, so ``temperature_c`` arrives empty on
almost every activity — and a coach without it reads August as a loss of form.
This walks the stored runs, asks Open-Meteo what the weather was at each run's
own start point and hour, and fills the gaps.

Deliberately a separate pass, like the lap enrichment: it is one network call
per run, it is never required for the app to work, and it must be re-runnable
in batches without redoing anything.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.collection.weather import fetch_weather, start_coordinates
from app.config import get_settings
from app.db.models import Activity
from app.logging_config import get_logger

logger = get_logger("app.services.weather_backfill")

# Open-Meteo's free tier is generous but not infinite; runs are spread over
# months so this is only ever a courtesy pause.
THROTTLE_S = 0.3


@dataclass
class WeatherFillResult:
    """What a fill run did."""

    considered: int = 0
    filled: int = 0
    no_location: int = 0
    no_data: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "considered": self.considered,
            "filled": self.filled,
            "no_location": self.no_location,
            "no_data": self.no_data,
            "errors": self.errors,
        }


def _fallback_location(session: Session) -> tuple[float, float] | None:
    """Home coordinates, or the start of the most recent GPS run.

    Used for activities recorded without GPS (treadmill, lost fix). Less
    accurate than the run's own start, but for temperature a few kilometres
    make no practical difference.
    """
    settings = get_settings()
    if settings.home_lat is not None and settings.home_lon is not None:
        return (settings.home_lat, settings.home_lon)
    row = session.scalar(
        select(Activity)
        .where(Activity.sport == "run", Activity.route_polyline.is_not(None))
        .order_by(Activity.date.desc())
        .limit(1)
    )
    return start_coordinates(row.route_polyline) if row is not None else None


def fill_missing_weather(
    session: Session,
    *,
    limit: int = 200,
    throttle_s: float = THROTTLE_S,
    use_fallback_location: bool = True,
    ref: date | None = None,
    fetch: Any = None,
    progress: Callable[[str], None] | None = None,
) -> WeatherFillResult:
    """Fill ``temperature_c`` / ``humidity_pct`` where Garmin left them empty.

    Only touches rows that are missing the data, so re-running is cheap and
    never overwrites a real measurement from the watch.
    """
    result = WeatherFillResult()
    rows = list(
        session.scalars(
            select(Activity)
            .where(
                or_(Activity.temperature_c.is_(None), Activity.humidity_pct.is_(None)),
                # Never invent weather for a treadmill run: it has no GPS, so
                # the fallback location would attach the street's temperature
                # to a session done in an air-conditioned gym. A wrong-but-
                # plausible number is worse than a missing one — it is exactly
                # what makes a coach blame the heat for an indoor pace.
                Activity.is_indoor.is_(False),
            )
            .order_by(Activity.date.desc())
            .limit(limit)
        ).all()
    )
    if not rows:
        _emit(progress, "Nessuna corsa senza meteo.")
        return result

    fallback = _fallback_location(session) if use_fallback_location else None
    _emit(progress, f"Cerco il meteo per {len(rows)} attività…")

    for row in rows:
        result.considered += 1
        coords = start_coordinates(row.route_polyline) or fallback
        if coords is None:
            result.no_location += 1
            continue

        weather = fetch_weather(
            coords[0], coords[1], row.date, row.start_time, ref=ref, fetch=fetch
        )
        if not weather:
            result.no_data += 1
            time.sleep(throttle_s)
            continue

        # Never overwrite what the watch actually measured.
        if row.temperature_c is None and "temperature_c" in weather:
            row.temperature_c = weather["temperature_c"]
        if row.humidity_pct is None and "humidity_pct" in weather:
            row.humidity_pct = weather["humidity_pct"]
        result.filled += 1
        if result.filled % 25 == 0:
            session.commit()
            _emit(progress, f"…{result.filled}/{len(rows)} completate")
        time.sleep(throttle_s)

    session.commit()
    logger.info("Weather fill: %s", result.as_dict())
    return result


def _emit(progress: Callable[[str], None] | None, message: str) -> None:
    if progress is not None:
        progress(message)
    else:
        logger.info(message)
