"""LLM as verbalizer for the plan (Fase B — plan architecture review).

The periodization engine (:func:`app.processing.periodization.build_plan_spec`)
already produces the whole plan deterministically: phases, volumes, paces,
session structure — with the chat §CTX§ honoured. The LLM no longer generates the
plan (no more monolithic JSON, no truncation, no hallucinated volumes). Its only
job here is **verbalization**: rewrite each session's ``description`` into nicer
coaching prose while every structured field (day, type, distance, pace, duration)
stays exactly as the engine set it.

Pattern A1: injectable ``call_fn`` for tests, gated on the API key, parsed
defensively, and total-fallback — no key / bad JSON / timeout keeps the engine's
own template descriptions, so the feature always works offline.
"""

from __future__ import annotations

import logging

from app.coaching import prompts
from app.config import Settings, get_settings
from app.schemas import PlanGenerateRequest

logger = logging.getLogger(__name__)

# Sessions with no meaningful prose to rewrite.
_SKIP_TYPES = {"rest"}


def _session_id(week_number: int, day_of_week: int) -> str:
    return f"w{week_number}d{day_of_week}"


def _prescriptions(spec: dict) -> list[dict]:
    """Flatten the spec into a compact list the model can rephrase.

    Each entry carries the engine's template ``hint`` (which already embeds the
    exact numbers) so the model rewrites the prose without recomputing anything.
    """
    out: list[dict] = []
    for week in spec.get("weeks", []):
        wn = week.get("week_number")
        phase = week.get("phase")
        for sess in week.get("sessions", []):
            if sess.get("session_type") in _SKIP_TYPES:
                continue
            out.append(
                {
                    "id": _session_id(wn, sess.get("day_of_week")),
                    "phase": phase,
                    "type": sess.get("session_type"),
                    "title": sess.get("title"),
                    "distance_km": sess.get("target_distance_km"),
                    "pace": sess.get("target_pace"),
                    "duration_min": sess.get("target_duration_min"),
                    "hint": sess.get("description"),
                }
            )
    return out


def _apply_descriptions(spec: dict, descriptions: dict) -> int:
    """Overwrite ``description`` only; never touch a structured field.

    Returns how many sessions were rewritten. Unknown ids and non-string values
    are ignored so a partial/truncated model reply degrades gracefully.
    """
    applied = 0
    for week in spec.get("weeks", []):
        wn = week.get("week_number")
        for sess in week.get("sessions", []):
            if sess.get("session_type") in _SKIP_TYPES:
                continue
            new = descriptions.get(_session_id(wn, sess.get("day_of_week")))
            if isinstance(new, str) and new.strip():
                sess["description"] = new.strip()
                applied += 1
    return applied


def verbalize_plan_spec(
    spec: dict,
    *,
    request: PlanGenerateRequest | None = None,
    settings: Settings | None = None,
    call_fn=None,
) -> dict:
    """Rewrite per-session descriptions with the LLM voice (best-effort).

    The spec is mutated in place and also returned. Any failure — no key, bad
    JSON, timeout — leaves the engine's template descriptions untouched. The LLM
    only sees prose; the numbers it is handed are the numbers that stay.
    """
    settings = settings or get_settings()

    if call_fn is None and settings.ai_enabled:
        from app.coaching.coach import AICoach

        coach = AICoach(settings)
        model = settings.planner_model or settings.coach_model
        call_fn = lambda s, u: coach._call(  # noqa: E731 - tiny adapter
            s, u, model, max_tokens=settings.plan_verbalize_max_tokens
        )

    if call_fn is None:
        return spec

    prescriptions = _prescriptions(spec)
    if not prescriptions:
        return spec

    try:
        from app.coaching.coach import _parse_json_response

        user = prompts.build_plan_verbalize_message(prescriptions, request)
        raw = call_fn(prompts.PLAN_VERBALIZE_SYSTEM_PROMPT, user)
        descriptions = _parse_json_response(raw)
        if not isinstance(descriptions, dict):
            raise ValueError("verbalization reply is not a JSON object")
        applied = _apply_descriptions(spec, descriptions)
        logger.info(
            "Plan verbalized: %d/%d sessions rewritten", applied, len(prescriptions)
        )
    except Exception as exc:  # noqa: BLE001 - any model/parse failure → templates
        logger.warning("Plan verbalization failed, keeping templates: %s", exc)

    return spec
