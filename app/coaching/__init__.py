"""Coaching layer: turn runs + metrics into analysis and a next workout.

Two backends, selected automatically:
* :class:`AICoach` — calls Claude when an API key is configured.
* :class:`OfflineCoach` — deterministic, rule-based fallback (no key, no cost).

Both implement the same :class:`Coach` interface, so callers never branch.
"""

from app.coaching.coach import AICoach, Coach, OfflineCoach, get_coach

__all__ = ["AICoach", "Coach", "OfflineCoach", "get_coach"]
