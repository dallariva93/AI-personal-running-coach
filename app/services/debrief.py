"""Post-run voice/text debrief → structured signals (Roadmap A4).

Twenty seconds of the athlete's own voice after a run replace the crude proxies
(Garmin stress → fatigue, body-battery → motivation). The transcript (produced
on-device by Android's ``SpeechRecognizer``, or typed) is POSTed to
``/api/debrief`` and turned into a small structured record:

    {rpe, soreness, pain_location, mood, notes}

Two extraction paths, same contract:

* **LLM** (Haiku) when a key is configured — richer understanding of free
  Italian. Defensive JSON parse; any failure falls back to…
* **rule-based** — a deterministic Italian parser that keeps the feature (and
  its tests) fully working offline / without credentials.

The extracted signals then: update ``Activity.rpe/notes``; upsert the day's
``DailyCheckin`` with ``source="voice"`` (so a later Garmin proxy never
overwrites it, per :mod:`app.services.checkin` precedence); and, when a pain
location is mentioned, raise a high-priority notifiable event — a bridge toward
the injury-conversation feature (G6).
"""

from __future__ import annotations

import re
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.coaching import prompts
from app.config import Settings, get_settings
from app.db.models import Activity, DailyCheckinRow
from app.logging_config import get_logger
from app.schemas import DailyCheckin, DebriefResult
from app.services.checkin import save_checkin
from app.services.event_service import log_event

logger = get_logger("app.services.debrief")

CallFn = "callable"  # (system, user) -> str


# ── Rule-based Italian extractor ─────────────────────────────────────────────
# Body parts we can flag as a pain location (canonical singular form → the word
# stems we accept in the transcript). Order matters only for readability.
_BODY_PARTS: dict[str, tuple[str, ...]] = {
    "polpaccio": ("polpacc",),
    "ginocchio": ("ginocch",),
    "caviglia": ("cavigli",),
    "tendine d'Achille": ("achill", "tendine"),
    "coscia": ("cosc", "quadricipit", "femoral"),
    "flessori": ("flessor", "adduttor"),
    "schiena": ("schien", "lombar", "dorsal"),
    "anca": ("anca", "anche", "bacino"),
    "tibia": ("tibi", "stinc"),
    "piede": ("piede", "piedi", "pianta", "alluce", "metatars"),
    "gluteo": ("gluteo", "glutei", "gluteo"),
    "inguine": ("inguin",),
    "gamba": ("gamba", "gambe"),
}

# Words that turn a body-part mention into an actual complaint.
_DISCOMFORT_CUES = (
    "dolor", "male", "fastidi", "tes", "indolenz", "contratt", "tirat",
    "indurit", "rigid", "infiammat", "acciacc", "fitta", "cramp", "bloccat",
    "duro", "dura", "pesant",
)

# Positive descriptors that explicitly clear a body part (not a complaint).
_POSITIVE_CUES = ("legger", "sciolt", "bene", "benissimo", "ottim", "fresc")

_LATERALITY = {
    "destro": "destro", "destra": "destro", "dx": "destro",
    "sinistro": "sinistro", "sinistra": "sinistro", "sx": "sinistro",
}

# Effort keywords → RPE when no explicit number is given.
_EFFORT_WORDS: tuple[tuple[tuple[str, ...], int], ...] = (
    (("durissim", "tostissim", "massacrant", "sfiancant", "distrutt", "morto", "morta"), 9),
    (("molto dura", "molto duro", "molto faticos", "tirata forte", "spint"), 8),
    (("dura", "duro", "tosta", "tosto", "pesante", "faticos", "sofferto", "fatica"), 7),
    (("medi", "normale", "regolare", "onesto", "onesta"), 5),
    (("facile", "tranquill", "leggera", "leggero", "scorrevol", "comod", "piano", "rilassat"), 3),
)

_MOOD_POSITIVE = ("bene", "benissimo", "content", "soddisfatt", "carico", "carica",
                  "alla grande", "gasato", "gasata", "sereno", "serena", "top",
                  "divert", "goduta", "goduto", "bella")
_MOOD_NEGATIVE = ("male", "demoralizzat", "giu", "giù", "scoraggiat", "frustrat",
                  "svogliat", "scarico", "scarica", "nervos")
