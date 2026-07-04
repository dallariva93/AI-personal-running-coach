"""Streak and badge computation.

Works on ORM Activity rows. Pure functions, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.db.models import Activity


def compute_streak(
    activities: list[Activity],
    rest_dates: set[date] | None = None,
) -> tuple[int, int]:
    """Return (current_streak_days, best_streak_days).

    A streak increments on consecutive calendar days with at least one run.
    Planned rest days (``rest_dates``) do not break the streak: a gap that
    coincides with a rest day is bridged (P0-8).
    The current streak is still alive if the last run was today or yesterday.
    """
    if not activities:
        return 0, 0

    rest = rest_dates or set()
    unique = sorted(
        {date.fromisoformat(a.date) for a in activities},
        reverse=True,
    )
    today = date.today()

    def _bridge_gap(prev_d: date, d: date) -> bool:
        """True if every day between d and prev_d (exclusive) is a rest day."""
        if prev_d - d <= timedelta(days=1):
            return True
        check = d + timedelta(days=1)
        while check < prev_d:
            if check not in rest:
                return False
            check += timedelta(days=1)
        return True

    # Current streak — must include today or yesterday to still be "live".
    current = 0
    if unique and unique[0] >= today - timedelta(days=1):
        expected = unique[0]
        for d in unique:
            if d == expected:
                current += 1
                expected -= timedelta(days=1)
            elif d < expected and _bridge_gap(expected + timedelta(days=1), d):
                current += 1
                expected = d - timedelta(days=1)
            else:
                break

    # Best-ever streak (scan whole history).
    best = max(current, 1 if unique else 0)
    run = 1
    for i in range(1, len(unique)):
        if _bridge_gap(unique[i - 1], unique[i]):
            run += 1
            best = max(best, run)
        else:
            run = 1

    return current, best


@dataclass
class AdherenceDay:
    """One calendar day's plan-adherence signal (Roadmap Q4).

    ``has_session`` and ``prescribed_rest`` are mutually exclusive: a day is
    either a prescribed workout, a prescribed rest day, or neither (not
    covered by any plan on that date — treated as neutral, see
    :func:`compute_adherence_streak`).
    """

    day: date
    has_session: bool = False
    execution_status: str | None = None  # only meaningful when has_session
    prescribed_rest: bool = False
    ran_hard: bool = False  # a non-easy activity landed on a prescribed rest day


def _day_state(d: AdherenceDay) -> bool | None:
    """True = adherent (extends the streak), False = broken, None = no plan
    coverage that day — skipped over, neither extends nor breaks (bridged,
    same spirit as rest-day bridging in :func:`compute_streak`)."""
    if d.has_session:
        # None = not yet evaluated (today, or predates the execution engine):
        # benefit of the doubt, only an explicit "skipped" breaks the streak.
        return d.execution_status != "skipped"
    if d.prescribed_rest:
        return not d.ran_hard
    return None  # no prescription that day — doesn't count as plan-honoured work


def compute_adherence_streak(days: list[AdherenceDay]) -> tuple[int, int]:
    """Return ``(current_streak_days, best_streak_days)`` of plan adherence.

    Unlike :func:`compute_streak` (which counts running days), this counts
    *calendar* days where the athlete honoured the plan: did the prescribed
    session (or rest was genuinely rest). A prescribed rest day with only an
    easy run does not break the streak; a ``skipped`` prescribed session does.
    Days with no plan coverage at all (e.g. before the plan started) are
    bridged — they neither extend nor break an existing streak.
    """
    if not days:
        return 0, 0

    ordered = sorted(days, key=lambda d: d.day)
    states = [_day_state(d) for d in ordered]

    best = 0
    run = 0
    for state in states:
        if state is None:
            continue
        if state:
            run += 1
            best = max(best, run)
        else:
            run = 0

    current = 0
    for state in reversed(states):
        if state is None:
            continue
        if not state:
            break
        current += 1

    return current, best


def compute_adherence_pct(days: list[AdherenceDay]) -> float | None:
    """% of plan-covered days honoured in ``days`` (Roadmap A6 weekly recap).

    Same day-state logic as :func:`compute_adherence_streak` (a prescribed
    session must not be ``skipped``; a prescribed rest day must not have been
    run hard), but expressed as a percentage over the window rather than a
    streak length. ``None`` when no day in the window carries any plan
    prescription (e.g. no plan was active that week).
    """
    covered = [s for d in days if (s := _day_state(d)) is not None]
    if not covered:
        return None
    return round(100.0 * sum(1 for s in covered if s) / len(covered), 0)


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
        {
            "id": "first_run",
            "label": "Prima corsa",
            "earned": True,
            "earned_date": sorted_asc[0].date,
        }
    )

    # Distance milestones.
    cum_km = 0.0
    milestone_idx = 0
    milestone_dates: dict[int, str] = {}
    for a in sorted_asc:
        cum_km += a.distance_km
        while (
            milestone_idx < len(_DISTANCE_MILESTONES)
            and cum_km >= _DISTANCE_MILESTONES[milestone_idx][0]
        ):
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
        {
            "id": "first_trail",
            "label": "Primo trail",
            "earned": trail is not None,
            "earned_date": trail.date if trail else None,
        }
    )

    # First race.
    race = next((a for a in sorted_asc if a.activity_type == "gara"), None)
    badges.append(
        {
            "id": "first_race",
            "label": "Prima gara",
            "earned": race is not None,
            "earned_date": race.date if race else None,
        }
    )

    # Half marathon / marathon completion.
    half = next((a for a in sorted_asc if 20.0 <= a.distance_km <= 22.5), None)
    marathon = next((a for a in sorted_asc if 41.0 <= a.distance_km <= 43.5), None)
    badges.append(
        {
            "id": "half_marathon",
            "label": "Mezza maratona completata",
            "earned": half is not None,
            "earned_date": half.date if half else None,
        }
    )
    badges.append(
        {
            "id": "marathon",
            "label": "Maratona completata",
            "earned": marathon is not None,
            "earned_date": marathon.date if marathon else None,
        }
    )

    # Streak milestones (based on best-ever).
    for threshold, label in _STREAK_MILESTONES:
        badges.append(
            {
                "id": f"streak_{threshold}",
                "label": label,
                "earned": best_streak >= threshold,
                "earned_date": None,
            }
        )

    return badges
