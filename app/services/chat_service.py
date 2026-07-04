"""Conversational AI coach service — Feature 23.

Persists multi-turn sessions and routes messages through the AI coach.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.coaching.coach import get_coach
from app.coaching.prompts import build_chat_system
from app.db.models import ChatMessage, ChatSession
from app.logging_config import get_logger
from app.schemas import (
    AthleteProfile,
    ChatMessageOut,
    ChatSendResponse,
    ChatSessionOut,
    TrainingMetrics,
)

logger = get_logger("app.services.chat_service")

_HISTORY_LIMIT = 20  # last N messages passed as context


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _session_to_out(session: ChatSession) -> ChatSessionOut:
    return ChatSessionOut(
        id=session.id,
        title=session.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
        message_count=len(session.messages),
    )


def list_sessions(db: Session) -> list[ChatSessionOut]:
    sessions = (
        db.query(ChatSession)
        .order_by(ChatSession.updated_at.desc())
        .limit(50)
        .all()
    )
    return [_session_to_out(s) for s in sessions]


def get_messages(db: Session, session_id: int) -> list[ChatMessageOut]:
    session = db.get(ChatSession, session_id)
    if session is None:
        return []
    return [ChatMessageOut.model_validate(m) for m in session.messages]


def delete_session(db: Session, session_id: int) -> bool:
    session = db.get(ChatSession, session_id)
    if session is None:
        return False
    db.delete(session)
    db.commit()
    return True


def _auto_title(first_user_message: str) -> str:
    """Generate a short title from the first user message."""
    text = first_user_message.strip()
    if len(text) <= 60:
        return text
    return text[:57] + "..."


def send_message(
    db: Session,
    user_text: str,
    session_id: int | None,
    profile: AthleteProfile | None,
    metrics: TrainingMetrics | None,
    recent_runs_raw: list | None = None,  # RunSummary objects (attribute access)
    active_plan_week: dict | None = None,
) -> ChatSendResponse:
    """Persist a user message, call the AI coach, persist the reply.

    Creates a new session when session_id is None.
    Returns the structured response including model routing info.
    """
    # Get or create session
    if session_id is not None:
        chat_session = db.get(ChatSession, session_id)
        if chat_session is None:
            chat_session = ChatSession(created_at=_utcnow(), updated_at=_utcnow())
            db.add(chat_session)
            db.flush()
    else:
        chat_session = ChatSession(created_at=_utcnow(), updated_at=_utcnow())
        db.add(chat_session)
        db.flush()

    # Set title from first user message
    if not chat_session.title or chat_session.title == "Nuova chat":
        if not db.query(ChatMessage).filter_by(session_id=chat_session.id).first():
            chat_session.title = _auto_title(user_text)

    # Persist user message
    user_msg = ChatMessage(
        session_id=chat_session.id,
        role="user",
        content=user_text,
        created_at=_utcnow(),
    )
    db.add(user_msg)
    db.flush()

    # Load conversation history (last N messages before the one we just added)
    history_rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == chat_session.id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    messages = [{"role": m.role, "content": m.content} for m in history_rows]
    # Trim to last _HISTORY_LIMIT (keep the most recent user message always)
    if len(messages) > _HISTORY_LIMIT:
        messages = messages[-_HISTORY_LIMIT:]

    # Build system prompt with current context
    recent_runs = recent_runs_raw or []
    system = build_chat_system(profile, metrics, recent_runs, active_plan_week)

    # Route + call AI
    coach = get_coach()
    reply_text, model_used, tier = coach.chat_message(messages, system)

    # Persist AI reply
    ai_msg = ChatMessage(
        session_id=chat_session.id,
        role="assistant",
        content=reply_text,
        model_used=model_used,
        tier=tier,
        created_at=_utcnow(),
    )
    db.add(ai_msg)

    chat_session.updated_at = _utcnow()
    db.commit()

    logger.info(
        "Chat session=%d tier=%s model=%s chars=%d",
        chat_session.id, tier, model_used, len(reply_text),
    )

    return ChatSendResponse(
        session_id=chat_session.id,
        session_title=chat_session.title,
        reply=reply_text,
        model_used=model_used,
        tier=tier,
    )
