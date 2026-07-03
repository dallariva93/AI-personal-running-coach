"""Coaching backends and the offline rule-based fallback."""

from __future__ import annotations

import json
import re
from datetime import date, timedelta
from typing import Protocol

from app.coaching import prompts
from app.config import Settings, get_settings
from app.exceptions import CoachingError
from app.logging_config import get_logger
from app.schemas import (
    AthleteProfile,
    AthleteSnapshot,
    CoachingResult,
    PlanGenerateRequest,
    RunSummary,
    TrainingMetrics,
    WorkoutSegmentIn,
    WorkoutSuggestRequest,
    WorkoutTemplateIn,
)
from app.utils import retry_call

logger = get_logger("app.coaching")


class Coach(Protocol):
    def analyze_run(
        self,
        run: RunSummary,
        history: list[RunSummary],
        metrics: TrainingMetrics,
        profile: AthleteProfile | None = None,
    ) -> CoachingResult: ...

    def plan_week(
        self,
        runs: list[RunSummary],
        metrics: TrainingMetrics,
        weekly: list[dict],
        profile: AthleteProfile | None = None,
        snapshot: AthleteSnapshot | None = None,
    ) -> CoachingResult: ...

    def plan_multiweek(
        self,
        request: PlanGenerateRequest,
        profile: AthleteProfile | None,
        metrics: TrainingMetrics | None,
        ramp_pct: float | None = None,
    ) -> dict: ...

    def suggest_workout(
        self,
        request: WorkoutSuggestRequest,
        metrics: TrainingMetrics | None,
        profile: AthleteProfile | None,
    ) -> WorkoutTemplateIn: ...

    def chat_for_plan(
        self,
        messages: list[dict],
    ) -> tuple[str, bool, str | None]: ...

    def chat_message(
        self,
        messages: list[dict],
        system: str,
    ) -> tuple[str, str, str]: ...


def _split_sections(text: str) -> tuple[str, str]:
    """Split a markdown response into (analysis, next_workout) by the headings."""
    analysis, next_workout = text, ""
    match = re.search(r"##\s*Prossimo allenamento", text, flags=re.IGNORECASE)
    if match:
        analysis = text[: match.start()]
        next_workout = text[match.end():]
    analysis = re.sub(r"^##\s*Analisi\s*", "", analysis.strip(), flags=re.IGNORECASE).strip()
    return analysis.strip(), next_workout.strip()


