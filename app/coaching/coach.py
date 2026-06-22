"""Coaching backends and the offline rule-based fallback."""

from __future__ import annotations

import re
from typing import Protocol

from app.coaching import prompts
from app.config import Settings, get_settings
from app.schemas import CoachingResult, RunSummary, TrainingMetrics


class Coach(Protocol):
    def analyze_run(
        self, run: RunSummary, history: list[RunSummary], metrics: TrainingMetrics
    ) -> CoachingResult: ...

    def plan_week(
        self, runs: list[RunSummary], metrics: TrainingMetrics, weekly: list[dict]
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

    def _get_client(self):
        if self._client is None:
            from anthropic import Anthropic  # lazy import

            self._client = Anthropic(api_key=self.settings.anthropic_api_key)
        return self._client

    def _call(self, system: str, user: str, model: str, max_tokens: int = 1500) -> str:
        resp = self._get_client().messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(block.text for block in resp.content if getattr(block, "type", "") == "text")

    def analyze_run(
        self, run: RunSummary, history: list[RunSummary], metrics: TrainingMetrics
    ) -> CoachingResult:
        system = prompts.SINGLE_SYSTEM_PROMPT.format(athlete_profile=self.settings.athlete_profile)
        user = prompts.build_single_user_message(run, history, metrics)
        text = self._call(system, user, self.settings.coach_model)
        analysis, next_workout = _split_sections(text)
        return CoachingResult(
            scope="single", model=self.settings.coach_model,
            analysis=analysis, next_workout=next_workout,
        )

    def plan_week(
        self, runs: list[RunSummary], metrics: TrainingMetrics, weekly: list[dict]
    ) -> CoachingResult:
        system = prompts.WEEKLY_SYSTEM_PROMPT.format(athlete_profile=self.settings.athlete_profile)
        user = prompts.build_weekly_user_message(runs, metrics, weekly)
        text = self._call(system, user, self.settings.planner_model or self.settings.coach_model,
                          max_tokens=2000)
        analysis, next_workout = _split_sections(text)
        return CoachingResult(
            scope="weekly", model=self.settings.planner_model or self.settings.coach_model,
            analysis=analysis, next_workout=next_workout,
        )


class OfflineCoach:
    """Deterministic, rule-based coaching. No API key, no cost, always works.

    The logic mirrors the methodology in the system prompt: respect 80/20,
    recover after hard/long efforts, back off when the form state is fatigued.
    Useful as a fallback and as the default in demo/CI.
    """

    MODEL = "offline-rules"

    def analyze_run(
        self, run: RunSummary, history: list[RunSummary], metrics: TrainingMetrics
    ) -> CoachingResult:
        analysis = self._analyze_run_text(run, metrics)
        next_workout = self._suggest_next(run, metrics)
        return CoachingResult(
            scope="single", model=self.MODEL, analysis=analysis, next_workout=next_workout
        )

    def plan_week(
        self, runs: list[RunSummary], metrics: TrainingMetrics, weekly: list[dict]
    ) -> CoachingResult:
        analysis = self._analyze_week_text(metrics, weekly)
        next_workout = self._suggest_week(metrics)
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

    def _analyze_week_text(self, m: TrainingMetrics, weekly: list[dict]) -> str:
        pts = [
            f"Volume ultimi 7 giorni: {m.acute_load_km} km; media settimanale (28 gg): "
            f"{m.chronic_load_km} km.",
            f"ACWR: {m.acwr if m.acwr is not None else 'n/d'} → {m.form_explanation}",
            f"Trend del carico: {m.load_trend}.",
        ]
        if m.easy_ratio is not None:
            pts.append(f"Quota volume facile: {m.easy_ratio*100:.0f}% (target ~80%).")
        if m.monotony is not None and m.monotony > 2.0:
            pts.append(
                f"Monotonia alta ({m.monotony}): settimana poco variata, alterna meglio "
                "carichi alti e bassi."
            )
        return "- " + "\n- ".join(pts)

    def _suggest_week(self, m: TrainingMetrics) -> str:
        base = max(m.chronic_load_km, m.acute_load_km, 20.0)
        if m.form_state == "fatigued":
            target = round(base * 0.7)
            intro = f"Settimana di **scarico** (~{target} km), il carico è alto."
            sessions = [
                "Lun: riposo",
                "Mar: 6 km easy Z2",
                "Gio: 6 km easy + 4x1 min Z4 leggeri",
                "Sab: 5 km recupero Z1-Z2",
                "Dom: 8-10 km lento Z2",
            ]
        elif m.form_state == "detraining":
            target = round(base * 1.1)
            intro = f"Settimana di **ricostruzione** (~{target} km), puoi risalire gradualmente."
            sessions = [
                "Lun: riposo",
                "Mar: 8 km easy Z2",
                "Mer: 6 km recupero",
                "Gio: tempo 10 km con 5 km Z3-Z4",
                "Sab: 6 km easy",
                "Dom: lungo 14-16 km Z2",
            ]
        else:
            target = round(base * 1.05)
            intro = f"Settimana **di mantenimento/progressione** (~{target} km), 80/20."
            sessions = [
                "Lun: riposo o 5 km recupero",
                "Mar: 8-10 km easy Z2",
                "Mer: intervalli 6x800 m Z4 (rec 2')",
                "Ven: 8 km easy",
                "Dom: lungo 16-18 km Z2",
            ]
        return intro + "\n\n" + "\n".join(f"- {s}" for s in sessions)


def get_coach(settings: Settings | None = None) -> Coach:
    """Return the AI coach if a key is configured, else the offline coach."""
    settings = settings or get_settings()
    return AICoach(settings) if settings.ai_enabled else OfflineCoach()