_MOOD_TIRED = ("stanc", "sfinit", "esaust", "spompat", "cotto", "cotta", "provat")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _clamp(value: int) -> int:
    return max(1, min(10, value))


def _extract_rpe(t: str) -> int | None:
    """Explicit '7 di fatica' / 'fatica 7' / '7/10' first, else keyword tone."""
    for pat in (
        r"(\d{1,2})\s*(?:/\s*10|su\s*10)",
        r"(\d{1,2})\s*di\s*(?:fatica|sforzo|fatta)",
        r"(?:fatica|sforzo|rpe|intensit[aà])\D{0,8}(\d{1,2})",
    ):
        m = re.search(pat, t)
        if m:
            return _clamp(int(m.group(1)))
    for stems, value in _EFFORT_WORDS:
        if any(s in t for s in stems):
            return value
    return None


def _extract_soreness(t: str) -> int | None:
    for pat in (
        r"(\d{1,2})\s*di\s*(?:dolore|indolenziment|male)",
        r"(?:dolore|indolenziment)\D{0,8}(\d{1,2})",
    ):
        m = re.search(pat, t)
        if m:
            return _clamp(int(m.group(1)))
    if any(s in t for s in ("dolore forte", "molto dolorant", "fa molto male", "fitta")):
        return 8
    if any(s in t for s in ("dolore", "fa male", "dolorant", "infiammat")):
        return 6
    if any(s in t for s in ("teso", "tesa", "indolenz", "contratt", "tirat", "indurit", "rigid")):
        return 4
    return None


def _find_pain_location(t: str) -> str | None:
    """Return 'part [lato]' when a body part is mentioned as a complaint."""
    words = t.split()
    for canonical, stems in _BODY_PARTS.items():
        for stem in stems:
            idx = next((i for i, w in enumerate(words) if stem in w), None)
            if idx is None:
                continue
            window = words[max(0, idx - 3): idx + 5]
            ctx = " ".join(window)
            # A positive descriptor with no complaint word clears it.
            if any(p in ctx for p in _POSITIVE_CUES) and not any(
                d in ctx for d in _DISCOMFORT_CUES
            ):
                continue
            if not any(d in ctx for d in _DISCOMFORT_CUES):
                continue
            side = next((_LATERALITY[w] for w in window if w in _LATERALITY), None)
            return f"{canonical} {side}" if side else canonical
    return None


def _extract_mood(t: str) -> str | None:
    if any(s in t for s in _MOOD_TIRED):
        return "stanco"
    if any(s in t for s in _MOOD_NEGATIVE):
        return "giù"
    if any(s in t for s in _MOOD_POSITIVE):
        return "bene"
    return None


def _rule_based_extract(text: str) -> DebriefResult:
    t = _norm(text)
    return DebriefResult(
        rpe=_extract_rpe(t),
        soreness=_extract_soreness(t),
        pain_location=_find_pain_location(t),
        mood=_extract_mood(t),
        notes=text.strip(),
    )


# ── LLM path (defensive) ─────────────────────────────────────────────────────


def _coerce_int(value: object) -> int | None:
    try:
        if value is None:
            return None
        return _clamp(int(value))
    except (TypeError, ValueError):
        return None


def _coerce_str(value: object) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _llm_extract(text: str, call_fn) -> DebriefResult:
    from app.coaching.coach import _parse_json_response

    raw = call_fn(prompts.DEBRIEF_EXTRACT_SYSTEM_PROMPT, text)
    data = _parse_json_response(raw)
    notes = _coerce_str(data.get("notes")) or text.strip()
    return DebriefResult(
        rpe=_coerce_int(data.get("rpe")),
        soreness=_coerce_int(data.get("soreness")),
        pain_location=_coerce_str(data.get("pain_location")),
        mood=_coerce_str(data.get("mood")),
        notes=notes,
    )


