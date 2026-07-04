"""Conversational AI coach service — Feature 23, unified in A8.

Persists multi-turn sessions and routes messages through the AI coach. One chat
surface, two modes (A8):

* ``general`` — the everyday coach. Its system prompt now also carries the
  coach's *own* recent behaviour (last decisions, diary events, executions) and
  the episodic memory, so it answers citing what it actually did; after each
  exchange a best-effort extractor stores durable athlete facts.
* ``plan_negotiation`` — the pre-plan interview, running through the same chat:
  the negotiation system prompt and the §CTX§/§READY§ flow are untouched, only
  the surface changed. When §READY§ arrives the response carries
  ``plan_ready=True`` + the ``runner_context`` JSON for ``/api/plan/generate``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from datetime import date as _date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.coaching.coach import get_coach
from app.coaching.prompts import build_chat_system
from app.db.models import ChatMessage, ChatSession, CoachDecisionRow, TrainingPlan
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

MODE_GENERAL = "general"
MODE_PLAN = "plan_negotiation"


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _session_to_out(session: ChatSession) -> ChatSessionOut:
    return ChatSessionOut(
        id=session.id,
        title=session.title,
        mode=session.mode or MODE_GENERAL,
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


# ── Coach-context gathering (A8) ─────────────────────────────────────────────


def recent_decisions_context(db: Session, limit: int = 5) -> list[dict]:
    """Last decisions (date + outcome + headline) for the system prompt."""
    rows = db.scalars(
        select(CoachDecisionRow).order_by(CoachDecisionRow.date.desc()).limit(limit)
    ).all()
    return [
        {"date": r.date, "decision": r.decision, "headline": r.headline}
        for r in rows
    ]


def recent_events_context(db: Session, limit: int = 10) -> list[dict]:
    """Last diary events (date + type + title) for the system prompt."""
    from app.services.event_service import recent_events

    return [
        {"date": e.date, "event_type": e.event_type, "title": e.title}
        for e in recent_events(db, days=30, limit=limit)
    ]


def recent_executions_context(db: Session, limit: int = 5) -> list[dict]:
    """Most recent scored plan sessions (date, title, score, status)."""
    plan = db.scalar(select(TrainingPlan).where(TrainingPlan.status == "active"))
    if plan is None:
        return []
    try:
        start = _date.fromisoformat(plan.start_date)
    except (ValueError, TypeError):
        return []
    scored: list[tuple[_date, dict]] = []
    for week in plan.weeks:
        for sess in week.sessions:
            if sess.execution_score is None and sess.execution_status is None:
                continue
            d = start + timedelta(days=(week.week_number - 1) * 7 + sess.day_of_week)
            scored.append((d, {
                "date": d.isoformat(),
                "title": sess.title,
                "score": sess.execution_score,
                "status": sess.execution_status,
            }))
    scored.sort(key=lambda t: t[0], reverse=True)
    return [item for _, item in scored[:limit]]


# ── Send ─────────────────────────────────────────────────────────────────────


def _get_or_create_session(
    db: Session, session_id: int | None, mode: str | None
) -> ChatSession:
    if session_id is not None:
        existing = db.get(ChatSession, session_id)
        if existing is not None:
            return existing
    chat_session = ChatSession(
        created_at=_utcnow(),
        updated_at=_utcnow(),
        mode=mode if mode in (MODE_GENERAL, MODE_PLAN) else MODE_GENERAL,
    )
    db.add(chat_session)
    db.flush()
    return chat_session


def send_message(
    db: Session,
    user_text: str,
    session_id: int | None,
    profile: AthleteProfile | None,
    metrics: TrainingMetrics | None,
    recent_runs_raw: list | None = None,  # RunSummary objects (attribute access)
    active_plan_week: dict | None = None,
    mode: str | None = None,
    memory_call_fn=None,
) -> ChatSendResponse:
    """Persist a user message, call the AI coach, persist the reply.

    ``mode`` is only honoured when this message creates the session; an
    existing session keeps the mode it was born with. ``memory_call_fn`` is the
    injectable LLM call for the episodic-memory extractor (tests).
    """
    chat_session = _get_or_create_session(db, session_id, mode)

    # Set title from first user message
    if not chat_session.title or chat_session.title == "Nuova chat":
        if not db.query(ChatMessage).filter_by(session_id=chat_session.id).first():
            chat_session.title = (
                "Costruzione piano" if chat_session.mode == MODE_PLAN
                else _auto_title(user_text)
            )

    # Persist user message
    user_msg = ChatMessage(
        session_id=chat_session.id,
        role="user",
        content=user_text,
        created_at=_utcnow(),
    )
    db.add(user_msg)
    db.flush()

    # Load conversation history (including the message just added)
    history_rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == chat_session.id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    messages = [{"role": m.role, "content": m.content} for m in history_rows]
    if len(messages) > _HISTORY_LIMIT:
        messages = messages[-_HISTORY_LIMIT:]

    coach = get_coach()
    plan_ready = False
    runner_context: str | None = None

    if chat_session.mode == MODE_PLAN:
        # Plan negotiation (A8): same §CTX§/§READY§ flow, new surface.
        reply_text, plan_ready, runner_context = coach.chat_for_plan(messages)
        model_used, tier = "plan-negotiation", "plan"
    else:
        system = build_chat_system(
            profile,
            metrics,
            recent_runs_raw or [],
            active_plan_week,
            recent_decisions=recent_decisions_context(db),
            recent_events=recent_events_context(db),
            recent_executions=recent_executions_context(db),
            memory_facts=_memory_facts(db),
        )
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

    # Episodic memory (A8): extract durable facts from what the athlete just
    # said. Best-effort and post-commit: a failure can never lose the exchange.
    if chat_session.mode == MODE_GENERAL:
        try:
            from app.services.coach_memory import maybe_update_memory

            maybe_update_memory(db, user_text, call_fn=memory_call_fn)
            db.commit()
        except Exception as exc:  # noqa: BLE001 - memory is an enhancement
            logger.info("Memory update failed (ignored): %s", exc)
            db.rollback()

    logger.info(
        "Chat session=%d mode=%s tier=%s model=%s chars=%d",
        chat_session.id, chat_session.mode, tier, model_used, len(reply_text),
    )

    return ChatSendResponse(
        session_id=chat_session.id,
        session_title=chat_session.title,
        reply=reply_text,
        model_used=model_used,
        tier=tier,
        mode=chat_session.mode or MODE_GENERAL,
        plan_ready=plan_ready,
        runner_context=runner_context,
    )


def _memory_facts(db: Session) -> list[str]:
    from app.services.coach_memory import list_memory_facts

    return list_memory_facts(db)
