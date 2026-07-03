"""LLM voice for the daily coaching note (Roadmap A1).

The *facts* stay deterministic (the decision engine decides what to do); this
module only rewrites the human surface — ``decision.daily_note`` — so it reads
fresh and never repeats yesterday's phrasing. Hard rules, enforced in code
after the model answers (not just asked for in the prompt):

* **No invented numbers.** Any number in the rewrite must already appear in the
  decision JSON. A novel number → reject, fall back to the template.
* **No repetition.** If the rewrite matches a note from the last 14 days →
  reject, fall back.
* **At most 2 sentences.** Trimmed, not rejected.

Any error, timeout, empty answer, disabled flag or missing API key returns the
original template note unchanged — the feature can only ever *improve* the note,
never break it. The network call is injectable (``call_fn``) so tests exercise
every guard without touching Anthropic.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from app.config import Settings, get_settings
from app.logging_config import get_logger
from app.schemas import CoachDecision

logger = get_logger("app.coaching.verbalizer")

# A number token: integer, decimal, or a M:SS pace ("4:30").
_NUM_RE = re.compile(r"\d+(?::\d+)?(?:\.\d+)?")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

_SYSTEM_PROMPT = (
    "Sei la voce di un coach di corsa italiano. Riscrivi la nota motivazionale "
    "del giorno in modo naturale, caldo e MAI ripetitivo. Regole ferree:\n"
    "1. Massimo 2 frasi brevi.\n"
    "2. NON inventare numeri: puoi citare solo i valori gia' presenti nei dati "
    "forniti (distanze, passi, giorni). Se non sei sicuro di un numero, non "
    "scriverlo.\n"
    "3. NON riutilizzare nessuna delle formulazioni recenti elencate.\n"
    "4. Resta fedele alla decisione: non contraddire il tipo di seduta.\n"
    "Rispondi SOLO con la nota, senza virgolette ne preamboli."
)


def _numbers_in(text: str) -> set[str]:
    return set(_NUM_RE.findall(text or ""))


def _allowed_numbers(decision: CoachDecision) -> set[str]:
    """Every number the rewrite is permitted to mention: those already in the
    decision's own text and numeric fields."""
    allowed: set[str] = set()
    for field in (
        decision.headline,
        decision.prescription,
        decision.rationale,
        decision.daily_note,
        decision.target_pace,
        *(decision.signals or []),
    ):
        allowed |= _numbers_in(field or "")
    for value in (decision.target_distance_km, decision.target_duration_min):
        if value is not None:
            allowed |= _numbers_in(str(value))
            allowed |= _numbers_in(str(int(value)) if value == int(value) else str(value))
    return allowed


def _normalise(note: str) -> str:
    return re.sub(r"\s+", " ", note).strip().lower().rstrip(".!")


def _trim_to_two_sentences(note: str) -> str:
    parts = _SENTENCE_SPLIT_RE.split(note.strip())
    return " ".join(parts[:2]).strip()


def _passes_guards(candidate: str, decision: CoachDecision, recent_notes: list[str]) -> bool:
    if not candidate:
        return False
    # No invented numbers.
    if not _numbers_in(candidate) <= _allowed_numbers(decision):
        logger.info("Verbalizer rejected: invented number in %r", candidate)
        return False
    # No repetition of a recent note (or of the template it's replacing).
    recent_norm = {_normalise(n) for n in recent_notes if n}
    recent_norm.discard("")
    if _normalise(candidate) in recent_norm:
        logger.info("Verbalizer rejected: repeats a recent note")
        return False
    return True


def _build_user_message(decision: CoachDecision, recent_notes: list[str]) -> str:
    recent = "\n".join(f"- {n}" for n in recent_notes if n) or "(nessuna)"
    return (
        f"DECISIONE: {decision.decision}\n"
        f"TITOLO: {decision.headline}\n"
        f"PRESCRIZIONE: {decision.prescription}\n"
        f"RAZIONALE: {decision.rationale}\n"
        f"NOTA ATTUALE (template da riscrivere): {decision.daily_note}\n"
        f"FORMULAZIONI RECENTI DA EVITARE:\n{recent}"
    )


def _default_call_fn(settings: Settings) -> Callable[[str, str], str]:
    """Build a one-shot Haiku call with a hard short timeout and no retries."""

    def _call(system: str, user: str) -> str:
        from anthropic import Anthropic  # lazy: only when enabled

        client = Anthropic(
            api_key=settings.anthropic_api_key,
            timeout=settings.verbalizer_timeout_seconds,
            max_retries=0,
        )
        resp = client.messages.create(
            model=settings.verbalizer_model,
            max_tokens=120,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(
            b.text for b in resp.content if getattr(b, "type", "") == "text"
        ).strip()

    return _call


def verbalize_decision(
    decision: CoachDecision,
    recent_notes: list[str],
    *,
    settings: Settings | None = None,
    call_fn: Callable[[str, str], str] | None = None,
) -> str:
    """Return a rewritten daily note, or the original template on any problem.

    ``call_fn(system, user) -> str`` is the model call; injected in tests. When
    omitted, a real Haiku call is built only if the verbalizer is enabled and an
    API key is present — otherwise the template note is returned untouched.
    """
    settings = settings or get_settings()
    template = decision.daily_note

    if call_fn is None:
        if not settings.verbalizer_enabled or not settings.anthropic_api_key:
            return template
        call_fn = _default_call_fn(settings)

    try:
        raw = call_fn(_SYSTEM_PROMPT, _build_user_message(decision, recent_notes))
    except Exception as exc:  # noqa: BLE001 - verbalization is best-effort
        logger.info("Verbalizer call failed, using template: %s", exc)
        return template

    candidate = _trim_to_two_sentences((raw or "").strip().strip('"'))
    if _passes_guards(candidate, decision, recent_notes):
        return candidate
    return template
