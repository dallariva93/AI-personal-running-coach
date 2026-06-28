"""Service layer for workout templates."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import WorkoutSegment, WorkoutTemplate
from app.schemas import (
    AthleteProfile,
    TrainingMetrics,
    WorkoutSegmentIn,
    WorkoutSuggestRequest,
    WorkoutTemplateIn,
    WorkoutTemplateOut,
)


def create_workout(db: Session, data: WorkoutTemplateIn) -> WorkoutTemplateOut:
    """Compute estimated totals, persist and return the template."""
    est_dist, est_dur = _compute_estimates(data.segments)

    template = WorkoutTemplate(
        name=data.name,
        description=data.description,
        type=data.type,
        estimated_distance_km=est_dist,
        estimated_duration_min=est_dur,
        created_at=datetime.now(UTC),
    )
    db.add(template)
    db.flush()

    for seg_in in data.segments:
        seg = WorkoutSegment(
            workout_id=template.id,
            position=seg_in.position,
            segment_type=seg_in.segment_type,
            repetitions=seg_in.repetitions,
            work_duration_sec=seg_in.work_duration_sec,
            work_distance_km=seg_in.work_distance_km,
            work_pace=seg_in.work_pace,
            rest_duration_sec=seg_in.rest_duration_sec,
            rest_type=seg_in.rest_type,
            notes=seg_in.notes,
        )
        db.add(seg)

    db.flush()
    db.refresh(template)
    return WorkoutTemplateOut.model_validate(template)


def list_workouts(db: Session) -> list[WorkoutTemplateOut]:
    """Return all templates, newest first."""
    rows = db.scalars(
        select(WorkoutTemplate).order_by(WorkoutTemplate.created_at.desc())
    ).all()
    return [WorkoutTemplateOut.model_validate(r) for r in rows]


def get_workout(db: Session, workout_id: int) -> WorkoutTemplateOut | None:
    """Return a single template by ID, or None."""
    row = db.get(WorkoutTemplate, workout_id)
    if row is None:
        return None
    return WorkoutTemplateOut.model_validate(row)


def delete_workout(db: Session, workout_id: int) -> bool:
    """Delete template (cascade deletes segments). Returns False if not found."""
    row = db.get(WorkoutTemplate, workout_id)
    if row is None:
        return False
    db.delete(row)
    db.flush()
    return True


def suggest_and_save(
    db: Session,
    request: WorkoutSuggestRequest,
    coach,
    metrics: TrainingMetrics | None,
    profile: AthleteProfile | None,
) -> WorkoutTemplateOut:
    """Call coach.suggest_workout(), persist, and return the template."""
    template_in: WorkoutTemplateIn = coach.suggest_workout(request, metrics, profile)
    return create_workout(db, template_in)


# ── internal helpers ──────────────────────────────────────────────────────────

_EASY_PACE_MIN_PER_KM = 6.0  # fallback pace for warmup/cooldown with duration only


def _pace_str_to_min_per_km(pace: str | None) -> float:
    """Parse 'M:SS/km' → minutes per km. Returns _EASY_PACE_MIN_PER_KM on failure."""
    if not pace:
        return _EASY_PACE_MIN_PER_KM
    try:
        p = pace.replace("/km", "").strip()
        parts = p.split(":")
        return int(parts[0]) + int(parts[1]) / 60.0
    except (IndexError, ValueError):
        return _EASY_PACE_MIN_PER_KM


def _compute_estimates(
    segments: list[WorkoutSegmentIn],
) -> tuple[float | None, float | None]:
    """Compute total estimated distance (km) and duration (min) from segments.

    Strategy per segment:
    - If work_distance_km is given: use it for distance; derive duration from pace.
    - Else if work_duration_sec is given: derive distance from pace; use duration directly.
    - rest: rest_duration_sec * repetitions (no distance).
    Multiply each segment's per-rep totals by repetitions.
    """
    total_dist_km = 0.0
    total_dur_min = 0.0

    for seg in segments:
        reps = max(1, seg.repetitions)
        pace_min = _pace_str_to_min_per_km(seg.work_pace)

        if seg.work_distance_km is not None:
            seg_dist = seg.work_distance_km * reps
            seg_dur = seg.work_distance_km * pace_min * reps
        elif seg.work_duration_sec is not None:
            seg_dur = (seg.work_duration_sec / 60.0) * reps
            seg_dist = (seg.work_duration_sec / 60.0) / pace_min * reps
        else:
            seg_dist = 0.0
            seg_dur = 0.0

        # Add rest time (per rep * reps, no distance)
        if seg.rest_duration_sec is not None:
            seg_dur += (seg.rest_duration_sec / 60.0) * reps

        total_dist_km += seg_dist
        total_dur_min += seg_dur

    if total_dist_km == 0.0 and total_dur_min == 0.0:
        return None, None
    dist = round(total_dist_km, 2) if total_dist_km > 0 else None
    dur = round(total_dur_min, 1) if total_dur_min > 0 else None
    return dist, dur
