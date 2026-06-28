"""ORM models for activities and coaching reports."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Activity(Base):
    """A single running activity, synthesised from Garmin into a compact form."""

    __tablename__ = "activities"
    __table_args__ = (
        UniqueConstraint("garmin_activity_id", name="uq_activity_garmin_id"),
        UniqueConstraint("strava_activity_id", name="uq_activity_strava_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Garmin's own activity id (string for safety). Nullable for manual entries.
    garmin_activity_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    # Strava's activity id, when the run arrived via the Strava webhook source.
    strava_activity_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

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
    aerobic_training_effect: Mapped[float | None] = mapped_column(Float, nullable=True)
    anaerobic_training_effect: Mapped[float | None] = mapped_column(Float, nullable=True)
    aerobic_te_message: Mapped[str | None] = mapped_column(String(64), nullable=True)
    anaerobic_te_message: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # GPS / elevation profile (populated when Garmin split data is available).
    altitude_profile: Mapped[list | None] = mapped_column(JSON, nullable=True)
    route_polyline: Mapped[str | None] = mapped_column(Text, nullable=True)

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
    level: Mapped[str | None] = mapped_column(String(16), nullable=True)
    risk_tolerance: Mapped[str | None] = mapped_column(String(16), nullable=True)

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


class RawActivityAsset(Base):
    """A raw payload archived to object storage for one Garmin activity.

    One row per ``(garmin_activity_id, kind)`` pair. Decoupled from
    :class:`Activity` (no FK) on purpose: we archive every Garmin activity
    (running and non-running) but only persist running summaries in
    ``activities``. Stored on object storage; the row keeps the pointer
    (``s3_key``), checksum and a copy of any tiny inline content type
    metadata for fast listing without touching the bucket.

    ``kind`` values currently emitted by :mod:`app.collection.garmin_raw`:

    * ``summary``                - get_activity JSON
    * ``details``                - get_activity_details JSON (per-second streams)
    * ``splits``                 - get_activity_splits JSON
    * ``typed_splits``           - get_activity_typed_splits JSON
    * ``split_summaries``        - get_activity_split_summaries JSON
    * ``weather``                - get_activity_weather JSON
    * ``hr_in_timezones``        - get_activity_hr_in_timezones JSON
    * ``power_in_timezones``     - get_activity_power_in_timezones JSON
    * ``exercise_sets``          - get_activity_exercise_sets JSON
    * ``gear``                   - get_activity_gear JSON
    * ``gpx``                    - download_activity GPX
    * ``tcx``                    - download_activity TCX
    * ``original_fit_zip``       - download_activity ORIGINAL (FIT inside zip)
    """

    __tablename__ = "raw_activity_assets"
    __table_args__ = (
        UniqueConstraint("garmin_activity_id", "kind", name="uq_raw_asset_activity_kind"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    garmin_activity_id: Mapped[str] = mapped_column(String(64), index=True)
    # Garmin's typeKey (running, cycling, ...). Kept for listing/filtering
    # without joining back to a heterogeneous source.
    activity_type_key: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(32))
    s3_key: Mapped[str] = mapped_column(String(512))
    content_type: Mapped[str] = mapped_column(String(64), default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<RawActivityAsset {self.garmin_activity_id}/{self.kind}>"


class StravaAccount(Base):
    """OAuth tokens for one connected Strava athlete.

    Single-athlete app → effectively one row, keyed on the Strava ``athlete_id``.
    Strava access tokens are short-lived (6 h); ``expires_at`` (epoch seconds)
    drives the refresh, performed lazily before each API call.
    """

    __tablename__ = "strava_accounts"
    __table_args__ = (UniqueConstraint("athlete_id", name="uq_strava_athlete_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    athlete_id: Mapped[int] = mapped_column(Integer, index=True)
    access_token: Mapped[str] = mapped_column(String(128))
    refresh_token: Mapped[str] = mapped_column(String(128))
    expires_at: Mapped[int] = mapped_column(Integer, default=0)  # epoch seconds
    scope: Mapped[str | None] = mapped_column(String(128), nullable=True)
    athlete_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<StravaAccount athlete={self.athlete_id}>"


class StravaWebhookEvent(Base):
    """Durable inbox for Strava push events — our lightweight job queue.

    The webhook handler must respond within ~2 s, so it only validates and
    persists the event here, then returns 200. A worker drains pending rows
    out-of-band (fetch the activity, map it, upsert). Persisting first makes
    the pipeline robust to restarts and to slow/failed downstream calls.
    """

    __tablename__ = "strava_webhook_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    object_type: Mapped[str] = mapped_column(String(16))  # activity | athlete
    object_id: Mapped[int] = mapped_column(Integer, index=True)  # Strava activity id
    aspect_type: Mapped[str] = mapped_column(String(16))  # create | update | delete
    owner_id: Mapped[int] = mapped_column(Integer, index=True)  # athlete id
    event_time: Mapped[int] = mapped_column(Integer, default=0)  # epoch from Strava
    updates: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # field changes
    status: Mapped[str] = mapped_column(
        String(16), default="pending", index=True
    )  # pending | done | error | skipped
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<StravaWebhookEvent {self.aspect_type} {self.object_id} {self.status}>"


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


class TrainingPlan(Base):
    """A multi-week structured training plan generated by the coach."""

    __tablename__ = "training_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    goal_type: Mapped[str] = mapped_column(String(64))
    goal_date: Mapped[str] = mapped_column(String(10))
    goal_time: Mapped[str | None] = mapped_column(String(16), nullable=True)
    level: Mapped[str] = mapped_column(String(32), default="intermediate")
    weeks_total: Mapped[int] = mapped_column(Integer)
    start_date: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(16), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    weeks: Mapped[list[TrainingPlanWeek]] = relationship(
        back_populates="plan",
        cascade="all, delete-orphan",
        order_by="TrainingPlanWeek.week_number",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<TrainingPlan {self.goal_type} {self.goal_date} status={self.status}>"


class TrainingPlanWeek(Base):
    """One week in a multi-week training plan."""

    __tablename__ = "training_plan_weeks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("training_plans.id", ondelete="CASCADE"), index=True
    )
    week_number: Mapped[int] = mapped_column(Integer)
    phase: Mapped[str] = mapped_column(String(32))
    target_km: Mapped[float] = mapped_column(Float)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    plan: Mapped[TrainingPlan] = relationship(back_populates="weeks")
    sessions: Mapped[list[TrainingPlanSession]] = relationship(
        back_populates="week",
        cascade="all, delete-orphan",
        order_by="TrainingPlanSession.day_of_week",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<TrainingPlanWeek {self.week_number} phase={self.phase}>"


class TrainingPlanSession(Base):
    """A single session (or rest day) within one week of a training plan."""

    __tablename__ = "training_plan_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    week_id: Mapped[int] = mapped_column(
        ForeignKey("training_plan_weeks.id", ondelete="CASCADE"), index=True
    )
    day_of_week: Mapped[int] = mapped_column(Integer)  # 0=Mon, 6=Sun
    session_type: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_distance_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_pace: Mapped[str | None] = mapped_column(String(16), nullable=True)
    target_duration_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    week: Mapped[TrainingPlanWeek] = relationship(back_populates="sessions")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<TrainingPlanSession day={self.day_of_week} {self.session_type}>"
