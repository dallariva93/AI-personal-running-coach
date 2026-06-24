"""Coaching backends and the offline rule-based fallback."""

from __future__ import annotations

import re
from typing import Protocol

from app.coaching import prompts
from app.config import Settings, get_settings
from app.exceptions import CoachingError
from app.logging_config import get_logger
from app.schemas import (
    AthleteProfile,
    AthleteSnapshot,
    CoachingResult,
    RunSummary,
    TrainingMetrics,
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
        return CoachingResult(
            scope="single", model=self.settings.coach_model,
            analysis=analysis, next_workout=next_workout,
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
        return CoachingResult(
            scope="weekly", model=model, analysis=analysis, next_workout=next_workout,
        )

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
        if profile.weekly_runs:
            bits.append(f"{profile.weekly_runs} uscite/sett")
        descr = ", ".join(bits) if bits else self.settings.athlete_profile
        if profile.physiology and profile.physiology.lt2_pace:
            descr += f". Soglia (LT2) ~{profile.physiology.lt2_pace}/km"
        return f"Atleta: {descr}."

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
        return CoachingResult(
            scope="single", model=self.MODEL, analysis=analysis, next_workout=next_workout
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
        return CoachingResult(
            scope="weekly", model=self.MODEL, analysis=analysis, next_workout=next_workout
        )

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
        if m.readiness_state and m.readiness_state != "unknown":
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
            sessions = self._assign_days(self._PHASE_SESSIONS[m.phase], available_days)
            return intro + "\n\n" + "\n".join(f"- {s}" for s in sessions)

        base = max(m.chronic_load_km, m.acute_load_km, 20.0)
        if m.form_state == "fatigued" or low_readiness:
            target = round(base * 0.7)
            reason = "il recupero è basso" if low_readiness else "il carico è alto"
            intro = f"Settimana di **scarico** (~{target} km), {reason}."
            contents = [
                "6 km easy Z2",
                "6 km easy + 4x1 min Z4 leggeri",
                "5 km recupero Z1-Z2",
                "8-10 km lento Z2",
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
        sessions = self._assign_days(contents, available_days)
        return intro + "\n\n" + "\n".join(f"- {s}" for s in sessions)


def get_coach(settings: Settings | None = None) -> Coach:
    """Return the AI coach if a key is configured, else the offline coach."""
    settings = settings or get_settings()
    return AICoach(settings) if settings.ai_enabled else OfflineCoach()
