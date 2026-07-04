"""Episodic memory v0 (Roadmap A8, bridge to N10): durable athlete facts.

After each chat exchange a small Haiku extractor pulls *durable* facts about the
athlete out of the user's message ("corre di solito la mattina", "fastidio
ricorrente al polpaccio destro") and stores one row per fact. The chat system
prompt injects them back, so the coach remembers across sessions.

Same discipline as every LLM surface in this codebase: the call is injectable
(``call_fn``) for tests, gated on the API key, parsed defensively, and entirely
best-effort — a failure can never break the chat.
"""

from __future__ import annotations

import json
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.coaching import prompts
from app.config import Settings, get_settings
from app.db.models import CoachMemory
from app.logging_config import get_logger

logger = get_logger("app.services.coach_memory")

_MAX_FACTS = 30  # keep the memory small: oldest rows beyond this are pruned
_MAX_FACT_LEN = 200


def list_memory_facts(db: Session, limit: int = 10) -> list[str]:
    """Most recently touched facts first, for the system prompt."""
    rows = db.scalars(
        select(CoachMemory).order_by(CoachMemory.updated_at.desc()).limit(limit)
    ).all()
    return [r.fact for r in rows]


def _normalise(fact: str) -> str:
    return re.sub(r"\s+", " ", fact).strip().lower().rstrip(".")


def _parse_facts(raw: str) -> list[str]:
    """Defensive parse of the extractor's JSON array of strings."""
    text = raw.strip()
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        return []
    data = json.loads(text[start:end + 1])
    if not isinstance(data, list):
        return []
    out: list[str] = []
    for item in data:
        fact = str(item).strip()
        if fact and len(fact) <= _MAX_FACT_LEN:
            out.append(fact)
    return out[:5]  # at most a handful per exchange


def maybe_update_memory(
    db: Session,
    user_text: str,
    *,
    settings: Settings | None = None,
    call_fn=None,
) -> list[str]:
    """Extract durable facts from ``user_text`` and upsert them. Best-effort.

    Returns the facts actually stored (new or refreshed). No key and no
    injected ``call_fn`` → no-op, so the offline path never touches the
    network. Any model/parse error is swallowed: memory is an enhancement,
    never a dependency.
    """
    settings = settings or get_settings()
    if call_fn is None:
        if not settings.ai_enabled:
            return []
        from app.coaching.coach import AICoach

        coach = AICoach(settings)
        call_fn = lambda s, u: coach._call(  # noqa: E731 - tiny adapter
            s, u, settings.chat_router_model, max_tokens=200
        )

    try:
        facts = _parse_facts(call_fn(prompts.MEMORY_EXTRACT_SYSTEM_PROMPT, user_text))
    except Exception as exc:  # noqa: BLE001 - memory must never break the chat
        logger.info("Memory extraction failed (ignored): %s", exc)
        return []
    if not facts:
        return []

    existing = {_normalise(r.fact): r for r in db.scalars(select(CoachMemory)).all()}
    stored: list[str] = []
    for fact in facts:
        row = existing.get(_normalise(fact))
        if row is not None:
            row.fact = fact  # refresh phrasing + updated_at (onupdate)
            db.add(row)
        else:
            db.add(CoachMemory(fact=fact))
        stored.append(fact)
    db.flush()

    # Prune: keep the memory bounded, dropping the least recently touched.
    rows = db.scalars(
        select(CoachMemory).order_by(CoachMemory.updated_at.desc())
    ).all()
    for stale in rows[_MAX_FACTS:]:
        db.delete(stale)
    db.flush()
    return stored
