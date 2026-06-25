"""Load and persist the athlete's structured profile + goal.

Single-athlete app: the profile lives in one singleton row (``id == 1``). These
helpers convert between the ORM row and the :class:`~app.schemas.AthleteProfile`
Pydantic model that the rest of the code (metrics, prompts) reasons over.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AthleteProfileRow
from app.schemas import AthletePhysiology, AthleteProfile, Goal, HRZones, Race

_SINGLETON_ID = 1


def _row_to_profile(row: AthleteProfileRow) -> AthleteProfile:
    goal = None
    if row.goal_type or row.goal_target_date:
        goal = Goal(
            goal_type=row.goal_type or "general",
            target_date=row.goal_target_date,
            target_time=row.goal_target_time,
            priority=row.goal_priority or "A",
        )
    return AthleteProfile(
        age=row.age,
        sex=row.sex,
        height_cm=row.height_cm,
        weight_kg=row.weight_kg,
        experience_years=row.experience_years,
        max_hr=row.max_hr,
        resting_hr=row.resting_hr,
        weekly_runs=row.weekly_runs,
        level=row.level or "intermediate",
        risk_tolerance=row.risk_tolerance or "moderate",
        available_days=row.available_days or [],
        zones=HRZones(**row.zones) if row.zones else None,
        physiology=AthletePhysiology(**row.physiology) if row.physiology else None,
        goal=goal,
        races=[Race(**r) for r in (row.races or [])],
        notes=row.notes,
    )


def get_profile_row(session: Session) -> AthleteProfileRow | None:
    return session.scalar(
        select(AthleteProfileRow).where(AthleteProfileRow.id == _SINGLETON_ID)
    )


def get_profile(session: Session) -> AthleteProfile | None:
    """Return the stored profile, or None when it hasn't been set up yet."""
    row = get_profile_row(session)
    return _row_to_profile(row) if row else None


def save_profile(session: Session, profile: AthleteProfile) -> AthleteProfileRow:
    """Insert or update the singleton profile row from a Pydantic model."""
    row = get_profile_row(session)
    if row is None:
        row = AthleteProfileRow(id=_SINGLETON_ID)
        session.add(row)

    row.age = profile.age
    row.sex = profile.sex
    row.height_cm = profile.height_cm
    row.weight_kg = profile.weight_kg
    row.experience_years = profile.experience_years
    row.max_hr = profile.max_hr
    row.resting_hr = profile.resting_hr
    row.weekly_runs = profile.weekly_runs
    row.level = profile.level
    row.risk_tolerance = profile.risk_tolerance
    row.available_days = profile.available_days or None
    row.zones = profile.zones.model_dump(exclude_none=True) if profile.zones else None
    row.physiology = (
        profile.physiology.model_dump(exclude_none=True) if profile.physiology else None
    )
    row.races = [r.model_dump(exclude_none=True) for r in profile.races] or None
    if profile.goal:
        row.goal_type = profile.goal.goal_type
        row.goal_target_date = profile.goal.target_date
        row.goal_target_time = profile.goal.target_time
        row.goal_priority = profile.goal.priority
    else:
        row.goal_type = row.goal_target_date = row.goal_target_time = row.goal_priority = None
    row.notes = profile.notes
    session.flush()
    return row
