"""API endpoints for workout templates."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.coaching.coach import get_coach
from app.db.database import get_session
from app.processing import compute_metrics
from app.schemas import (
    WorkoutSuggestRequest,
    WorkoutTemplateIn,
    WorkoutTemplateOut,
)
from app.services.checkin import latest_checkin
from app.services.ingest import _all_summaries
from app.services.profile import get_profile
from app.services.workout_service import (
    create_workout,
    delete_workout,
    get_workout,
    list_workouts,
    suggest_and_save,
)

router = APIRouter(prefix="/api", tags=["workouts"])


def _commit(session: Session) -> None:
    session.commit()


@router.post("/workouts", response_model=WorkoutTemplateOut, status_code=201)
def post_workout(
    payload: WorkoutTemplateIn,
    session: Session = Depends(get_session),
) -> WorkoutTemplateOut:
    """Create a new workout template."""
    result = create_workout(session, payload)
    _commit(session)
    refreshed = get_workout(session, result.id)
    return refreshed or result


@router.get("/workouts", response_model=list[WorkoutTemplateOut])
def get_workouts(session: Session = Depends(get_session)) -> list[WorkoutTemplateOut]:
    """List all workout templates, newest first."""
    return list_workouts(session)


@router.get("/workouts/{workout_id}", response_model=WorkoutTemplateOut)
def get_workout_by_id(
    workout_id: int,
    session: Session = Depends(get_session),
) -> WorkoutTemplateOut:
    """Return a single workout template by ID."""
    result = get_workout(session, workout_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Workout non trovato.")
    return result


@router.delete("/workouts/{workout_id}")
def delete_workout_by_id(
    workout_id: int,
    session: Session = Depends(get_session),
) -> dict:
    """Delete a workout template (cascade deletes segments)."""
    ok = delete_workout(session, workout_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Workout non trovato.")
    _commit(session)
    return {"ok": True}


@router.post("/workouts/suggest", response_model=WorkoutTemplateOut, status_code=201)
def post_suggest_workout(
    payload: WorkoutSuggestRequest,
    session: Session = Depends(get_session),
) -> WorkoutTemplateOut:
    """AI-generate a workout and auto-save it to the library."""
    profile = get_profile(session)
    summaries = _all_summaries(session)
    metrics = (
        compute_metrics(summaries, profile=profile, checkin=latest_checkin(session))
        if summaries
        else None
    )
    coach = get_coach()
    try:
        result = suggest_and_save(session, payload, coach, metrics, profile)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _commit(session)
    refreshed = get_workout(session, result.id)
    return refreshed or result
