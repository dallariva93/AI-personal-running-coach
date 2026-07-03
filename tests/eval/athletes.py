"""Synthetic athletes for the eval harness (Roadmap A9).

A :class:`SyntheticAthlete` is a compact, deterministic description of a runner:
level, baseline weekly volume, HRV pattern and injury proneness. The simulator
turns it into a real athlete profile, a load history and day-by-day check-ins so
the coaching pipeline can be exercised end to end without any live data.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas import AthleteProfile, Goal


@dataclass(frozen=True)
class SyntheticAthlete:
    """A deterministic runner archetype driving one simulation.

    ``hrv_pattern`` and ``injury_prone`` steer the seeded history and check-ins;
    ``weekly_km`` anchors the baseline volume the plan and load are built from.
    """

    key: str
    level: str  # beginner | intermediate | advanced
    weekly_km: float
    hrv_pattern: str  # stable | declining | suppressed
    injury_prone: bool
    risk_tolerance: str = "moderate"

    def profile(self, goal: Goal) -> AthleteProfile:
        """Build the athlete profile the pipeline consumes for this scenario."""
        return AthleteProfile(
            level=self.level,
            risk_tolerance=self.risk_tolerance,
            weekly_runs=5,
            max_hr=190,
            resting_hr=50,
            goal=goal,
        )


# Five archetypes spanning levels and recovery/injury patterns. Combined with
# the readiness patterns and phases in the scenario matrix they produce the
# 50 deterministic scenarios required by the brief.
ATHLETES: list[SyntheticAthlete] = [
    SyntheticAthlete("beginner_stable", "beginner", 25.0, "stable", False, "conservative"),
    SyntheticAthlete("intermediate_stable", "intermediate", 45.0, "stable", False),
    SyntheticAthlete("advanced_stable", "advanced", 80.0, "stable", False, "aggressive"),
    SyntheticAthlete("intermediate_injury_prone", "intermediate", 45.0, "stable", True),
    SyntheticAthlete("intermediate_hrv_declining", "intermediate", 50.0, "declining", False),
]
