"""Personal-record computation from stored Activity rows.

Works directly on ORM objects (not RunSummary) so each PR can carry the
activity_id back to the caller.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.db.models import Activity


def _pace_sec(pace: str | None) -> float:
    """Parse "M:SS/km" → seconds per km. Returns inf on bad input."""
    if not pace:
        return float("inf")
    try:
        clean = pace.replace("/km", "").strip()
        m, s = clean.split(":")
        return int(m) * 60 + int(s)
    except Exception:
        return float("inf")


def compute_personal_records(activities: list[Activity]) -> list[dict]:
    """Return a list of PR dicts (distance, pace, date, activity_id).

    Distances checked:
      - 1K   segment: fastest_split_1k across all activities
      - 5K   segment: fastest_split_5k across all activities
      - 5K   race: best avg_pace on 4.8–5.5 km runs
      - 10K  race: best avg_pace on 9.5–10.8 km runs
      - 21K  half:  best avg_pace on 20–22.5 km runs
      - 42K  marathon: best avg_pace on 41–43.5 km runs
    """
    prs: list[dict] = []

    def _best(candidates: list[Activity], pace_fn) -> Activity | None:
        valid = [a for a in candidates if pace_fn(a) < float("inf")]
        return min(valid, key=pace_fn) if valid else None

    # 1 km segment PR
    b = _best(activities, lambda a: _pace_sec(a.fastest_split_1k))
    if b:
        prs.append(
            {"distance": "1K", "pace": b.fastest_split_1k, "date": b.date, "activity_id": b.id}
        )

    # 5 km segment PR (from Garmin split data)
    b = _best(activities, lambda a: _pace_sec(a.fastest_split_5k))
    if b:
        prs.append(
            {
                "distance": "5K split",
                "pace": b.fastest_split_5k,
                "date": b.date,
                "activity_id": b.id,
            }
        )

    # 5 km race PR
    b = _best(
        [a for a in activities if 4.8 <= a.distance_km <= 5.5],
        lambda a: _pace_sec(a.avg_pace),
    )
    if b:
        prs.append({"distance": "5K", "pace": b.avg_pace, "date": b.date, "activity_id": b.id})

    # 10 km race PR
    b = _best(
        [a for a in activities if 9.5 <= a.distance_km <= 10.8],
        lambda a: _pace_sec(a.avg_pace),
    )
    if b:
        prs.append({"distance": "10K", "pace": b.avg_pace, "date": b.date, "activity_id": b.id})

    # Half marathon PR
    b = _best(
        [a for a in activities if 20.0 <= a.distance_km <= 22.5],
        lambda a: _pace_sec(a.avg_pace),
    )
    if b:
        prs.append({"distance": "21K", "pace": b.avg_pace, "date": b.date, "activity_id": b.id})

    # Marathon PR
    b = _best(
        [a for a in activities if 41.0 <= a.distance_km <= 43.5],
        lambda a: _pace_sec(a.avg_pace),
    )
    if b:
        prs.append({"distance": "42K", "pace": b.avg_pace, "date": b.date, "activity_id": b.id})

    return prs
