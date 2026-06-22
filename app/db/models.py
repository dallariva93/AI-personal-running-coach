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

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    reports: Mapped[list[CoachingReport]] = relationship(
        back_populates="activity", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Activity {self.date} {self.activity_type} {self.distance_km}km>"


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
