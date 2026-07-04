"""LLM voice for shareable recaps (Roadmap A6), reusing the A1 verbalizer discipline.

The *facts* (:mod:`app.processing.recap`) stay deterministic; this module only
rewrites the human surface into something worth sharing. Same hard rule as the
A1 verbalizer, enforced in code after the model answers:

* **No invented numbers.** Any number in the rewrite must already appear in the
  facts passed in. A novel number → reject, fall back to the deterministic
  template built straight from the same facts.

Any error, timeout, empty answer, disabled flag or missing API key returns the
template — the feature can only ever *improve* the recap, never break it (and
never leaves the athlete without a shareable card). The network call is
injectable (``call_fn``) so tests exercise every guard without touching
Anthropic. Reuses the same ``verbalizer_enabled`` flag as A1: no new feature
flag to wire up in prod.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from app.config import Settings, get_settings
from app.logging_config import get_logger
from app.processing.recap import RaceRecapFacts, WeeklyRecapFacts

logger = get_logger("app.coaching.recap_narrative")

_NUM_RE = re.compile(r"\d+(?::\d+)?(?:\.\d+)?")

_WEEKLY_SYSTEM_PROMPT = (
    "Sei la voce di un coach di corsa italiano. Scrivi un breve recap "
    "settimanale da condividere, caldo e mai banale. Regole ferree:\n"
    "1. Massimo 2 frasi brevi.\n"
    "2. NON inventare numeri: puoi citare SOLO i valori gia' presenti nei dati "
    "forniti. Se non sei sicuro di un numero, non scriverlo.\n"
    "3. Tono da traguardo raggiunto, adatto a essere condiviso.\n"
    "Rispondi SOLO con il testo, senza virgolette ne preamboli."
)

_RACE_SYSTEM_PROMPT = (
    "Sei la voce di un coach di corsa italiano. Scrivi un breve recap di una "
    "gara appena corsa, da condividere, celebrativo. Regole ferree:\n"
    "1. Massimo 2 frasi brevi.\n"
    "2. NON inventare numeri: puoi citare SOLO i valori gia' presenti nei dati "
    "forniti.\n"
    "3. Se il tempo e' stato piu veloce del previsto, celebralo; se piu lento, "
    "resta comunque positivo (l'aver finito conta).\n"
    "Rispondi SOLO con il testo, senza virgolette ne preamboli."
)


def _numbers_in(text: str) -> set[str]:
    return set(_NUM_RE.findall(text or ""))


def _trim_to_two_sentences(note: str) -> str:
    parts = re.split(r"(?<=[.!?])\s+", note.strip())
    return " ".join(parts[:2]).strip()


def _weekly_template(f: WeeklyRecapFacts) -> str:
    bits = [f"Settimana da {f.distance_km:g} km su {f.runs_count} uscite"]
    if f.adherence_pct is not None:
        bits.append(f"aderenza al piano {f.adherence_pct:.0f}%")
    text = ", ".join(bits) + "."
    if f.best_moment:
        text += f" {f.best_moment}."
    return text


def _race_template(f: RaceRecapFacts) -> str:
    text = f"{f.distance_km:g} km in {f.actual_time}"
    if f.delta_label:
        text += f", {f.delta_label}"
    return text + "."


def _weekly_allowed_numbers(f: WeeklyRecapFacts) -> set[str]:
    allowed: set[str] = set()
    for value in (f.distance_km, f.runs_count, f.adherence_pct, f.avg_execution_score):
        if value is not None:
            allowed |= _numbers_in(str(value))
            allowed |= _numbers_in(f"{value:g}" if isinstance(value, float) else str(value))
    allowed |= _numbers_in(f.best_moment or "")
    return allowed


def _race_allowed_numbers(f: RaceRecapFacts) -> set[str]:
    allowed: set[str] = set()
    allowed |= _numbers_in(str(f.distance_km)) | _numbers_in(f"{f.distance_km:g}")
    allowed |= _numbers_in(f.actual_time)
    allowed |= _numbers_in(f.predicted_time or "")
    allowed |= _numbers_in(f.delta_label or "")
    return allowed


def _weekly_user_message(f: WeeklyRecapFacts) -> str:
    return (
        f"Distanza settimanale: {f.distance_km} km\n"
        f"Numero di uscite: {f.runs_count}\n"
        f"Aderenza al piano: {f.adherence_pct if f.adherence_pct is not None else 'n/d'}%\n"
        f"Execution score medio: "
        f"{f.avg_execution_score if f.avg_execution_score is not None else 'n/d'}\n"
        f"Momento migliore: {f.best_moment or '(nessuno in particolare)'}"
    )


def _race_user_message(f: RaceRecapFacts) -> str:
    return (
        f"Distanza gara: {f.distance_km} km\n"
        f"Tempo reale: {f.actual_time}\n"
        f"Tempo previsto (pre-gara): {f.predicted_time or 'n/d'}\n"
        f"Delta: {f.delta_label or 'n/d'}"
    )


def _default_call_fn(settings: Settings) -> Callable[[str, str], str]:
    def _call(system: str, user: str) -> str:
        from anthropic import Anthropic  # lazy: only when enabled

        client = Anthropic(
            api_key=settings.anthropic_api_key,
            timeout=settings.verbalizer_timeout_seconds,
            max_retries=0,
        )
        resp = client.messages.create(
            model=settings.verbalizer_model,
            max_tokens=150,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(
            b.text for b in resp.content if getattr(b, "type", "") == "text"
        ).strip()

    return _call


def _rewrite(
    system_prompt: str,
    user_message: str,
    template: str,
    allowed_numbers: set[str],
    *,
    settings: Settings | None,
    call_fn: Callable[[str, str], str] | None,
) -> str:
    settings = settings or get_settings()
    if call_fn is None:
        if not settings.verbalizer_enabled or not settings.anthropic_api_key:
            return template
        call_fn = _default_call_fn(settings)

    try:
        raw = call_fn(system_prompt, user_message)
    except Exception as exc:  # noqa: BLE001 - narrative rewrite is best-effort
        logger.info("Recap narrative call failed, using template: %s", exc)
        return template

    candidate = _trim_to_two_sentences((raw or "").strip().strip('"'))
    if not candidate:
        return template
    if not _numbers_in(candidate) <= allowed_numbers:
        logger.info("Recap narrative rejected: invented number in %r", candidate)
        return template
    return candidate


def build_weekly_narrative(
    facts: WeeklyRecapFacts,
    *,
    settings: Settings | None = None,
    call_fn: Callable[[str, str], str] | None = None,
) -> str:
    """Return an LLM-voiced weekly recap, or the deterministic template."""
    template = _weekly_template(facts)
    return _rewrite(
        _WEEKLY_SYSTEM_PROMPT, _weekly_user_message(facts), template,
        _weekly_allowed_numbers(facts), settings=settings, call_fn=call_fn,
    )


def build_race_narrative(
    facts: RaceRecapFacts,
    *,
    settings: Settings | None = None,
    call_fn: Callable[[str, str], str] | None = None,
) -> str:
    """Return an LLM-voiced race recap, or the deterministic template."""
    template = _race_template(facts)
    return _rewrite(
        _RACE_SYSTEM_PROMPT, _race_user_message(facts), template,
        _race_allowed_numbers(facts), settings=settings, call_fn=call_fn,
    )
