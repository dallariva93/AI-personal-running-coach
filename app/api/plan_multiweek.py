"""API endpoints for multi-week training plans."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.coaching.coach import get_coach
from app.db.database import get_session
from app.processing import compute_metrics
from app.schemas import (
    PlanChatRequest,
    PlanChatResponse,
    PlanGenerateRequest,
    PlanSessionOut,
    TrainingPlanOut,
)
from app.services.checkin import latest_checkin
from app.services.ingest import _all_summaries
from app.services.plan_service import (
    archive_plan,
    generate_plan,
    get_current_plan,
    get_plan,
    toggle_session_complete,
)
from app.services.profile import get_profile

router = APIRouter(prefix="/api", tags=["plan-multiweek"])


def _commit(session: Session) -> None:
    session.commit()


@router.post("/plan/chat", response_model=PlanChatResponse)
def post_plan_chat(payload: PlanChatRequest) -> PlanChatResponse:
    """Chat with Haiku to collect runner profile before plan generation."""
    coach = get_coach()
    messages = [{"role": m.role, "content": m.content} for m in payload.messages]
    try:
        message, is_complete, runner_context = coach.chat_for_plan(messages)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return PlanChatResponse(
        message=message, is_complete=is_complete, runner_context=runner_context
    )


@router.post("/plan/generate", response_model=TrainingPlanOut, status_code=201)
def post_generate_plan(
    payload: PlanGenerateRequest,
    session: Session = Depends(get_session),
) -> TrainingPlanOut:
    """Generate and persist a new multi-week training plan."""
    profile = get_profile(session)
    summaries = _all_summaries(session)
    metrics = compute_metrics(
        summaries, profile=profile, checkin=latest_checkin(session)
    ) if summaries else None
    coach = get_coach()
    try:
        plan = generate_plan(session, payload, coach, profile=profile, metrics=metrics)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _commit(session)
    # Re-fetch to ensure IDs are fresh
    refreshed = get_current_plan(session)
    return refreshed or plan


@router.get("/plan/current", response_model=TrainingPlanOut)
def get_current(session: Session = Depends(get_session)) -> TrainingPlanOut:
    """Return the currently active training plan."""
    plan = get_current_plan(session)
    if plan is None:
        raise HTTPException(status_code=404, detail="Nessun piano attivo.")
    return plan


@router.get("/plan/{plan_id}", response_model=TrainingPlanOut)
def get_plan_by_id(
    plan_id: int, session: Session = Depends(get_session)
) -> TrainingPlanOut:
    """Return a training plan by ID."""
    plan = get_plan(session, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Piano non trovato.")
    return plan


@router.patch("/plan/sessions/{session_id}/complete", response_model=PlanSessionOut)
def patch_session_complete(
    session_id: int, session: Session = Depends(get_session)
) -> PlanSessionOut:
    """Toggle the completion status of a training session."""
    try:
        result = toggle_session_complete(session, session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _commit(session)
    return result


@router.delete("/plan/{plan_id}")
def delete_plan(
    plan_id: int, session: Session = Depends(get_session)
) -> dict:
    """Archive (soft-delete) a training plan."""
    ok = archive_plan(session, plan_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Piano non trovato.")
    _commit(session)
    return {"ok": True}
