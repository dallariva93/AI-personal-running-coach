"""Streak and badge computation.

Works on ORM Activity rows. Pure functions, no I/O.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.db.models import Activity


def compute_streak(activities: list[Activity]) -> tuple[int, int]:
    """Return (current_streak_days, best_streak_days).

    A streak increments on consecutive calendar days with at least one run.
    The current streak is still alive if the last run was today or yesterday.
    """
    if not activities:
        return 0, 0

    unique = sorted(
        {date.fromisoformat(a.date) for a in activities},
        reverse=True,
    )
    today = date.today()

    # Current streak — must include today or yesterday to still be "live".
    current = 0
    if unique and unique[0] >= today - timedelta(days=1):
        expected = unique[0]
        for d in unique:
            if d == expected:
                current += 1
                expected -= timedelta(days=1)
            else:
                break

    # Best-ever streak (scan whole history).
    best = max(current, 1 if unique else 0)
    run = 1
    for i in range(1, len(unique)):
        if unique[i - 1] - unique[i] == timedelta(days=1):
            run += 1
            best = max(best, run)
        else:
            run = 1

    return current, best


_DISTANCE_MILESTONES = [
    (100, "100 km percorsi"),
    (500, "500 km percorsi"),
    (1000, "1.000 km percorsi"),
    (5000, "5.000 km percorsi"),
]
_STREAK_MILESTONES = [
    (7, "7 giorni di fila"),
    (30, "30 giorni di fila"),
]


def compute_badges(
    activities: list[Activity],
    current_streak: int,
    best_streak: int,
) -> list[dict]:
    """Return a list of badge dicts (id, label, earned, earned_date)."""
    badges: list[dict] = []
    if not activities:
        return badges

    total_km = sum(a.distance_km for a in activities)
    sorted_asc = sorted(activities, key=lambda a: a.date)

    # First run (everyone earns this on day 1).
    badges.append(
        {"id": "first_run", "label": "Prima corsa", "earned": True, "earned_date": sorted_asc[0].date}
    )

    # Distance milestones.
    cum_km = 0.0
    milestone_idx = 0
    milestone_dates: dict[int, str] = {}
    for a in sorted_asc:
        cum_km += a.distance_km
        while milestone_idx < len(_DISTANCE_MILESTONES) and cum_km >= _DISTANCE_MILESTONES[milestone_idx][0]:
            milestone_dates[_DISTANCE_MILESTONES[milestone_idx][0]] = a.date
            milestone_idx += 1
    for km, label in _DISTANCE_MILESTONES:
        badges.append(
            {
                "id": f"{km}km",
                "label": label,
                "earned": total_km >= km,
                "earned_date": milestone_dates.get(km),
            }
        )

    # First trail run.
    trail = next((a for a in sorted_asc if a.activity_type == "trail"), None)
    badges.append(
        {"id": "first_trail", "label": "Primo trail", "earned": trail is not None, "earned_date": trail.date if trail else None}
    )

    # First race.
    race = next((a for a in sorted_asc if a.activity_type == "gara"), None)
    badges.append(
        {"id": "first_race", "label": "Prima gara", "earned": race is not None, "earned_date": race.date if race else None}
    )

    # Half marathon / marathon completion.
    half = next((a for a in sorted_asc if 20.0 <= a.distance_km <= 22.5), None)
    marathon = next((a for a in sorted_asc if 41.0 <= a.distance_km <= 43.5), None)
    badges.append(
        {"id": "half_marathon", "label": "Mezza maratona completata", "earned": half is not None, "earned_date": half.date if half else None}
    )
    badges.append(
        {"id": "marathon", "label": "Maratona completata", "earned": marathon is not None, "earned_date": marathon.date if marathon else None}
    )

    # Streak milestones (based on best-ever).
    for threshold, label in _STREAK_MILESTONES:
        badges.append(
            {"id": f"streak_{threshold}", "label": label, "earned": best_streak >= threshold, "earned_date": None}
        )

    return badges
