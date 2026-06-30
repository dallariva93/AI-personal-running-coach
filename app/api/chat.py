"""Conversational AI coach API — Feature 23."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_session
from app.processing import compute_metrics
from app.schemas import ChatMessageOut, ChatSendRequest, ChatSendResponse, ChatSessionOut
from app.services.chat_service import delete_session, get_messages, list_sessions, send_message
from app.services.checkin import latest_checkin
from app.services.ingest import _all_summaries
from app.services.plan_service import get_current_plan
from app.services.profile import get_profile

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.get("/sessions", response_model=list[ChatSessionOut])
def get_sessions(db: Session = Depends(get_session)) -> list[ChatSessionOut]:
    """List all chat sessions, most recent first."""
    return list_sessions(db)


@router.get("/{session_id}/messages", response_model=list[ChatMessageOut])
def get_session_messages(
    session_id: int,
    db: Session = Depends(get_session),
) -> list[ChatMessageOut]:
    """Return messages for a specific session."""
    return get_messages(db, session_id)


@router.delete("/{session_id}", status_code=204)
def delete_chat_session(
    session_id: int,
    db: Session = Depends(get_session),
) -> None:
    """Delete a chat session and all its messages."""
    if not delete_session(db, session_id):
        raise HTTPException(status_code=404, detail="Sessione non trovata")


@router.post("/send", response_model=ChatSendResponse)
def post_send(
    payload: ChatSendRequest,
    db: Session = Depends(get_session),
) -> ChatSendResponse:
    """Send a user message, get an AI reply, persist both."""
    profile = get_profile(db)
    summaries = _all_summaries(db)
    metrics = (
        compute_metrics(summaries, profile=profile, checkin=latest_checkin(db))
        if summaries
        else None
    )

    # Build recent runs list for context (last 10)
    recent_runs_raw = [
        {
            "date": r.activity_date.isoformat() if r.activity_date else "",
            "type": r.activity_type,
            "distance_km": r.distance_km,
            "avg_pace": r.avg_pace,
            "avg_hr": r.avg_hr,
        }
        for r in summaries[-10:]
    ] if summaries else []

    # Get current plan week for context
    active_plan_week: dict | None = None
    try:
        plan = get_current_plan(db)
        if plan and plan.weeks:
            today = date.today()
            for week in plan.weeks:
                if week.start_date and week.end_date:
                    if week.start_date.date() <= today <= week.end_date.date():
                        active_plan_week = {
                            "week_number": week.week_number,
                            "phase": week.phase,
                            "description": week.description,
                        }
                        break
    except Exception:
        pass

    try:
        return send_message(
            db=db,
            user_text=payload.message,
            session_id=payload.session_id,
            profile=profile,
            metrics=metrics,
            recent_runs_raw=recent_runs_raw,
            active_plan_week=active_plan_week,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