def extract_debrief(
    text: str,
    *,
    settings: Settings | None = None,
    call_fn=None,
) -> DebriefResult:
    """Turn a debrief transcript into structured signals.

    Prefers the LLM (real key or injected ``call_fn``); any failure — no key,
    bad JSON, timeout — falls back to the deterministic rule-based parser, so
    the feature always works offline. ``notes`` always echoes the raw text.
    """
    text = (text or "").strip()
    if not text:
        return DebriefResult(notes="")

    settings = settings or get_settings()
    if call_fn is None and settings.ai_enabled:
        from app.coaching.coach import AICoach

        coach = AICoach(settings)
        call_fn = lambda s, u: coach._call(  # noqa: E731 - tiny adapter
            s, u, settings.chat_router_model, max_tokens=300
        )

    if call_fn is not None:
        try:
            return _llm_extract(text, call_fn)
        except Exception as exc:  # noqa: BLE001 - any model/parse failure → rules
            logger.warning("Debrief LLM extraction failed, using rules: %s", exc)

    return _rule_based_extract(text)


# ── Persistence + side effects ───────────────────────────────────────────────


def _resolve_activity(db: Session, activity_id: int | None) -> Activity | None:
    if activity_id is not None:
        return db.get(Activity, activity_id)
    # No id (voice flow may not know it): attach to the most recent run.
    return db.scalar(
        select(Activity)
        .where(Activity.sport == "run")
        .order_by(Activity.date.desc(), Activity.id.desc())
        .limit(1)
    )


def process_debrief(
    db: Session,
    text: str,
    activity_id: int | None = None,
    *,
    settings: Settings | None = None,
    call_fn=None,
) -> DebriefResult:
    """Extract a debrief and apply it: activity, check-in, pain event.

    Returns the extracted :class:`DebriefResult` (with ``activity_id`` set to
    the run it was attached to, if any).
    """
    extract = extract_debrief(text, settings=settings, call_fn=call_fn)

    activity = _resolve_activity(db, activity_id)
    target_date = activity.date if activity is not None else date.today().isoformat()

    if activity is not None:
        extract.activity_id = activity.id
        if extract.rpe is not None:
            activity.rpe = extract.rpe
        if extract.notes:
            activity.notes = (
                f"{activity.notes}\n{extract.notes}" if activity.notes else extract.notes
            )
        db.flush()

    # Upsert the day's check-in as a voice source, carrying forward whatever a
    # proxy already recorded (HRV/sleep/motivation) so we enrich, never wipe.
    existing = db.scalar(
        select(DailyCheckinRow).where(DailyCheckinRow.date == target_date)
    )
    checkin = DailyCheckin(
        date=target_date,
        source="voice",
        fatigue=extract.rpe if extract.rpe is not None
        else (existing.fatigue if existing else None),
        soreness=extract.soreness if extract.soreness is not None
        else (existing.soreness if existing else None),
        sleep_h=existing.sleep_h if existing else None,
        hrv_rmssd=existing.hrv_rmssd if existing else None,
        motivation=existing.motivation if existing else None,
        notes=extract.notes or (existing.notes if existing else None),
    )
    save_checkin(db, checkin)

    if extract.pain_location:
        log_event(
            db,
            date_str=target_date,
            event_type="debrief_pain",
            title="Hai indicato un fastidio",
            detail=(
                f"Sento che hai indicato dolore al {extract.pain_location}: "
                "vuoi dirmi di più?"
            ),
            after={
                "pain_location": extract.pain_location,
                "activity_id": extract.activity_id,
                "deep_link": "debrief",
            },
            notifiable=True,
            priority="high",
            dedupe_key=f"debrief_pain:{target_date}:{extract.pain_location}",
        )

    return extract


def maybe_prompt_debrief(db: Session, activity: Activity | None) -> None:
    """After a new run is ingested/scored, nudge the athlete for a 20s debrief.

    Notifiable, deep-links to the on-device bottom-sheet, one per activity
    (dedupe on activity id). Best-effort: never raises.
    """
    if activity is None or activity.sport != "run":
        return
    log_event(
        db,
        date_str=activity.date,
        event_type="debrief_prompt",
        title="Com'è andata?",
        detail="Raccontami in 20 secondi com'è andata la corsa: 5 tocchi e ho i tuoi numeri.",
        after={"deep_link": "debrief", "activity_id": activity.id},
        notifiable=True,
        priority="low",
        dedupe_key=f"debrief_prompt:{activity.id}",
    )