class AICoach:
    """Coaching via the Anthropic Claude API."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client = None
        self._fallback = OfflineCoach()

    def _get_client(self):
        if self._client is None:
            from anthropic import Anthropic  # lazy import

            self._client = Anthropic(
                api_key=self.settings.anthropic_api_key,
                timeout=self.settings.ai_timeout_seconds,
                max_retries=0,  # we handle retries/backoff ourselves
            )
        return self._client

    def _call(self, system: str, user: str, model: str, max_tokens: int = 1500) -> str:
        def _do() -> str:
            resp = self._get_client().messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            return "".join(
                block.text for block in resp.content if getattr(block, "type", "") == "text"
            )

        return retry_call(
            _do,
            retries=max(1, self.settings.ai_max_retries),
            base_delay=2.0,
            description=f"claude.messages.create({model})",
        )

    def _call_chat(
        self, system: str, messages: list[dict], max_tokens: int = 600,
        model: str | None = None,
    ) -> str:
        """Multi-turn chat call. Defaults to Haiku; pass model to override."""
        _model = model or "claude-haiku-4-5-20251001"

        def _do() -> str:
            resp = self._get_client().messages.create(
                model=_model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
            )
            return "".join(
                block.text for block in resp.content if getattr(block, "type", "") == "text"
            )

        return retry_call(_do, retries=2, base_delay=1.0, description=f"chat.{_model}")

    def _route_message(self, message: str) -> str:
        """Classify message complexity with Haiku. Returns 'simple'|'medium'|'complex'."""
        try:
            raw = self._call(
                prompts.CHAT_ROUTING_SYSTEM_PROMPT,
                message,
                self.settings.chat_router_model,
                max_tokens=20,
            )
            data = json.loads(raw.strip())
            tier = data.get("tier", "simple")
            return tier if tier in ("simple", "medium", "complex") else "simple"
        except Exception:
            return "simple"

    def analyze_run(
        self,
        run: RunSummary,
        history: list[RunSummary],
        metrics: TrainingMetrics,
        profile: AthleteProfile | None = None,
    ) -> CoachingResult:
        system = prompts.SINGLE_SYSTEM_PROMPT.format(
            athlete_profile=self._profile_text(profile)
        )
        user = prompts.build_single_user_message(run, history, metrics, profile)
        try:
            text = self._call(system, user, self.settings.coach_model)
        except Exception as exc:
            return self._handle_failure(
                exc, self._fallback.analyze_run, run, history, metrics, profile
            )
        analysis, next_workout = _split_sections(text)
        confidence, missing = self._fallback._assess_confidence(run, metrics, profile)
        return CoachingResult(
            scope="single", model=self.settings.coach_model,
            analysis=analysis, next_workout=next_workout,
            confidence=confidence, missing_data=missing,
        )

    def plan_week(
        self,
        runs: list[RunSummary],
        metrics: TrainingMetrics,
        weekly: list[dict],
        profile: AthleteProfile | None = None,
        snapshot: AthleteSnapshot | None = None,
    ) -> CoachingResult:
        system = prompts.WEEKLY_SYSTEM_PROMPT.format(
            athlete_profile=self._profile_text(profile)
        )
        user = prompts.build_weekly_user_message(runs, metrics, weekly, profile, snapshot)
        model = self.settings.planner_model or self.settings.coach_model
        try:
            text = self._call(system, user, model, max_tokens=2000)
        except Exception as exc:
            return self._handle_failure(
                exc, self._fallback.plan_week, runs, metrics, weekly, profile, snapshot
            )
        analysis, next_workout = _split_sections(text)
        confidence, missing = self._fallback._assess_confidence(None, metrics, profile)
        return CoachingResult(
            scope="weekly", model=model, analysis=analysis, next_workout=next_workout,
            confidence=confidence, missing_data=missing,
        )

    def plan_multiweek(
        self,
        request: PlanGenerateRequest,
        profile: AthleteProfile | None,
        metrics: TrainingMetrics | None,
        ramp_pct: float | None = None,
    ) -> dict:
        """Generate a full multi-week training plan via Claude, fall back to offline."""
        model = self.settings.planner_model or self.settings.coach_model
        user = prompts.build_multiweek_plan_message(request, profile, metrics, ramp_pct)
        try:
            raw = self._call(
                prompts.MULTIWEEK_PLAN_SYSTEM_PROMPT,
                user,
                model,
                max_tokens=8000,
            )
            plan_data = _parse_json_response(raw)
            _validate_plan_structure(plan_data)
            return plan_data
        except Exception as exc:
            logger.error(
                "Multiweek plan AI call failed, falling back to offline: %s", exc
            )
            return self._fallback.plan_multiweek(request, profile, metrics, ramp_pct)

    def suggest_workout(
        self,
        request: WorkoutSuggestRequest,
        metrics: TrainingMetrics | None,
        profile: AthleteProfile | None,
    ) -> WorkoutTemplateIn:
        """Generate a workout suggestion via Claude, fall back to offline."""
        model = self.settings.coach_model
        user = prompts.build_workout_suggest_message(request, metrics, profile)
        try:
            raw = self._call(
                prompts.WORKOUT_SUGGEST_SYSTEM_PROMPT,
                user,
                model,
                max_tokens=2000,
            )
            data = _parse_json_response(raw)
            return WorkoutTemplateIn(**data)
        except Exception as exc:
            logger.error(
                "Workout suggest AI call failed, falling back to offline: %s", exc
            )
            return self._fallback.suggest_workout(request, metrics, profile)

    def chat_for_plan(
        self,
        messages: list[dict],
    ) -> tuple[str, bool, str | None]:
        """Multi-turn Haiku chat to collect runner profile before plan generation.

        Returns (visible_message, is_complete, runner_context_json).
        When is_complete=True, runner_context_json contains the extracted runner
        profile as a JSON string ready to pass to plan generation.
        """
        try:
            raw = self._call_chat(prompts.PLAN_CHAT_SYSTEM_PROMPT, messages)
        except Exception as exc:
            logger.error("Plan chat AI call failed, using offline: %s", exc)
            return self._fallback.chat_for_plan(messages)

        is_complete = "§READY§" in raw
        runner_context: str | None = None
        if is_complete:
            ctx_match = re.search(r"§CTX§\s*(.*?)\s*§/CTX§", raw, re.DOTALL)
            if ctx_match:
                runner_context = ctx_match.group(1).strip()

        # Strip sentinels from the message shown to the user
        message = re.sub(r"§CTX§.*?§/CTX§", "", raw, flags=re.DOTALL)
        message = message.replace("§READY§", "").strip()
        return message, is_complete, runner_context

    def chat_message(
        self,
        messages: list[dict],
        system: str,
    ) -> tuple[str, str, str]:
        """Route a conversational message and return (reply, model_used, tier)."""
        last_user = next(
            (m["content"] for m in reversed(messages) if m["role"] == "user"),
            "",
        )
        tier = self._route_message(last_user)
        model = {
            "simple": self.settings.chat_simple_model,
            "medium": self.settings.chat_medium_model,
            "complex": self.settings.chat_complex_model,
        }[tier]
        try:
            reply = self._call_chat(system, messages, max_tokens=1000, model=model)
        except Exception as exc:
            logger.error("Chat message AI call failed: %s", exc)
            reply, _, _ = self._fallback.chat_message(messages, system)
            return reply, self._fallback.MODEL, tier
        return reply, model, tier

    def _profile_text(self, profile: AthleteProfile | None) -> str:
        """Render the athlete profile for the system prompt.

        Prefers the structured profile, falling back to the free-text setting.
        """
        if profile is None:
            return self.settings.athlete_profile
        bits: list[str] = []
        if profile.age:
            bits.append(f"{profile.age} anni")
        if profile.sex:
            bits.append(profile.sex)
        if profile.experience_years:
            bits.append(f"{profile.experience_years:g} anni di corsa")
        if profile.max_hr:
            bits.append(f"FCmax {profile.max_hr}")
        if profile.resting_hr:
            bits.append(f"FCriposo {profile.resting_hr}")
        if profile.weekly_runs:
            bits.append(f"{profile.weekly_runs} uscite/sett")
        descr = ", ".join(bits) if bits else self.settings.athlete_profile
        if profile.physiology and profile.physiology.lt2_pace:
            descr += f". Soglia (LT2) ~{profile.physiology.lt2_pace}/km"
        zones = self._zones_text(profile.zones)
        if zones:
            descr += f". Zone FC: {zones}"
        descr += f". {self._tone_directive(profile)}"
        return f"Atleta: {descr}."

    @staticmethod
    def _tone_directive(profile: AthleteProfile) -> str:
        """Tone guidance from level + risk tolerance (priority #4)."""
        lvl = {
            "beginner": "Principiante: progredisci con prudenza e spiega il perché",
            "intermediate": "Atleta intermedio",
            "advanced": "Atleta avanzato: può sostenere stimoli e carichi impegnativi",
        }.get(profile.level, "Atleta intermedio")
        risk = {
            "conservative": "tolleranza al rischio bassa, privilegia la cautela",
            "moderate": "tolleranza al rischio media",
            "aggressive": "tolleranza al rischio alta: spingi sugli stimoli, "
            "allarmati solo su segnali davvero rossi",
        }.get(profile.risk_tolerance, "tolleranza al rischio media")
        return f"{lvl}; {risk}."

    @staticmethod
    def _zones_text(zones) -> str:
        """Render personalised HR zones as 'Z2 141-155, Z4 169-178'."""
        if zones is None:
            return ""
        parts = []
        for name, bounds in (
            ("Z1", zones.z1_hr), ("Z2", zones.z2_hr), ("Z3", zones.z3_hr),
            ("Z4", zones.z4_hr), ("Z5", zones.z5_hr),
        ):
            if bounds:
                parts.append(f"{name} {bounds[0]}-{bounds[1]}")
        return ", ".join(parts)

    def _handle_failure(self, exc: Exception, fallback_fn, *args) -> CoachingResult:
        """On AI failure, either degrade to the offline coach or re-raise."""
        if self.settings.ai_fallback_offline:
            logger.error("Claude call failed, falling back to offline coach: %s", exc)
            result = fallback_fn(*args)
            result.model = f"{self._fallback.MODEL} (fallback)"
            return result
        logger.error("Claude call failed and fallback disabled: %s", exc)
        raise CoachingError(f"Coaching AI non disponibile: {exc}") from exc


class OfflineCoach:
    """Deterministic, rule-based coaching. No API key, no cost, always works.

    The logic mirrors the methodology in the system prompt: respect 80/20,
    recover after hard/long efforts, back off when the form state is fatigued.
    Useful as a fallback and as the default in demo/CI.
    """

    MODEL = "offline-rules"

    def analyze_run(
        self,
        run: RunSummary,
        history: list[RunSummary],
        metrics: TrainingMetrics,
        profile: AthleteProfile | None = None,
    ) -> CoachingResult:
        analysis = self._analyze_run_text(run, metrics)
        next_workout = self._suggest_next(run, metrics)
        confidence, missing = self._assess_confidence(run, metrics, profile)
        return CoachingResult(
            scope="single", model=self.MODEL, analysis=analysis,
            next_workout=next_workout, confidence=confidence, missing_data=missing,
        )

    def plan_week(
        self,
        runs: list[RunSummary],
        metrics: TrainingMetrics,
        weekly: list[dict],
        profile: AthleteProfile | None = None,
        snapshot: AthleteSnapshot | None = None,
    ) -> CoachingResult:
        analysis = self._analyze_week_text(metrics, weekly, profile)
        available = profile.available_days if profile else None
        next_workout = self._suggest_week(metrics, available)
        confidence, missing = self._assess_confidence(None, metrics, profile)
        return CoachingResult(
            scope="weekly", model=self.MODEL, analysis=analysis,
            next_workout=next_workout, confidence=confidence, missing_data=missing,
        )

    @staticmethod
    def _assess_confidence(
        run: RunSummary | None,
        metrics: TrainingMetrics,
        profile: AthleteProfile | None,
    ) -> tuple[str, list[str]]:
        """Determine confidence level and list missing data (Roadmap #5)."""
        missing: list[str] = []
        if run is not None:
            if run.avg_hr is None:
                missing.append("Frequenza cardiaca")
            if run.rpe is None:
                missing.append("RPE")
            if run.elevation_gain_m is None:
                missing.append("Dislivello")
        if metrics.ctl is None:
            missing.append("CTL (carico cronico)")
        if metrics.tsb is None:
            missing.append("TSB (forma)")
        if profile is None:
            missing.append("Profilo atleta")
        elif profile.goal is None or not profile.goal.target_date:
            missing.append("Obiettivo gara")
        if len(missing) >= 3:
            level = "low"
        elif len(missing) >= 1:
            level = "medium"
        else:
            level = "high"
        return level, missing

    # -- helpers ------------------------------------------------------------
    def _analyze_run_text(self, run: RunSummary, m: TrainingMetrics) -> str:
        pts: list[str] = []
        pts.append(
            f"Corsa '{run.activity_type}' di {run.distance_km} km in "
            f"{run.duration_min:.0f} min (passo {run.avg_pace or 'n/d'})."
        )
        if run.activity_type in {"easy", "recupero"} and run.avg_hr and run.max_hr:
            if run.avg_hr > 0.85 * run.max_hr:
                pts.append(
                    "FC media alta per una seduta facile: probabilmente sei andato "
                    "troppo forte, tienila più bassa la prossima volta."
                )
            else:
                pts.append("Intensità coerente con una seduta facile: bene così.")
        if run.elevation_gain_m and run.elevation_gain_m > 100:
            pts.append(
                f"Dislivello significativo ({run.elevation_gain_m:.0f} m): occhio al recupero."
            )
        if run.temperature_c is not None and run.temperature_c >= 25:
            extra = " e umidità alta" if (run.humidity_pct or 0) >= 70 else ""
            pts.append(
                f"Caldo ({run.temperature_c:.0f}°C{extra}): FC e fatica risultano più alte "
                "a parità di sforzo, non farti ingannare dal passo."
            )
        # Trail/hilly effort: >25 m of climb per km (GAP 20). Computed inline
        # from RunSummary so the coaching layer stays decoupled from processing.
        if run.elevation_gain_m and run.distance_km > 0 and run.duration_min > 0:
            climb_per_km = run.elevation_gain_m / run.distance_km
            if climb_per_km >= 25:
                vam = run.elevation_gain_m / (run.duration_min / 60.0)
                equiv = run.distance_km + run.elevation_gain_m * 0.01
                pts.append(
                    f"Uscita trail ({climb_per_km:.0f} m D+/km, VAM {vam:.0f} m/h, "
                    f"~{equiv:.0f} km equivalenti in piano): valuta lo sforzo sul "
                    "tempo in piedi, non sul passo."
                )
        pts.append(m.form_explanation)
        if m.easy_ratio is not None and m.easy_ratio < 0.7:
            pts.append(
                f"Negli ultimi 7 giorni solo il {m.easy_ratio*100:.0f}% del volume è facile: "
                "stai facendo troppo intenso, riequilibra verso l'80/20."
            )
        return "- " + "\n- ".join(p for p in pts if p)

    def _suggest_next(self, run: RunSummary, m: TrainingMetrics) -> str:
        hard = run.activity_type in {"tempo", "intervalli", "lungo", "gara"}
        if m.form_state == "fatigued":
            return (
                "**Recupero / riposo.** Lo stato di forma è affaticato e il carico cresce "
                "troppo in fretta. Proposta: 5-6 km molto facili in Z1-Z2 (passo comodo, "
                "conversazione possibile) oppure un giorno di riposo completo."
            )
        if hard:
            return (
                "**Easy / recupero** dopo la seduta impegnativa. Proposta: 6-8 km facili in "
                "Z1-Z2, cadenza rilassata. Niente intensità per far assimilare il lavoro."
            )
        if m.form_state == "detraining":
            return (
                "**Qualità leggera.** Hai margine di carico. Proposta: 8-10 km con 4-5 km "
                "in Z3 (medio) o 5-6 ripetute da 1 min in Z4 con recupero, dopo riscaldamento."
            )
        return (
            "**Fondo medio-facile.** Proposta: 8-10 km in Z2 a passo controllato. "
            "Se ti senti bene, ultimi 2 km leggermente più veloci (progressione)."
        )

    def _analyze_week_text(
        self, m: TrainingMetrics, weekly: list[dict], profile: AthleteProfile | None = None
    ) -> str:
        pts = []
        if profile and profile.goal and profile.goal.target_date:
            g = profile.goal
            days = g.days_to_go()
            if days is not None:
                pts.append(
                    f"Obiettivo {g.goal_type} il {g.target_date}: "
                    f"mancano {days} giorni (~{max(0, days)//7} settimane)."
                )
        if m.phase:
            pts.append(f"Fase del piano: **{m.phase}** — {m.phase_focus or ''}".rstrip())
        if m.predicted_race_time:
            prob = ""
            if m.race_probability is not None:
                prob = f", probabilità obiettivo ~{m.race_probability*100:.0f}%"
            pts.append(
                f"Previsione gara: **~{m.predicted_race_time}**{prob} "
                f"(confidenza {m.race_confidence})."
            )
        pts += [
            f"Volume ultimi 7 giorni: {m.acute_load_km} km; media settimanale (28 gg): "
            f"{m.chronic_load_km} km.",
            f"Carico interno 7gg: {m.acute_load_internal} unità (RPE×durata).",
        ]
        if m.tsb is not None:
            pts.append(
                f"Forma (TSB): {m.tsb:+.0f} (CTL {m.ctl} / ATL {m.atl}) → {m.form_explanation}"
            )
        else:
            pts.append(m.form_explanation)
        pts.append(f"ACWR (secondario): {m.acwr if m.acwr is not None else 'n/d'}.")
        pts.append(f"Trend del carico: {m.load_trend}.")
        if m.injury_level:
            extra = f" — {', '.join(m.injury_factors)}" if m.injury_factors else ""
            pts.append(
                f"Rischio infortunio: {m.injury_level} ({m.injury_score:.0f}/100){extra}."
            )
        if m.efficiency_trend and m.efficiency_trend != "unknown":
            label = {
                "improving": "in miglioramento", "declining": "in calo", "stable": "stabile",
            }.get(m.efficiency_trend, m.efficiency_trend)
            pts.append(f"Efficienza aerobica (passo a pari FC): {label}.")
        if m.readiness_state and m.readiness_state != "unknown" and m.readiness is not None:
            pts.append(f"Recupero (check-in): {m.readiness_state} ({m.readiness:.0f}/100).")
        if m.easy_ratio is not None:
            pts.append(f"Quota volume facile: {m.easy_ratio*100:.0f}% (target ~80%).")
        if m.monotony is not None and m.monotony > 2.0:
            pts.append(
                f"Monotonia alta ({m.monotony}): settimana poco variata, alterna meglio "
                "carichi alti e bassi."
            )
        return "- " + "\n- ".join(pts)

    # Per-phase weekly templates: the *workout content* only (no day labels).
    # Days are assigned afterwards from the athlete's available days (GAP 15).
    _PHASE_SESSIONS = {
        "base": [
            "8-10 km easy Z2",
            "6 km recupero + allunghi",
            "8 km easy Z2",
            "lungo progressivo 16-20 km Z2",
        ],
        "build": [
            "10 km easy Z2",
            "tempo 12 km con 6 km Z3-Z4",
            "8 km easy",
            "lungo 18-22 km con ultimi 5 km a ritmo medio",
        ],
        "specific": [
            "10 km easy + 4 allunghi",
            "ripetute al ritmo gara (es. 5x2 km)",
            "8 km easy Z2",
            "lungo 20-26 km con porzioni a ritmo gara",
        ],
        "peak": [
            "8 km easy",
            "VO2max 6x1000 m Z5 (rec 2-3')",
            "6 km easy + allunghi",
            "medio 16 km con finale veloce",
        ],
        "taper": [
            "6 km easy con 4x30 s a ritmo gara",
            "5 km easy",
            "4 km sciolti + 3 allunghi",
            "8-10 km lento Z2",
        ],
        "race": [
            "5 km easy con 3 allunghi a ritmo gara",
            "4 km sciolti",
            "attivazione 20 min + 3 allunghi",
            "🏁 GARA",
        ],
    }

    _DAY_ABBR = {
        "monday": "Lun", "tuesday": "Mar", "wednesday": "Mer", "thursday": "Gio",
        "friday": "Ven", "saturday": "Sab", "sunday": "Dom",
        "lun": "Lun", "mar": "Mar", "mer": "Mer", "gio": "Gio",
        "ven": "Ven", "sab": "Sab", "dom": "Dom",
    }
    # Sensible default training days by number of sessions, when none are set.
    _DEFAULT_DAYS = {
        1: ["Dom"], 2: ["Mar", "Dom"], 3: ["Mar", "Gio", "Dom"],
        4: ["Mar", "Gio", "Sab", "Dom"], 5: ["Mar", "Mer", "Ven", "Sab", "Dom"],
        6: ["Mar", "Mer", "Gio", "Ven", "Sab", "Dom"],
    }

    def _assign_days(self, contents: list[str], available_days: list[str] | None) -> list[str]:
        """Lay workout contents onto real week days (GAP 15)."""
        if available_days:
            days = [self._DAY_ABBR.get(d.strip().lower(), d[:3]) for d in available_days]
        else:
            days = self._DEFAULT_DAYS.get(len(contents), self._DEFAULT_DAYS[5])
        lines = []
        for i, content in enumerate(contents):
            day = days[i] if i < len(days) else days[-1]
            lines.append(f"{day}: {content}")
        return lines

    def _suggest_week(
        self, m: TrainingMetrics, available_days: list[str] | None = None
    ) -> str:
        low_readiness = m.readiness_state == "red"
        # Phase-driven plan when periodization is active (and recovery is OK).
        if (
            m.phase
            and m.phase in self._PHASE_SESSIONS
            and m.form_state != "fatigued"
            and not low_readiness
        ):
            target = m.phase_volume_target_km or round(
                max(m.chronic_load_km, m.acute_load_km, 20.0), 1
            )
            label = {
                "base": "Base", "build": "Build", "specific": "Specifico",
                "peak": "Peak", "taper": "Taper", "race": "Settimana gara",
            }[m.phase]
            intro = (
                f"Fase **{label}** (~{round(target)} km"
                + (f", {m.weeks_to_race} sett. alla gara" if m.weeks_to_race else "")
                + f"). {m.phase_focus or ''}".rstrip()
            )
            intro += self._adaptive_suffix(m)
            sessions = self._assign_days(self._PHASE_SESSIONS[m.phase], available_days)
            return intro + "\n\n" + "\n".join(f"- {s}" for s in sessions)

        base = max(m.chronic_load_km, m.acute_load_km, 20.0)
        if m.form_state == "fatigued" or low_readiness:
            target = round(base * 0.7)
            if low_readiness:
                # Forced deload: recovery is red → all easy, no quality.
                intro = f"Settimana di **scarico forzato** (~{target} km), recupero basso."
                contents = [
                    "6 km easy Z2",
                    "5 km recupero Z1-Z2",
                    "6 km easy Z2",
                    "8-10 km lento Z2",
                ]
            else:
                # Programmed deload: load is high but recovery is OK → cut volume
                # yet keep one reduced quality stimulus so fitness doesn't stall.
                intro = f"Settimana di **scarico programmato** (~{target} km), il carico è alto."
                contents = [
                    "6 km easy Z2",
                    "qualità ridotta: 8 km con 5x1 min a ritmo soglia (rec 2')",
                    "5 km recupero Z1-Z2",
                    "10-12 km lento Z2",
                ]
        elif m.form_state == "detraining":
            target = round(base * 1.1)
            intro = f"Settimana di **ricostruzione** (~{target} km), puoi risalire gradualmente."
            contents = [
                "8 km easy Z2",
                "6 km recupero",
                "tempo 10 km con 5 km Z3-Z4",
                "6 km easy",
                "lungo 14-16 km Z2",
            ]
        else:
            target = round(base * 1.05)
            intro = f"Settimana **di mantenimento/progressione** (~{target} km), 80/20."
            contents = [
                "8-10 km easy Z2",
                "intervalli 6x800 m Z4 (rec 2')",
                "8 km easy",
                "lungo 16-18 km Z2",
            ]
        intro += self._adaptive_suffix(m)
        sessions = self._assign_days(contents, available_days)
        return intro + "\n\n" + "\n".join(f"- {s}" for s in sessions)

    @staticmethod
    def _adaptive_suffix(m: TrainingMetrics) -> str:
        """Append the adaptive-engine notes (Fase 4) to the weekly intro."""
        if not m.adaptive_notes:
            return ""
        return " ⚙️ Adattamenti: " + "; ".join(m.adaptive_notes) + "."

    def suggest_workout(
        self,
        request: WorkoutSuggestRequest,
        metrics: TrainingMetrics | None,
        profile: AthleteProfile | None,
    ) -> WorkoutTemplateIn:
        """Generate a deterministic workout template based on session_type."""
        level = (profile.level if profile else None) or "intermediate"
        easy_pace = _offline_easy_pace(level, metrics)
        tempo_pace = _offline_tempo_pace(level, metrics)
        interval_pace = _offline_interval_pace(level, metrics)

        stype = request.session_type.lower()

        if stype == "intervals":
            return WorkoutTemplateIn(
                name="Ripetute 5×1000m",
                description=(
                    f"Sessione di velocità: riscaldamento 10 min, "
                    f"5×1000m @ {interval_pace} con 90s recupero trot, "
                    "defaticamento 10 min."
                ),
                type="interval",
                segments=[
                    WorkoutSegmentIn(
                        position=0,
                        segment_type="warmup",
                        repetitions=1,
                        work_duration_sec=600.0,
                        work_pace=easy_pace,
                        notes="Corsa facile 10 min di riscaldamento",
                    ),
                    WorkoutSegmentIn(
                        position=1,
                        segment_type="interval_block",
                        repetitions=5,
                        work_distance_km=1.0,
                        work_pace=interval_pace,
                        rest_duration_sec=90.0,
                        rest_type="jog",
                        notes=f"1 km @ {interval_pace}, recupero 90s trot",
                    ),
                    WorkoutSegmentIn(
                        position=2,
                        segment_type="cooldown",
                        repetitions=1,
                        work_duration_sec=600.0,
                        work_pace=easy_pace,
                        notes="Defaticamento 10 min",
                    ),
                ],
            )

        if stype == "tempo":
            return WorkoutTemplateIn(
                name="Corsa a soglia 25 min",
                description=(
                    f"Seduta di soglia: riscaldamento 10 min, "
                    f"25 min continui @ {tempo_pace}, defaticamento 10 min."
                ),
                type="threshold",
                segments=[
                    WorkoutSegmentIn(
                        position=0,
                        segment_type="warmup",
                        repetitions=1,
                        work_duration_sec=600.0,
                        work_pace=easy_pace,
                        notes="Corsa facile 10 min",
                    ),
                    WorkoutSegmentIn(
                        position=1,
                        segment_type="threshold",
                        repetitions=1,
                        work_duration_sec=1500.0,
                        work_pace=tempo_pace,
                        notes=f"25 min @ {tempo_pace} (Z3-Z4, ritmo soglia)",
                    ),
                    WorkoutSegmentIn(
                        position=2,
                        segment_type="cooldown",
                        repetitions=1,
                        work_duration_sec=600.0,
                        work_pace=easy_pace,
                        notes="Defaticamento 10 min",
                    ),
                ],
            )

        if stype == "long":
            return WorkoutTemplateIn(
                name="Lungo in Z2",
                description=(
                    f"Lungo progressivo a passo facile {easy_pace}. "
                    "Corsa continua in Z2, costruzione aerobica."
                ),
                type="easy",
                segments=[
                    WorkoutSegmentIn(
                        position=0,
                        segment_type="easy",
                        repetitions=1,
                        work_distance_km=18.0,
                        work_pace=easy_pace,
                        notes=f"Lungo 18 km @ {easy_pace}, ritmo conversazione Z2",
                    ),
                ],
            )

        if stype == "strides":
            return WorkoutTemplateIn(
                name="Corsa con allunghi 6×80m",
                description=(
                    f"Corsa facile 20 min @ {easy_pace} + 6 allunghi da 80m "
                    "a passo veloce con 90s recupero camminata."
                ),
                type="custom",
                segments=[
                    WorkoutSegmentIn(
                        position=0,
                        segment_type="easy",
                        repetitions=1,
                        work_duration_sec=1200.0,
                        work_pace=easy_pace,
                        notes="Corsa facile 20 min di attivazione",
                    ),
                    WorkoutSegmentIn(
                        position=1,
                        segment_type="strides",
                        repetitions=6,
                        work_distance_km=0.08,
                        work_pace="3:30/km",
                        rest_duration_sec=90.0,
                        rest_type="walk",
                        notes="80m a passo veloce, recupero 90s camminata",
                    ),
                ],
            )

        # Default: easy recovery
        return WorkoutTemplateIn(
            name="Corsa facile 35 min",
            description=(
                f"Corsa facile di recupero 35 min @ {easy_pace}. "
                "Z1-Z2, ritmo conversazione, cadenza rilassata."
            ),
            type="easy",
            segments=[
                WorkoutSegmentIn(
                    position=0,
                    segment_type="easy",
                    repetitions=1,
                    work_duration_sec=2100.0,
                    work_pace=easy_pace,
                    notes=f"35 min @ {easy_pace}, passo molto comodo Z1-Z2",
                ),
            ],
        )

    def chat_for_plan(
        self,
        messages: list[dict],
    ) -> tuple[str, bool, str | None]:
        """Offline fallback: immediately signals completion with no runner context."""
        return (
            "Modalità offline — la chat AI non è disponibile senza credenziali. "
            "Puoi comunque generare il piano: sarà calibrato sui tuoi allenamenti salvati.",
            True,
            None,
        )

    def chat_message(
        self,
        messages: list[dict],
        system: str,
    ) -> tuple[str, str, str]:
        """Offline fallback: coaching chat not available without credentials."""
        return (
            "Modalità offline — il coaching conversazionale non è disponibile senza "
            "credenziali Anthropic. Configura ANTHROPIC_API_KEY per usare questa funzione.",
            self.MODEL,
            "simple",
        )

    def plan_multiweek(
        self,
        request: PlanGenerateRequest,
        profile: AthleteProfile | None,
        metrics: TrainingMetrics | None,
        ramp_pct: float | None = None,
    ) -> dict:
        """Generate a complete multi-week plan using deterministic templates."""
        from datetime import datetime as _dt

        try:
            race_date = _dt.strptime(request.goal_date[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            race_date = date.today() + timedelta(weeks=16)

        today = date.today()
        start_date = today - timedelta(days=today.weekday())  # Monday of current week

        days_to_race = (race_date - today).days
        weeks_total = max(4, min(24, (days_to_race + 6) // 7))

        baseline_km = 30.0
        if metrics:
            baseline_km = max(metrics.chronic_load_km, metrics.acute_load_km, 20.0)

        long_day = request.long_run_day  # 0=Mon, 6=Sun
        dpw = max(3, min(6, request.days_per_week))

        # Build phase allocation
        taper_weeks = {"marathon": 3, "half": 2, "10k": 1, "5k": 1}.get(
            request.goal_type, 2
        )
        race_weeks = 1
        taper_weeks = min(taper_weeks, max(0, weeks_total - race_weeks))
        prep_weeks = max(0, weeks_total - taper_weeks - race_weeks)

        base_w = max(1, round(prep_weeks * 0.35))
        build_w = max(1, round(prep_weeks * 0.30))
        specific_w = max(1, round(prep_weeks * 0.20))
        peak_w = max(0, prep_weeks - base_w - build_w - specific_w)

        phase_alloc = [
            ("Base", base_w),
            ("Build", build_w),
            ("Specifico", specific_w),
            ("Peak", peak_w),
            ("Taper", taper_weeks),
            ("Gara", race_weeks),
        ]

        paces = _compute_paces(request.level, request.goal_type, request.goal_time)

        weeks_out = []
        week_num = 1
        for phase_name, phase_len in phase_alloc:
            if phase_len <= 0:
                continue
            for _i in range(phase_len):
                is_cutback = (week_num % 4 == 0) and phase_name not in ("Taper", "Gara")
                vol_factor = _phase_volume_factor(phase_name, is_cutback)
                target_km = round(baseline_km * vol_factor, 1)
                phase_desc = _phase_description(phase_name, week_num, is_cutback)
                sessions = _build_week_sessions(
                    phase_name=phase_name,
                    week_number=week_num,
                    days_per_week=dpw,
                    long_run_day=long_day,
                    target_km=target_km,
                    paces=paces,
                    goal_type=request.goal_type,
                    is_cutback=is_cutback,
                )
                weeks_out.append({
                    "week_number": week_num,
                    "phase": phase_name,
                    "target_km": target_km,
                    "description": phase_desc,
                    "sessions": sessions,
                })
                week_num += 1

        return {
            "weeks_total": len(weeks_out),
            "start_date": start_date.isoformat(),
            "weeks": weeks_out,
        }


# ── JSON parsing helpers ─────────────────────────────────────────────────────

def _parse_json_response(raw: str) -> dict:
    """Extract and parse a JSON object from the raw LLM response."""
    text = raw.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:])
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    # Find the outermost JSON object
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object found in response")
    return json.loads(text[start:end + 1])


def _validate_plan_structure(data: dict) -> None:
    """Validate the minimal required structure of a generated plan."""
    if "weeks" not in data or not isinstance(data["weeks"], list):
        raise ValueError("Plan missing 'weeks' list")
    if not data["weeks"]:
        raise ValueError("Plan has no weeks")
    for week in data["weeks"]:
        if "sessions" not in week or not isinstance(week["sessions"], list):
            raise ValueError(f"Week {week.get('week_number')} missing sessions")
        if len(week["sessions"]) == 0:
            raise ValueError(f"Week {week.get('week_number')} has no sessions")


# ── Offline plan generation helpers ─────────────────────────────────────────

def _compute_paces(level: str, goal_type: str, goal_time: str | None) -> dict[str, str]:
    """Compute pace targets for each session type based on level and goal."""
    defaults = {
        "beginner": {"easy": "6:30", "long": "6:45", "tempo": "5:50", "intervals": "5:20"},
        "intermediate": {"easy": "5:30", "long": "5:45", "tempo": "4:45", "intervals": "4:15"},
        "advanced": {"easy": "5:00", "long": "5:10", "tempo": "4:15", "intervals": "3:50"},
    }
    paces = defaults.get(level, defaults["intermediate"]).copy()

    if goal_time:
        try:
            parts = goal_time.split(":")
            if len(parts) == 3:
                total_sec = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            elif len(parts) == 2:
                total_sec = int(parts[0]) * 60 + int(parts[1])
            else:
                return {k: f"{v}/km" for k, v in paces.items()}

            dist_km = {
                "marathon": 42.195, "half": 21.0975, "10k": 10.0, "5k": 5.0,
            }.get(goal_type, 42.195)
            race_pace_sec = total_sec / dist_km
            easy_sec = race_pace_sec * 1.18
            long_sec = race_pace_sec * 1.22
            tempo_sec = race_pace_sec * 1.05
            intervals_sec = race_pace_sec * 0.97

            def _fmt(sec: float) -> str:
                m = int(sec // 60)
                s = int(sec % 60)
                return f"{m}:{s:02d}"

            paces = {
                "easy": _fmt(easy_sec),
                "long": _fmt(long_sec),
                "tempo": _fmt(tempo_sec),
                "intervals": _fmt(intervals_sec),
            }
        except (ValueError, TypeError, ZeroDivisionError):
            pass

    return {k: f"{v}/km" for k, v in paces.items()}


def _phase_volume_factor(phase: str, is_cutback: bool) -> float:
    factors = {
        "Base": 0.85, "Build": 1.0, "Specifico": 1.10,
        "Peak": 1.05, "Taper": 0.60, "Gara": 0.30,
    }
    f = factors.get(phase, 1.0)
    return f * 0.80 if is_cutback else f


def _phase_description(phase: str, week_num: int, is_cutback: bool) -> str:
    desc = {
        "Base": "Costruzione aerobica: volume progressivo in Z2, 80/20.",
        "Build": "Sviluppo del volume e introduzione delle sedute di soglia.",
        "Specifico": "Lavoro specifico: ripetute e lungo con porzioni a ritmo gara.",
        "Peak": "Affinamento: meno volume, qualità alta vicino al ritmo gara.",
        "Taper": "Scarico progressivo: mantieni l'intensità, riduci il volume.",
        "Gara": "Settimana gara: riposo, attivazione leggera, gareggia!",
    }.get(phase, "")
    if is_cutback:
        desc = f"Settimana di scarico (-20%). {desc}"
    return f"Settimana {week_num}: {desc}"


_REST_SESSION = {
    "day_of_week": -1,  # will be overwritten
    "session_type": "rest",
    "title": "Riposo",
    "description": "Recupero completo. Stretching leggero se desiderato.",
    "target_distance_km": None,
    "target_pace": None,
    "target_duration_min": None,
}

# Training day patterns per phase (indices into 0=Mon..6=Sun)
_PHASE_DAY_PATTERNS: dict[str, dict[int, tuple[str, ...]]] = {
    3: {
        "Base":     (1, 4, 6),   # Tue Thu Sun
        "Build":    (1, 4, 6),
        "Specifico":(1, 4, 6),
        "Peak":     (1, 4, 6),
        "Taper":    (1, 4, 6),
        "Gara":     (2, 5, 6),
    },
    4: {
        "Base":     (1, 3, 5, 6),
        "Build":    (1, 3, 5, 6),
        "Specifico":(1, 3, 5, 6),
        "Peak":     (1, 3, 5, 6),
        "Taper":    (1, 3, 5, 6),
        "Gara":     (1, 3, 5, 6),
    },
    5: {
        "Base":     (1, 2, 4, 5, 6),
        "Build":    (1, 2, 4, 5, 6),
        "Specifico":(1, 2, 4, 5, 6),
        "Peak":     (1, 2, 4, 5, 6),
        "Taper":    (1, 3, 4, 5, 6),
        "Gara":     (1, 3, 4, 5, 6),
    },
    6: {
        "Base":     (0, 1, 2, 4, 5, 6),
        "Build":    (0, 1, 2, 4, 5, 6),
        "Specifico":(0, 1, 2, 4, 5, 6),
        "Peak":     (0, 1, 2, 4, 5, 6),
        "Taper":    (0, 1, 2, 4, 5, 6),
        "Gara":     (0, 1, 3, 4, 5, 6),
    },
}


def _build_week_sessions(
    phase_name: str,
    week_number: int,
    days_per_week: int,
    long_run_day: int,
    target_km: float,
    paces: dict[str, str],
    goal_type: str,
    is_cutback: bool,
) -> list[dict]:
    """Build the 7 sessions for one training week."""
    dpw = max(3, min(6, days_per_week))
    pattern_map = _PHASE_DAY_PATTERNS.get(dpw, _PHASE_DAY_PATTERNS[4])
    training_days = set(pattern_map.get(phase_name, pattern_map.get("Base", (1, 3, 5, 6))))

    # Override: ensure long_run_day is a training day (unless Gara or Taper late)
    if phase_name not in ("Gara",):
        training_days.add(long_run_day)
        # Remove one day if too many
        while len(training_days) > dpw:
            candidates = sorted(training_days - {long_run_day})
            training_days.discard(candidates[0])

    easy_km = round(target_km * 0.10, 1)
    easy_km = max(easy_km, 5.0)
    long_km_base = round(target_km * 0.30, 1)
    long_km = max(long_km_base, 10.0)

    sessions: list[dict] = []
    sorted_training = sorted(training_days)

    # Assign session types to training days
    workout_assignments = _assign_workouts(
        phase_name, sorted_training, long_run_day, goal_type, is_cutback
    )

    for day in range(7):
        if day not in training_days:
            s = dict(_REST_SESSION)
            s["day_of_week"] = day
            sessions.append(s)
        else:
            wtype = workout_assignments.get(day, "easy")
            s = _make_session(wtype, day, easy_km, long_km, paces, phase_name, goal_type)
            sessions.append(s)

    return sorted(sessions, key=lambda x: x["day_of_week"])


def _assign_workouts(
    phase: str,
    training_days: list[int],
    long_day: int,
    goal_type: str,
    is_cutback: bool,
) -> dict[int, str]:
    """Assign session types to each training day."""
    result: dict[int, str] = {}

    if phase == "Gara":
        for i, d in enumerate(training_days):
            if i == len(training_days) - 1:
                result[d] = "race"
            elif i == len(training_days) - 2:
                result[d] = "strides"
            else:
                result[d] = "easy"
        return result

    # The long run goes on long_day if it's a training day
    long_assigned = False
    quality_types = _quality_for_phase(phase, goal_type, is_cutback)
    quality_idx = 0

    for d in training_days:
        if d == long_day and not long_assigned and phase not in ("Taper",):
            result[d] = "long"
            long_assigned = True
        elif quality_idx < len(quality_types):
            result[d] = quality_types[quality_idx]
            quality_idx += 1
        else:
            result[d] = "easy"

    # If long wasn't assigned, replace the last easy with long (Taper skip)
    if not long_assigned and phase not in ("Taper",):
        for d in reversed(training_days):
            if result.get(d) == "easy":
                result[d] = "long"
                break

    return result


def _quality_for_phase(phase: str, goal_type: str, is_cutback: bool) -> list[str]:
    """Return ordered list of quality sessions to schedule for a phase."""
    if is_cutback:
        return ["tempo"]
    return {
        "Base": ["strides", "easy"],
        "Build": ["tempo", "easy"],
        "Specifico": ["intervals", "tempo"],
        "Peak": ["intervals", "tempo"],
        "Taper": ["strides", "easy"],
        "Gara": [],
    }.get(phase, ["easy"])


def _make_session(
    stype: str,
    day: int,
    easy_km: float,
    long_km: float,
    paces: dict[str, str],
    phase: str,
    goal_type: str,
) -> dict:
    ep = paces.get("easy", "5:30/km")
    lp = paces.get("long", "5:45/km")
    tp = paces.get("tempo", "4:45/km")
    ip = paces.get("intervals", "4:15/km")

    if stype == "easy":
        return {
            "day_of_week": day,
            "session_type": "easy",
            "title": "Corsa facile",
            "description": f"Corsa facile in Z2 a {ep}. "
                           "Ritmo di conversazione, frequenza cardiaca controllata.",
            "target_distance_km": easy_km,
            "target_pace": ep,
            "target_duration_min": round(easy_km * _pace_to_min(ep) + 0.5),
        }
    if stype == "long":
        return {
            "day_of_week": day,
            "session_type": "long",
            "title": "Lungo",
            "description": f"Lungo progressivo {long_km:.0f} km in Z2 a {lp}. "
                           "Inizia lento, ultimi 3-4 km puoi accelerare leggermente.",
            "target_distance_km": long_km,
            "target_pace": lp,
            "target_duration_min": round(long_km * _pace_to_min(lp) + 0.5),
        }
    if stype == "tempo":
        tempo_km = round(easy_km * 1.5, 1)
        warmup = 2.0
        cooldown = 2.0
        quality_km = max(3.0, round(tempo_km - warmup - cooldown, 1))
        total_km = warmup + quality_km + cooldown
        return {
            "day_of_week": day,
            "session_type": "tempo",
            "title": "Corsa a soglia",
            "description": f"Riscaldamento {warmup:.0f} km easy + "
                           f"{quality_km:.0f} km @ {tp} (Z3-Z4) + "
                           f"defaticamento {cooldown:.0f} km easy.",
            "target_distance_km": round(total_km, 1),
            "target_pace": tp,
            "target_duration_min": round(
                warmup * _pace_to_min(ep)
                + quality_km * _pace_to_min(tp)
                + cooldown * _pace_to_min(ep)
                + 0.5
            ),
        }
    if stype == "intervals":
        reps = 5 if goal_type in ("marathon", "half") else 6
        rep_dist = 1.0 if goal_type in ("10k", "5k") else 1.5
        rec_min = 3 if goal_type in ("marathon", "half") else 2
        warmup = 2.5
        cooldown = 2.0
        quality_km = reps * rep_dist
        total_km = warmup + quality_km + cooldown
        return {
            "day_of_week": day,
            "session_type": "intervals",
            "title": "Ripetute",
            "description": f"Riscaldamento {warmup:.1f} km + "
                           f"{reps}×{rep_dist:.0f} km @ {ip} con {rec_min} min recupero + "
                           f"defaticamento {cooldown:.0f} km.",
            "target_distance_km": round(total_km, 1),
            "target_pace": ip,
            "target_duration_min": round(
                warmup * _pace_to_min(ep)
                + quality_km * _pace_to_min(ip)
                + reps * rec_min
                + cooldown * _pace_to_min(ep)
                + 0.5
            ),
        }
    if stype == "strides":
        return {
            "day_of_week": day,
            "session_type": "strides",
            "title": "Corsa con allunghi",
            "description": f"{easy_km:.0f} km facili a {ep} + 4 allunghi da 100 m "
                           "a ritmo veloce con 2 min recupero.",
            "target_distance_km": easy_km,
            "target_pace": ep,
            "target_duration_min": round(easy_km * _pace_to_min(ep) + 12 + 0.5),
        }
    if stype == "race":
        return {
            "day_of_week": day,
            "session_type": "race",
            "title": "GARA",
            "description": "Giorno di gara. Attivazione 15 min + 3 allunghi, poi gareggia!",
            "target_distance_km": None,
            "target_pace": None,
            "target_duration_min": None,
        }
    if stype == "cross":
        return {
            "day_of_week": day,
            "session_type": "cross",
            "title": "Cross training",
            "description": "Bici, nuoto o palestra leggera. Recupero attivo, no impatto.",
            "target_distance_km": None,
            "target_pace": None,
            "target_duration_min": 45.0,
        }
    # Default: easy
    return {
        "day_of_week": day,
        "session_type": "easy",
        "title": "Corsa facile",
        "description": f"Corsa facile in Z2 a {ep}.",
        "target_distance_km": easy_km,
        "target_pace": ep,
        "target_duration_min": round(easy_km * _pace_to_min(ep) + 0.5),
    }


def _pace_to_min(pace_str: str) -> float:
    """Convert 'M:SS/km' to minutes per km."""
    try:
        pace = pace_str.replace("/km", "").strip()
        parts = pace.split(":")
        return int(parts[0]) + int(parts[1]) / 60.0
    except (IndexError, ValueError):
        return 5.5


def _offline_easy_pace(level: str, metrics: TrainingMetrics | None) -> str:
    """Return a sensible easy pace string for the given level."""
    defaults = {"beginner": "6:30/km", "intermediate": "5:30/km", "advanced": "5:00/km"}
    return defaults.get(level, "5:30/km")


def _offline_tempo_pace(level: str, metrics: TrainingMetrics | None) -> str:
    defaults = {"beginner": "5:50/km", "intermediate": "4:45/km", "advanced": "4:15/km"}
    if metrics and metrics.phase:
        pass  # could refine from LT2 when available
    return defaults.get(level, "4:45/km")


def _offline_interval_pace(level: str, metrics: TrainingMetrics | None) -> str:
    defaults = {"beginner": "5:20/km", "intermediate": "4:15/km", "advanced": "3:50/km"}
    return defaults.get(level, "4:15/km")


def get_coach(settings: Settings | None = None) -> Coach:
    """Return the AI coach if a key is configured, else the offline coach."""
    settings = settings or get_settings()
    return AICoach(settings) if settings.ai_enabled else OfflineCoach()
