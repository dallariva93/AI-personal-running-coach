"""Domain exception hierarchy.

Keeping a small, explicit set of exceptions lets the API layer map failures to
clean HTTP responses and lets callers distinguish *recoverable* integration
errors (Garmin/Claude down) from programming errors.
"""

from __future__ import annotations


class CoachError(Exception):
    """Base class for all application-level errors."""


class CollectionError(CoachError):
    """Raised when activity data cannot be collected (e.g. Garmin unreachable)."""


class CoachingError(CoachError):
    """Raised when the AI coaching call fails irrecoverably."""


class ConfigurationError(CoachError):
    """Raised when required configuration is missing or invalid."""
