"""ORM models for activities and coaching reports."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Activity(Base):
    """A single running activity, synthesised from Garmin into a compact form."""

    __tablename__ = "activities"
    __table_args__ = (UniqueConstraint("garmin_activity_id", name="uq_activity_garmin_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Garmin's own activity id (string for safety). Nullable for manual entries.
    garmin_activity_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    date: Mapped[str] = mapped_column(String(10), index=True)  # ISO date YYYY-MM-DD
    activity_type: Mapped[str] = mapped_column(String(32), default="easy")  # easy/tempo/...
    duration_min: Mapped[float] = mapped_column(Float, default=0.0)
    distance_km: Mapped[float] = mapped_column(Float, default=0.0)
    avg_pace: Mapped[str | None] = mapped_column(String(16), nullable=True)  # "5:18/km"
    avg_hr: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_hr: Mapped[int | None] = mapped_column(Integer, nullable=True)
    elevation_gain_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_cadence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rpe: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1-10, optional
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Semi-structured extras kept as JSON: hr zones, splits, etc.
    hr_zones: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    splits_km: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Environment (GAP 18) and trail (GAP 20) extras.
    temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    humidity_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    elevation_loss_m: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Garmin-derived rich metrics (filled by the details enrichment step).
    garmin_training_load: Mapped[float | None] = mapped_column(Float, nullable=True)
    vigorous_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
    moderate_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
    body_battery_delta: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stamina_drop: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_grade_adjusted_pace: Mapped[str | None] = mapped_column(String(16), nullable=True)
    fastest_split_1k: Mapped[str | None] = mapped_column(String(16), nullable=True)
    fastest_split_5k: Mapped[str | None] = mapped_column(String(16), nullable=True)
    vo2max: Mapped[float | None] = mapped_column(Float, nullable=True)
    aerobic_te_message: Mapped[str | None] = mapped_column(String(64), nullable=True)
    anaerobic_te_message: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    reports: Mapped[list[CoachingReport]] = relationship(
        back_populates="activity", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Activity {self.date} {self.activity_type} {self.distance_km}km>"


class AthleteProfileRow(Base):
    """The athlete's structured profile, goal, zones and thresholds.

    Single-athlete app → a singleton row (``id == 1``). Flat scalar columns for
    the common fields (easy to edit from a form) and JSON for the nested zones /
    physiology blobs. See :class:`app.schemas.AthleteProfile`.
    """

    __tablename__ = "athlete_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sex: Mapped[str | None] = mapped_column(String(16), nullable=True)
    height_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    experience_years: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_hr: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resting_hr: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weekly_runs: Mapped[int | None] = mapped_column(Integer, nullable=True)

    available_days: Mapped[list | None] = mapped_column(JSON, nullable=True)
    zones: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    physiology: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    races: Mapped[list | None] = mapped_column(JSON, nullable=True)  # B/C races (GAP 16)

    # Goal (denormalised for querying / display / periodization).
    goal_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    goal_target_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    goal_target_time: Mapped[str | None] = mapped_column(String(16), nullable=True)
    goal_priority: Mapped[str | None] = mapped_column(String(4), nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<AthleteProfileRow goal={self.goal_type} target={self.goal_target_date}>"


class CoachingReport(Base):
    """The AI (or rule-based) coaching output tied to an activity or a week."""

    __tablename__ = "coaching_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    activity_id: Mapped[int | None] = mapped_column(
        ForeignKey("activities.id", ondelete="CASCADE"), nullable=True, index=True
    )
    scope: Mapped[str] = mapped_column(String(16), default="single")  # single | weekly
    model: Mapped[str] = mapped_column(String(64), default="offline")
    analysis: Mapped[str] = mapped_column(Text, default="")
    next_workout: Mapped[str] = mapped_column(Text, default="")
    # Snapshot of the metrics that informed this report (form, load, ACWR...).
    metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)

    activity: Mapped[Activity | None] = relationship(back_populates="reports")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<CoachingReport {self.scope} model={self.model}>"


class DailyCheckinRow(Base):
    """A subjective daily wellness check-in (GAP 9). One row per date."""

    __tablename__ = "daily_checkins"
    __table_args__ = (UniqueConstraint("date", name="uq_checkin_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[str] = mapped_column(String(10), index=True)  # ISO YYYY-MM-DD
    sleep_h: Mapped[float | None] = mapped_column(Float, nullable=True)
    fatigue: Mapped[int | None] = mapped_column(Integer, nullable=True)
    soreness: Mapped[int | None] = mapped_column(Integer, nullable=True)
    motivation: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<DailyCheckin {self.date} fatigue={self.fatigue}>"
