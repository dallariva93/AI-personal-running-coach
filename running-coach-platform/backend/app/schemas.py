"""Pydantic schemas shared across collection, processing and coaching modules.

These form the stable contract between the three independent layers:
- collection produces ``RunSummary`` objects,
- processing turns a list of them into ``TrainingMetrics``,
- coaching consumes both and returns ``CoachingResult``.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

ACTIVITY_TYPES = ("easy", "tempo", "intervalli", "lungo", "recupero", "gara", "altro")


class RunSummary(BaseModel):
    """Compact, LLM-friendly representation of one running activity."""

    model_config = ConfigDict(extra="ignore")

    garmin_activity_id: str | None = None
    date: str  # ISO YYYY-MM-DD
    activity_type: str = "easy"
    duration_min: float = 0.0
    distance_km: float = 0.0
    avg_pace: str | None = None
    avg_hr: int | None = None
    max_hr: int | None = None
    elevation_gain_m: float | None = None
    avg_cadence: int | None = None
    rpe: int | None = None
    notes: str | None = None
    hr_zones: dict[str, float] | None = None
    splits_km: list[str] | None = None


class TrainingMetrics(BaseModel):
    """Derived training-load and form metrics for a window of activities."""

    runs_count: int = 0
    total_distance_km: float = 0.0
    total_duration_min: float = 0.0
    weekly_distance_km: float = 0.0
    acute_load_km: float = 0.0  # last 7 days
    chronic_load_km: float = 0.0  # last 28 days (weekly average)
    acwr: float | None = None  # acute:chronic workload ratio
    monotony: float | None = None  # weekly load monotony (mean/std of daily load)
    easy_ratio: float | None = None  # fraction of easy/recovery volume (target ~0.8)
    form_state: str = "unknown"  # fresh | balanced | fatigued | detraining | unknown
    form_explanation: str = ""
    load_trend: str = "stable"  # rising | stable | falling
    week_start: str | None = None


class WeeklyBucket(BaseModel):
    """Aggregated stats for a single ISO week (used by the dashboard chart)."""

    week_start: str
    distance_km: float = 0.0
    duration_min: float = 0.0
    runs: int = 0


class CoachingResult(BaseModel):
    """Output of the coaching layer."""

    scope: str = "single"  # single | weekly
    model: str = "offline"
    analysis: str = ""
    next_workout: str = ""

    def as_markdown(self) -> str:
        return f"## Analisi\n\n{self.analysis}\n\n## Prossimo allenamento\n\n{self.next_workout}\n"


class ActivityOut(BaseModel):
    """API response model for a stored activity."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    garmin_activity_id: str | None
    date: str
    activity_type: str
    duration_min: float
    distance_km: float
    avg_pace: str | None
    avg_hr: int | None
    max_hr: int | None
    elevation_gain_m: float | None
    avg_cadence: int | None
    rpe: int | None
    notes: str | None


class ReportOut(BaseModel):
    """API response model for a coaching report."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    activity_id: int | None
    scope: str
    model: str
    analysis: str
    next_workout: str
    metrics: dict | None = None
    created_at: str | None = None


class ManualActivityIn(BaseModel):
    """Payload for manually creating an activity via the API."""

    date: str
    activity_type: str = Field(default="easy")
    duration_min: float = 0.0
    distance_km: float = 0.0
    avg_hr: int | None = None
    rpe: int | None = None
    notes: str | None = None
