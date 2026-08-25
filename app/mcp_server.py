"""MCP server: exposes the coaching data + engine as tools for Claude.

This is the server half of the Claude *custom connector* (see
``docs/MCP_CONNECTOR_ROADMAP.md``). It is deliberately a **thin adapter** over
the existing service layer — the same relationship the REST routes already have
with ``app/services`` — so there is exactly one implementation of every metric.

Two design rules the tools follow:

* **Read-only, with one deliberate exception.** Everything here reads. The one
  tool that writes — ``push_garmin_week``, which puts the planned sessions on
  the athlete's watch — was added knowingly, and is fenced: it does nothing
  without a confirmation code that only ``preview_garmin_week`` issues, that is
  bound to the week's exact content, and that expires. So the blast radius of a
  leaked URL stays "someone read my running data", and a push cannot happen
  without the preview having been shown first. Every other write stays on the
  authenticated REST API.
* **Parsimonious.** The chat context window is the scarce resource, not CPU.
  Tools return compact, pre-digested dicts (rounded floats, ISO dates, no ORM
  dumps); the expensive per-activity detail is a separate opt-in call.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.coaching.prompts import semantic_summary
from app.config import get_settings
from app.db.database import get_session_factory
from app.db.models import Activity, DailyCheckinRow, TrainingPlanSession
from app.exceptions import CollectionError
from app.logging_config import get_logger
from app.processing import compute_metrics
from app.processing.performance import estimate_thresholds
from app.processing.periodization import build_plan_spec
from app.processing.records import compute_personal_records
from app.schemas import PlanGenerateRequest, RunSummary, TrainingMetrics
from app.services import get_profile, hrv_history, latest_checkin
from app.services.athlete_model_service import estimate_athlete_model
from app.services.garmin_export import preview_week, push_week
from app.services.ingest import _activity_to_summary, _all_summaries, list_cross_training
from app.services.plan_service import get_current_plan
from app.services.yazio_sync import food_log, recent_nutrition
from app.services.yazio_sync import is_connected as yazio_connected

logger = get_logger("app.mcp")

SERVER_NAME = "running-coach"

INSTRUCTIONS = """\
Dati di allenamento di corsa di un singolo atleta, con il motore di analisi \
(carico, forma, periodizzazione, predizione gara) già applicato.

Parti sempre da `get_athlete_overview`: restituisce profilo, forma attuale, \
fase del piano e obiettivo in una sola chiamata, ed è il contesto minimo per \
qualsiasi ragionamento da allenatore. Approfondisci solo dopo, con i tool \
specifici.

Le metriche sono già calcolate: CTL/ATL/TSB, ACWR, distribuzione delle \
intensità, readiness. Non ricalcolarle a mano dai dati grezzi — usa i valori \
restituiti e interpretali.

Due regole che valgono sempre:

* **I ritmi si ancorano alla soglia misurata**, non al tempo obiettivo. \
Chiama `get_athlete_physiology` prima di prescrivere passi: contiene LT1/LT2, \
zone HR e il Digital Twin (tolleranza alla rampa, recupero, sensibilità al \
caldo, durabilità) appreso dallo storico di questo atleta.
* **I piani si generano con `generate_plan_draft`**, non a mano. Il motore \
deterministico garantisce volumi coerenti, rampe limitate, scarichi e taper \
al punto giusto. Tu interpreti e adatti il risultato; scrivere un piano \
freehand reintroduce esattamente gli errori che il motore evita.

Attenzione al tipo di seduta: il campo `type` di un'attività è **dedotto** dal \
payload Garmin e sbaglia spesso (una seduta di qualità può risultare "easy"). \
Quando l'attività porta `planned`, quello è ciò che il piano prescriveva ed è \
il dato attendibile — basa su quello la distribuzione delle intensità e \
l'aderenza, altrimenti l'80/20 ti sembrerà sano proprio quando non lo è.

Il carico non è solo corsa: `get_cross_training` restituisce bici, nuoto e \
palestra, che le metriche di corsa escludono di proposito. Consultalo prima di \
prescrivere una settimana pesante.

Se il diario alimentare è collegato, `get_nutrition` dà per ogni giorno \
calorie, macro e soprattutto `balance_kcal` (assunzione meno fabbisogno): un \
calo di forma da deficit energetico è indistinguibile da uno da troppo carico \
se guardi solo le corse. Controllalo prima di prescrivere un taglio di volume \
— ma leggi `days_logged`: con un diario compilato a metà i totali \
sottostimano l'assunzione reale. `get_food_diary` scende al singolo alimento \
di un giorno, e serve solo quando la domanda è *cosa* ha mangiato.

Puoi mettere le sedute pianificate sull'orologio, ma **solo se te lo chiede** e \
**una settimana per volta**: `preview_garmin_week` mostra cosa arriverebbe e \
restituisce un codice, `push_garmin_week` invia. Fai sempre vedere l'anteprima \
per intero e aspetta un sì esplicito prima di inviare — quello che approva non \
è un numero su uno schermo, è la seduta che poi corre. Se il piano si adatta \
nel frattempo il codice scade da solo: è voluto, rimostra l'anteprima. Non \
esportare mai di tua iniziativa, né più settimane insieme.

Quando un'attività ha `is_indoor: true` è un tapis roulant: il passo dipende \
dalla calibrazione del nastro e non è confrontabile con quello su strada, il \
dislivello a zero significa "nessun dato" e non "percorso piatto", e il meteo \
è assente di proposito. Contala nel volume, non usarla per giudicare la forma.
"""


@contextmanager
def _db() -> Iterator[Session]:
    """A short-lived session, one per tool call.

    Deliberately does not commit: the reading tools have nothing to commit, and
    the one writing tool (``push_garmin_week``) commits explicitly inside its
    own service call, so an accidental write can never ride out on the way past.
    """
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def _r(value: float | None, digits: int = 1) -> float | None:
    """Round for the wire — full float precision is noise in a chat context."""
    return None if value is None else round(value, digits)


def _parse_date(value: str | None, field: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:  # pragma: no cover - message asserted in tests
        raise ValueError(f"{field}: data non valida '{value}', usa YYYY-MM-DD") from exc


def _metrics_for(session: Session, ref: date | None = None) -> TrainingMetrics:
    """The single path to metrics: identical inputs to the dashboard and API."""
    return compute_metrics(
        _all_summaries(session),
        ref=ref,
        profile=get_profile(session),
        checkin=latest_checkin(session),
        hrv_history=hrv_history(session, ref=ref) if ref else hrv_history(session),
    )


def _metrics_payload(m: TrainingMetrics) -> dict[str, Any]:
    """The coach-relevant slice of TrainingMetrics (the full model is ~60 fields)."""
    return {
        "volume": {
            "weekly_km": _r(m.weekly_distance_km),
            "acute_load_km_7d": _r(m.acute_load_km),
            "chronic_load_km_28d": _r(m.chronic_load_km),
            "load_trend": m.load_trend,
        },
        "form": {
            "ctl_fitness": _r(m.ctl),
            "atl_fatigue": _r(m.atl),
            "tsb_form": _r(m.tsb),
            "state": m.form_state,
            "explanation": m.form_explanation,
        },
        "risk": {
            "acwr": _r(m.acwr, 2),
            "monotony": _r(m.monotony, 2),
            "injury_level": m.injury_level,
            "injury_factors": m.injury_factors,
        },
        "intensity": {
            "easy_ratio": _r(m.easy_ratio, 2),
            "moderate_ratio": _r(m.moderate_ratio, 2),
            "hard_ratio": _r(m.hard_ratio, 2),
            "target_easy_ratio": 0.8,
        },
        "readiness": {
            "score": _r(m.readiness),
            "state": m.readiness_state,
            "hrv_rmssd": _r(m.hrv_rmssd),
            "hrv_status": m.hrv_status,
        },
        "phase": {
            "name": m.phase,
            "focus": m.phase_focus,
            "weeks_to_race": m.weeks_to_race,
            "volume_target_km": _r(m.phase_volume_target_km),
        },
        "efficiency": {
            "aerobic_efficiency": _r(m.aerobic_efficiency, 2),
            "trend": m.efficiency_trend,
        },
        "runs_counted": m.runs_count,
    }


def _summary_payload(s: RunSummary) -> dict[str, Any]:
    """One activity, compact — the shape used in every list response."""
    return {
        "date": s.date,
        "type": s.activity_type,
        "distance_km": _r(s.distance_km),
        "duration_min": _r(s.duration_min),
        "avg_pace": s.avg_pace,
        "avg_hr": s.avg_hr,
        "elevation_gain_m": _r(s.elevation_gain_m, 0),
        "rpe": s.rpe,
        # Treadmill: pace depends on the belt, elevation is meaningless and
        # there is no weather. Flagged so none of it reads as fitness.
        "is_indoor": s.is_indoor,
    }


def _aggregate(runs: list[RunSummary]) -> dict[str, Any]:
    """Totals for a date range — the unit `compare_periods` reasons over."""
    if not runs:
        return {"runs": 0, "total_km": 0.0, "total_hours": 0.0}
    total_km = sum(r.distance_km for r in runs)
    total_min = sum(r.duration_min for r in runs)
    hr_values = [r.avg_hr for r in runs if r.avg_hr]
    # Pace over the whole period, not the mean of per-run paces: a 3 km and a
    # 30 km run must not weigh the same.
    pace_sec = (total_min * 60 / total_km) if total_km else None
    return {
        "runs": len(runs),
        "total_km": _r(total_km),
        "total_hours": _r(total_min / 60),
        "longest_run_km": _r(max(r.distance_km for r in runs)),
        "avg_pace": f"{int(pace_sec // 60)}:{int(pace_sec % 60):02d}/km" if pace_sec else None,
        "avg_hr": round(sum(hr_values) / len(hr_values)) if hr_values else None,
        "total_elevation_m": _r(sum(r.elevation_gain_m or 0 for r in runs), 0),
    }


def _planned_sessions_for(
    session: Session, activity_ids: list[int]
) -> dict[int, dict[str, Any]]:
    """What each activity was *supposed* to be, from the plan it executed.

    `activity_type` is inferred from the Garmin payload, so a quality session
    can land labelled "easy" — which quietly makes the 80/20 split look healthy
    while it isn't. The plan knows what was prescribed; the execution scorer
    already links the two. Surfacing that link turns adherence from a guess
    into a fact.
    """
    if not activity_ids:
        return {}
    rows = session.scalars(
        select(TrainingPlanSession).where(
            TrainingPlanSession.executed_activity_id.in_(activity_ids)
        )
    ).all()
    return {
        row.executed_activity_id: {
            "session_type": row.session_type,
            "title": row.title,
            "target_distance_km": _r(row.target_distance_km),
            "target_pace": row.target_pace,
            "execution_status": row.execution_status,
            "execution_score": _r(row.execution_score, 0),
            "plan_session_id": row.id,
        }
        for row in rows
        if row.executed_activity_id is not None
    }


def _in_range(runs: list[RunSummary], start: date | None, end: date | None) -> list[RunSummary]:
    out = []
    for r in runs:
        try:
            d = date.fromisoformat(r.date)
        except ValueError:  # defensive: a malformed stored date must not 500
            continue
        if (start is None or d >= start) and (end is None or d <= end):
            out.append(r)
    return out


def build_mcp_server():  # noqa: ANN201 - FastMCP, imported lazily
    """Build the MCP server.

    The import is function-local so the ``mcp`` dependency is only required
    when the connector is actually enabled — the REST app, the CLI and the
    test suite keep importing ``app.main`` without it.
    """
    from mcp.server.fastmcp import FastMCP
    from mcp.server.transport_security import TransportSecuritySettings

    settings = get_settings()
    hosts = settings.mcp_transport_hosts
    if hosts:
        security = TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            # Keep localhost usable alongside the deploy hostname so the same
            # config works for a local MCP Inspector run.
            allowed_hosts=[*hosts, "127.0.0.1:*", "localhost:*"],
            allowed_origins=[
                *(f"https://{h}" for h in hosts),
                "http://127.0.0.1:*",
                "http://localhost:*",
            ],
        )
    else:
        # The SDK default allows ONLY localhost, which would 421 every request
        # to a deployed hostname. Off is the honest default here; set
        # MCP_ALLOWED_HOSTS to turn it back on (see config.mcp_transport_hosts).
        security = TransportSecuritySettings(enable_dns_rebinding_protection=False)
        logger.warning(
            "MCP: host validation disabled (MCP_ALLOWED_HOSTS not set). "
            "Set it to the public hostname to enable DNS-rebinding protection."
        )

    # stateless_http: every call is self-contained, so no session affinity is
    # needed — and a redeploy can't strand the connector with a dead
    # Mcp-Session-Id. streamable_http_path="/" makes the mounted URL exactly
    # the secret path, with no extra suffix.
    mcp = FastMCP(
        SERVER_NAME,
        instructions=INSTRUCTIONS,
        stateless_http=True,
        streamable_http_path="/",
        transport_security=security,
    )

    @mcp.tool()
    def get_athlete_overview() -> dict[str, Any]:
        """Profilo, forma attuale, fase del piano e obiettivo in una chiamata.

        Chiamalo SEMPRE per primo in una conversazione di coaching: è il
        contesto minimo per rispondere da allenatore. Evita di chiamare
        get_training_metrics subito dopo — il riassunto è già incluso qui.
        """
        with _db() as session:
            profile = get_profile(session)
            metrics = _metrics_for(session)
            plan = get_current_plan(session)
            goal = profile.goal if profile else None
            return {
                "athlete": {
                    "level": profile.level,
                    "age": profile.age,
                    "experience_years": profile.experience_years,
                    "weekly_runs": profile.weekly_runs,
                    "max_hr": profile.max_hr,
                    "resting_hr": profile.resting_hr,
                    "risk_tolerance": profile.risk_tolerance,
                } if profile else None,
                "goal": {
                    "type": goal.goal_type,
                    "date": goal.target_date,
                    "target_time": goal.target_time,
                    "days_to_go": goal.days_to_go(),
                } if goal and goal.target_date else None,
                "summary": semantic_summary(metrics),
                "form": {
                    "tsb": _r(metrics.tsb),
                    "state": metrics.form_state,
                    "readiness": _r(metrics.readiness),
                    "readiness_state": metrics.readiness_state,
                },
                "volume": {
                    "weekly_km": _r(metrics.weekly_distance_km),
                    "chronic_load_km_28d": _r(metrics.chronic_load_km),
                    "trend": metrics.load_trend,
                },
                "phase": metrics.phase,
                "weeks_to_race": metrics.weeks_to_race,
                "race_prediction": metrics.predicted_race_time,
                "active_plan": {
                    "id": plan.id,
                    "weeks_total": plan.weeks_total,
                    "current_week": plan.current_week_number,
                    "weeks_remaining": plan.weeks_remaining,
                } if plan else None,
                "runs_in_history": metrics.runs_count,
            }

    @mcp.tool()
    def get_training_metrics(ref_date: str | None = None) -> dict[str, Any]:
        """Metriche complete di carico, forma, rischio e intensità.

        Usalo quando servono i numeri di dettaglio che l'overview non contiene
        (ACWR, monotonia, rischio infortunio, distribuzione 80/20, efficienza).
        Passa `ref_date` (YYYY-MM-DD) per ricostruire lo stato di forma a una
        data passata, utile per confrontare periodi o rileggere una gara.
        """
        ref = _parse_date(ref_date, "ref_date")
        with _db() as session:
            metrics = _metrics_for(session, ref=ref)
            payload = _metrics_payload(metrics)
            payload["as_of"] = (ref or date.today()).isoformat()
            payload["summary"] = semantic_summary(metrics)
            return payload

    @mcp.tool()
    def list_activities(
        from_date: str | None = None,
        to_date: str | None = None,
        limit: int = 30,
    ) -> dict[str, Any]:
        """Elenco compatto delle corse in un intervallo, dalla più recente.

        Usalo per vedere cosa è stato fatto davvero (l'allenamento reale, non
        quello pianificato). Senza filtri restituisce le ultime `limit` corse.

        Ogni voce porta il suo `id`: passalo a get_activity_detail per il
        dettaglio, senza tirare a indovinare.

        Ogni voce porta anche `planned`, cioè la seduta del piano che quella
        corsa ha eseguito, quando c'è. Il campo `type` è dedotto dal payload
        Garmin e può sbagliare (una qualità etichettata "easy"): quando
        `planned` è presente, è quello il dato attendibile — usalo per
        giudicare la distribuzione delle intensità e l'aderenza.
        """
        start = _parse_date(from_date, "from_date")
        end = _parse_date(to_date, "to_date")
        limit = max(1, min(limit, 200))
        with _db() as session:
            # Read rows, not summaries: the listing has to carry each activity's
            # id or `get_activity_detail` becomes a guessing game.
            query = select(Activity).where(Activity.sport == "run")
            if start:
                query = query.where(Activity.date >= start.isoformat())
            if end:
                query = query.where(Activity.date <= end.isoformat())
            rows = list(session.scalars(query.order_by(Activity.date.desc())).all())
            window = rows[:limit]
            planned = _planned_sessions_for(session, [r.id for r in window])
            return {
                "range": {
                    "from": start.isoformat() if start else None,
                    "to": end.isoformat() if end else None,
                },
                "returned": len(window),
                "matching_total": len(rows),
                "totals": _aggregate([_activity_to_summary(r) for r in window]),
                "activities": [
                    {
                        "id": row.id,
                        **_summary_payload(_activity_to_summary(row)),
                        "planned": planned.get(row.id),
                    }
                    for row in window
                ],
            }

    @mcp.tool()
    def get_activity_detail(activity_id: int) -> dict[str, Any]:
        """Dettaglio completo di una corsa: split al km, zone HR, meteo, note.

        Chiamalo solo quando l'analisi richiede davvero il dentro-della-seduta
        (es. valutare la tenuta del ritmo o il drift cardiaco), non per
        scorrere lo storico: gli id vengono da list_activities.

        Include `planned`: cosa prevedeva il piano per questa corsa, con il
        punteggio di esecuzione. Se c'è, fidati di quello e non del campo
        `type`, che è dedotto e può essere sbagliato.

        Include `laps`: i lap reali dell'orologio, uno per ogni ripetuta e per
        ogni recupero, ciascuno con la sua distanza. È il campo da leggere per
        una seduta a ripetute — `splits_km` media tutto su chilometri interi e
        rende invisibile una serie da 500 m. Quando c'è `role` viene da Garmin
        (allenamento strutturato); quando manca, deducilo tu dai numeri invece
        di darlo per scontato.
        """
        with _db() as session:
            row = session.get(Activity, activity_id)
            if row is None or row.sport != "run":
                raise ValueError(f"Corsa con id {activity_id} non trovata.")
            s = _activity_to_summary(row)
            payload = _summary_payload(s)
            payload.update({
                "id": row.id,
                "start_time": s.start_time,
                "max_hr": s.max_hr,
                "avg_cadence": s.avg_cadence,
                # The real laps: one entry per repetition and per recovery,
                # each with its own distance. `splits_km` below averages the
                # same run into whole kilometres, which makes an interval
                # session unreadable — prefer `laps` whenever it is present.
                "laps": s.laps,
                "splits_km": s.splits_km,
                "hr_zones_min": s.hr_zones,
                "temperature_c": _r(s.temperature_c),
                "humidity_pct": _r(s.humidity_pct, 0),
                "garmin_training_load": _r(s.garmin_training_load, 0),
                "notes": s.notes,
                # What the plan prescribed, when this activity executed one.
                # `type` above is inferred from the Garmin payload and can be
                # wrong; this is the ground truth.
                "planned": _planned_sessions_for(session, [row.id]).get(row.id),
            })
            return payload

    @mcp.tool()
    def get_current_training_plan() -> dict[str, Any]:
        """Il piano attivo: struttura, avanzamento e settimana corrente.

        Usalo per rispondere su cosa è previsto, come procede l'aderenza, o
        prima di suggerire modifiche. Le settimane sono riassunte; per le
        sedute di una settimana specifica usa get_plan_week.
        """
        with _db() as session:
            plan = get_current_plan(session)
            if plan is None:
                return {"active_plan": None, "hint": "Nessun piano attivo."}
            return {
                "id": plan.id,
                "goal": {
                    "type": plan.goal_type,
                    "date": plan.goal_date,
                    "target_time": plan.goal_time,
                },
                "level": plan.level,
                "start_date": plan.start_date,
                "weeks_total": plan.weeks_total,
                "current_week_number": plan.current_week_number,
                "weeks_remaining": plan.weeks_remaining,
                "overall_completion_pct": _r(plan.overall_completion_pct, 0),
                "weeks": [
                    {
                        "week_number": w.week_number,
                        "phase": w.phase,
                        "target_km": _r(w.target_km),
                        "completion_pct": _r(w.completion_pct, 0),
                        "rationale": w.rationale,
                    }
                    for w in plan.weeks
                ],
            }

    @mcp.tool()
    def get_plan_week(week_number: int) -> dict[str, Any]:
        """Le sedute di una settimana del piano, con passi, segmenti e fueling.

        Usalo quando la domanda riguarda l'esecuzione concreta ("cosa faccio
        giovedì?", "com'è strutturato il lungo?"). Il numero di settimana viene
        da get_current_training_plan.
        """
        with _db() as session:
            plan = get_current_plan(session)
            if plan is None:
                raise ValueError("Nessun piano attivo.")
            week = next((w for w in plan.weeks if w.week_number == week_number), None)
            if week is None:
                raise ValueError(
                    f"Settimana {week_number} inesistente "
                    f"(il piano ne ha {plan.weeks_total})."
                )
            days = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
            return {
                "week_number": week.week_number,
                "phase": week.phase,
                "target_km": _r(week.target_km),
                "rationale": week.rationale,
                "completion_pct": _r(week.completion_pct, 0),
                "is_current_week": week.week_number == plan.current_week_number,
                "sessions": [
                    {
                        "id": s.id,
                        "day": days[s.day_of_week] if 0 <= s.day_of_week < 7 else None,
                        "type": s.session_type,
                        "title": s.title,
                        "description": s.description,
                        "target_distance_km": _r(s.target_distance_km),
                        "target_pace": s.target_pace,
                        "completed": s.completed,
                        "execution_status": s.execution_status,
                        "adjustment_note": s.adjustment_note,
                        "fueling": s.fueling,
                        "segments": [
                            {
                                "position": seg.position,
                                "type": seg.segment_type,
                                "repetitions": seg.repetitions,
                                "work_distance_km": _r(seg.work_distance_km),
                                "work_duration_sec": _r(seg.work_duration_sec, 0),
                                "work_pace": seg.work_pace,
                                "rest_duration_sec": _r(seg.rest_duration_sec, 0),
                                "rest_type": seg.rest_type,
                                "notes": seg.notes,
                            }
                            for seg in s.segments
                        ],
                    }
                    for s in week.sessions
                ],
            }

    @mcp.tool()
    def get_race_prediction() -> dict[str, Any]:
        """Tempo gara previsto sull'obiettivo e probabilità di centrarlo.

        Usalo per domande sul risultato atteso o sulla realisticità
        dell'obiettivo. La previsione deriva dalle prestazioni recenti, non dal
        tempo desiderato.
        """
        with _db() as session:
            profile = get_profile(session)
            metrics = _metrics_for(session)
            goal = profile.goal if profile else None
            if not metrics.predicted_race_time:
                return {
                    "prediction": None,
                    "hint": (
                        "Previsione non disponibile: serve un obiettivo di gara "
                        "e uno storico sufficiente."
                    ),
                    "goal_type": goal.goal_type if goal else None,
                }
            return {
                "goal_type": goal.goal_type if goal else None,
                "goal_date": goal.target_date if goal else None,
                "target_time": goal.target_time if goal else None,
                "predicted_time": metrics.predicted_race_time,
                "probability_of_target": _r(metrics.race_probability, 2),
                "confidence": metrics.race_confidence,
                "current_fitness_ctl": _r(metrics.ctl),
                "weeks_to_race": metrics.weeks_to_race,
            }

    @mcp.tool()
    def compare_periods(
        period_a_from: str,
        period_a_to: str,
        period_b_from: str,
        period_b_to: str,
    ) -> dict[str, Any]:
        """Confronta volumi, ritmi e intensità fra due intervalli di date.

        Il tool giusto per le domande "sto meglio di prima?": stagione contro
        stagione, blocco contro blocco, questo mese contro lo scorso. Tutte le
        date in YYYY-MM-DD.
        """
        a_from = _parse_date(period_a_from, "period_a_from")
        a_to = _parse_date(period_a_to, "period_a_to")
        b_from = _parse_date(period_b_from, "period_b_from")
        b_to = _parse_date(period_b_to, "period_b_to")
        with _db() as session:
            runs = _all_summaries(session)
            a_runs = _in_range(runs, a_from, a_to)
            b_runs = _in_range(runs, b_from, b_to)
            a, b = _aggregate(a_runs), _aggregate(b_runs)
            # Form at the END of each window: the state the athlete reached,
            # not today's state projected backwards.
            a_metrics = _metrics_for(session, ref=a_to) if a_to else None
            b_metrics = _metrics_for(session, ref=b_to) if b_to else None
            delta_km = (a["total_km"] or 0) - (b["total_km"] or 0)
            return {
                "period_a": {"from": period_a_from, "to": period_a_to, **a,
                             "ctl_at_end": _r(a_metrics.ctl) if a_metrics else None},
                "period_b": {"from": period_b_from, "to": period_b_to, **b,
                             "ctl_at_end": _r(b_metrics.ctl) if b_metrics else None},
                "delta": {
                    "total_km": _r(delta_km),
                    "total_km_pct": (
                        _r(delta_km / b["total_km"] * 100, 0) if b["total_km"] else None
                    ),
                    "runs": a["runs"] - b["runs"],
                },
            }

    @mcp.tool()
    def get_athlete_physiology() -> dict[str, Any]:
        """Soglie, zone HR, vincoli di calendario, gare secondarie e Digital Twin.

        Chiamalo PRIMA di prescrivere ritmi o di costruire un piano: contiene
        ciò che rende i passi *tuoi* invece che generici. In particolare
        `thresholds.lt2_pace` è l'ancora corretta per i ritmi — non derivarli
        mai dal tempo obiettivo, che è un'aspirazione, non una misura.

        `digital_twin` è appreso dallo storico: tolleranza alla rampa, tempo di
        recupero, sensibilità al caldo e durabilità, ognuno con la sua
        confidenza (0-100). Se `learning` è true il dato è ancora provvisorio:
        usalo con prudenza e dillo.
        """
        with _db() as session:
            profile = get_profile(session)
            physiology = profile.physiology if profile else None
            # Stored thresholds are the athlete's own; the estimate is the
            # fallback so the coach is never left without a pace anchor.
            estimated = estimate_thresholds(_all_summaries(session))
            twin = estimate_athlete_model(session)
            zones = profile.zones if profile and profile.zones else None

            def _estimate(entry) -> dict[str, Any] | None:
                if entry is None:
                    return None
                return {
                    "value": _r(entry.value, 2),
                    "confidence": entry.confidence,
                    "learning": entry.learning,
                }

            lt2 = (physiology.lt2_pace if physiology else None) or (
                estimated.lt2_pace if estimated else None
            )
            if physiology and physiology.lt2_pace:
                source = "profilo"
            elif estimated and estimated.lt2_pace:
                source = "stimato dalle corse recenti"
            else:
                # Being explicit beats a plausible-looking null: without an
                # anchor the coach must say so, not quietly invent paces.
                source = "non disponibile"

            return {
                "thresholds": {
                    "lt1_pace": (physiology.lt1_pace if physiology else None)
                    or (estimated.lt1_pace if estimated else None),
                    "lt2_pace": lt2,
                    "critical_speed": (physiology.critical_speed if physiology else None)
                    or (estimated.critical_speed if estimated else None),
                    "lactate_threshold_hr": physiology.lactate_threshold_hr
                    if physiology
                    else None,
                    "source": source,
                    "hint": None if lt2 else (
                        "Nessuna soglia disponibile: servono sforzi intensi recenti "
                        "(tempo/ripetute/gara) o una soglia inserita nel profilo. "
                        "Senza, non prescrivere ritmi precisi — dillo all'atleta."
                    ),
                },
                "hr_zones": {
                    "z1": zones.z1_hr, "z2": zones.z2_hr, "z3": zones.z3_hr,
                    "z4": zones.z4_hr, "z5": zones.z5_hr,
                } if zones else None,
                "max_hr": profile.max_hr if profile else None,
                "resting_hr": profile.resting_hr if profile else None,
                "availability": {
                    # A plan is a negotiation with a calendar: without these the
                    # coach must ask rather than assume.
                    "available_days": profile.available_days if profile else [],
                    "weekly_runs": profile.weekly_runs if profile else None,
                    "risk_tolerance": profile.risk_tolerance if profile else None,
                },
                "races": [
                    {
                        "name": r.name,
                        "type": r.race_type,
                        "date": r.date,
                        "target_time": r.target_time,
                        "priority": r.priority,
                    }
                    for r in (profile.races if profile else [])
                ],
                "digital_twin": {
                    "ramp_tolerance_pct": _estimate(twin.ramp_tolerance_pct),
                    "recovery_halflife_days": _estimate(twin.recovery_halflife_days),
                    "heat_sensitivity_s_per_c": _estimate(twin.heat_sensitivity_s_per_c),
                    "durability_0_100": _estimate(twin.durability),
                    "computed_at": twin.computed_at,
                },
            }

    @mcp.tool()
    def generate_plan_draft(
        goal_type: str | None = None,
        goal_date: str | None = None,
        goal_time: str | None = None,
        days_per_week: int = 4,
        long_run_day: int = 6,
        include_sessions: bool = True,
    ) -> dict[str, Any]:
        """Genera una BOZZA di piano col motore di periodizzazione deterministico.

        **Usa questo tool invece di inventare un piano a mano.** Il motore
        garantisce proprietà che la scrittura libera sbaglia: i volumi tornano
        (il totale settimanale è la somma delle sedute), la progressione
        rispetta un limite di rampa, gli scarichi cadono dove il carico lo
        richiede, il taper è progressivo, le gare B/C finiscono sulle loro date
        e l'obiettivo viene confrontato con la forma reale (`goal_realism`).

        Il tuo lavoro è il resto: interpretarla, spiegarla, adattarla alla
        conversazione e segnalare cosa non torna. Puoi rigenerarla con
        parametri diversi quante volte serve.

        Il piano è completo, dalla settimana 1 alla gara. Ogni settimana ha
        `sessions` (le sedute di allenamento) e `rest_days` (i giorni di
        riposo, come elenco di nomi): insieme coprono tutti e sette i giorni.

        Parametri omessi → presi dall'obiettivo salvato nel profilo.
        `long_run_day`: 0=lunedì … 6=domenica.

        NON salva nulla: è una bozza da leggere, il piano attivo dell'app non
        viene toccato. Dillo esplicitamente quando la presenti.
        """
        with _db() as session:
            profile = get_profile(session)
            stored_goal = profile.goal if profile else None
            goal_type = goal_type or (stored_goal.goal_type if stored_goal else None)
            goal_date = goal_date or (stored_goal.target_date if stored_goal else None)
            goal_time = goal_time or (stored_goal.target_time if stored_goal else None)
            if not goal_type or not goal_date:
                raise ValueError(
                    "Servono goal_type e goal_date (nessun obiettivo salvato nel "
                    "profilo): passali esplicitamente, es. goal_type='marathon', "
                    "goal_date='2026-10-25'."
                )
            _parse_date(goal_date, "goal_date")
            if not 1 <= days_per_week <= 7:
                raise ValueError("days_per_week deve essere fra 1 e 7.")
            if not 0 <= long_run_day <= 6:
                raise ValueError("long_run_day deve essere fra 0 (lunedì) e 6 (domenica).")

            metrics = _metrics_for(session)
            spec = build_plan_spec(
                PlanGenerateRequest(
                    goal_type=goal_type,
                    goal_date=goal_date,
                    goal_time=goal_time,
                    level=profile.level if profile else "intermediate",
                    days_per_week=days_per_week,
                    long_run_day=long_run_day,
                ),
                profile=profile,
                metrics=metrics,
            )
            days = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
            weeks = []
            for w in spec["weeks"]:
                out: dict[str, Any] = {
                    "week_number": w["week_number"],
                    "phase": w["phase"],
                    "target_km": _r(w["target_km"]),
                    "description": w["description"],
                }
                if include_sessions:
                    # Rest days collapse to a list of day names. The engine
                    # always emits 7 sessions per week, so ~3 of them were
                    # identical "Riposo / recupero completo" objects — 35% of
                    # this payload saying nothing. Training sessions + rest
                    # days still reconstruct the full week.
                    training = [s for s in w["sessions"] if s["session_type"] != "rest"]
                    out["rest_days"] = [
                        days[s["day_of_week"]]
                        for s in w["sessions"]
                        if s["session_type"] == "rest" and 0 <= s["day_of_week"] < 7
                    ]
                    out["sessions"] = [
                        {
                            "day": days[s["day_of_week"]] if 0 <= s["day_of_week"] < 7 else None,
                            "type": s["session_type"],
                            "title": s["title"],
                            "description": s["description"],
                            "km": _r(s.get("target_distance_km")),
                            "pace": s.get("target_pace"),
                            "duration_min": _r(s.get("target_duration_min"), 0),
                        }
                        for s in training
                    ]
                weeks.append(out)
            return {
                "is_draft": True,
                "saved": False,
                "note": (
                    "Bozza generata dal motore di periodizzazione. Non è il piano "
                    "attivo: per renderlo tale va generato dall'app."
                ),
                "goal": {"type": goal_type, "date": goal_date, "target_time": goal_time},
                "weeks_total": spec["weeks_total"],
                "start_date": spec["start_date"],
                "baseline_km": _r(spec["baseline_km"]),
                "goal_realism": spec.get("goal_realism"),
                "weeks": weeks,
            }

    @mcp.tool()
    def get_training_history_summary(months: int = 6) -> dict[str, Any]:
        """Aggregati mese per mese: volume, ritmo, intensità, sedute lunghe.

        Il modo economico di avere in contesto una stagione intera senza
        scaricare centinaia di attività. Usalo per giudicare la progressione a
        lungo termine, la costanza e la struttura di un blocco passato — cioè
        ogni volta che devi costruire o valutare un piano pluri-mensile.
        """
        months = max(1, min(months, 36))
        with _db() as session:
            runs = _all_summaries(session)
        buckets: dict[str, list[RunSummary]] = {}
        for r in runs:
            try:
                d = date.fromisoformat(r.date)
            except ValueError:
                continue
            buckets.setdefault(f"{d.year:04d}-{d.month:02d}", []).append(r)

        keys = sorted(buckets, reverse=True)[:months]
        out = []
        for key in keys:
            group = buckets[key]
            agg = _aggregate(group)
            hard = [r for r in group if r.activity_type in ("tempo", "intervals", "race")]
            long_runs = [r for r in group if r.distance_km >= 18]
            agg.update({
                "month": key,
                "hard_sessions": len(hard),
                "long_runs_18k_plus": len(long_runs),
            })
            out.append(agg)
        return {
            "months_returned": len(out),
            "months": out,
            "hint": (
                "Nessuno storico in questo intervallo." if not out else None
            ),
        }

    @mcp.tool()
    def get_personal_records() -> dict[str, Any]:
        """Record personali per distanza (1K, 5K, 10K, mezza, maratona).

        Usalo per ancorare i ritmi a prestazioni reali e per valutare se un
        obiettivo è coerente con quello che l'atleta ha già dimostrato.
        """
        with _db() as session:
            activities = list(
                session.scalars(
                    select(Activity).where(Activity.sport == "run")
                ).all()
            )
            records = compute_personal_records(activities)
            return {
                "records": records,
                "hint": "Nessun record: storico insufficiente." if not records else None,
            }

    @mcp.tool()
    def get_cross_training(limit: int = 30) -> dict[str, Any]:
        """Bici, nuoto e palestra: il carico che non compare nelle metriche di corsa.

        Le metriche di corsa escludono di proposito il cross-training, per non
        inquinare CTL/ATL e la distribuzione delle intensità. Chiama questo
        tool quando devi valutare il carico *complessivo* o pianificare una
        settimana realistica per chi fa anche altro.
        """
        limit = max(1, min(limit, 100))
        with _db() as session:
            rows = list_cross_training(session, limit=limit)
            by_sport: dict[str, int] = {}
            for row in rows:
                by_sport[row.sport] = by_sport.get(row.sport, 0) + 1
            return {
                "returned": len(rows),
                "by_sport": by_sport,
                "sessions": [
                    {
                        "date": r.date,
                        "sport": r.sport,
                        "duration_min": _r(r.duration_min),
                        "distance_km": _r(r.distance_km),
                        "avg_hr": r.avg_hr,
                    }
                    for r in rows
                ],
            }

    @mcp.tool()
    def get_readiness_history(days: int = 30) -> dict[str, Any]:
        """Andamento di sonno, fatica, dolori, motivazione e HRV.

        Usalo quando la domanda riguarda il recupero nel tempo ("sono stanco da
        settimane?"), o prima di alzare il carico: un trend in peggioramento è
        un veto che le medie di volume non mostrano.
        """
        days = max(1, min(days, 365))
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        with _db() as session:
            rows = list(
                session.scalars(
                    select(DailyCheckinRow)
                    .where(DailyCheckinRow.date >= cutoff)
                    .order_by(DailyCheckinRow.date.desc())
                ).all()
            )
            entries = [
                {
                    "date": r.date,
                    "sleep_h": _r(r.sleep_h),
                    "fatigue_1_10": r.fatigue,
                    "soreness_1_10": r.soreness,
                    "motivation_1_10": r.motivation,
                    "hrv_rmssd": _r(r.hrv_rmssd),
                }
                for r in rows
            ]

            def _avg(field: str) -> float | None:
                values = [e[field] for e in entries if e[field] is not None]
                return _r(sum(values) / len(values), 1) if values else None

            return {
                "days_requested": days,
                "entries_found": len(entries),
                "averages": {
                    "sleep_h": _avg("sleep_h"),
                    "fatigue_1_10": _avg("fatigue_1_10"),
                    "soreness_1_10": _avg("soreness_1_10"),
                    "motivation_1_10": _avg("motivation_1_10"),
                    "hrv_rmssd": _avg("hrv_rmssd"),
                },
                "entries": entries,
                "hint": "Nessun check-in registrato." if not entries else None,
            }

    @mcp.tool()
    def get_nutrition(days: int = 14) -> dict[str, Any]:
        """Calorie e macronutrienti per giorno, dal diario alimentare (Yazio).

        Serve a distinguere due cose che dai soli dati di corsa sembrano
        identiche: un blocco che si blocca per **troppo carico** e uno che si
        blocca perché l'atleta **mangia poco**. Guardalo prima di concludere che
        serve ridurre il volume, e prima di prescrivere una settimana pesante.

        `balance_kcal` è la differenza fra assunzione e fabbisogno del giorno
        (negativo = deficit): è quello che risponde davvero alla domanda, perché
        1900 kcal sono abbondanti o pochissime a seconda di cosa serviva.

        Sono totali giornalieri, non i singoli pasti. Attenzione a
        `days_logged`: un diario compilato a metà fa sembrare un deficit
        enorme dove c'è solo un pasto non registrato — con copertura bassa non
        trarre conclusioni sul bilancio energetico.
        """
        days = max(1, min(days, 365))
        end = date.today()
        start = end - timedelta(days=days - 1)
        with _db() as session:
            if not yazio_connected(session):
                return {
                    "connected": False,
                    "days": [],
                    "hint": (
                        "Yazio non è collegato: nessun dato di alimentazione. "
                        "Non dedurne nulla sul bilancio energetico."
                    ),
                }
            rows = recent_nutrition(session, start, end)
            entries = [
                {
                    "date": r.date,
                    "energy_kcal": _r(r.energy_kcal, 0),
                    "energy_goal_kcal": _r(r.energy_goal_kcal, 0),
                    # The number that actually answers "am I eating enough":
                    # intake alone is meaningless without what the day required.
                    "balance_kcal": (
                        _r(r.energy_kcal - r.energy_goal_kcal, 0)
                        if r.energy_kcal is not None and r.energy_goal_kcal is not None
                        else None
                    ),
                    "protein_g": _r(r.protein_g, 0),
                    "carbs_g": _r(r.carbs_g, 0),
                    "fat_g": _r(r.fat_g, 0),
                }
                for r in rows
            ]

            def _avg(field: str) -> float | None:
                values = [e[field] for e in entries if e[field] is not None]
                return _r(sum(values) / len(values), 0) if values else None

            return {
                "connected": True,
                "days_requested": days,
                "days_logged": len(entries),
                "averages": {
                    "energy_kcal": _avg("energy_kcal"),
                    "energy_goal_kcal": _avg("energy_goal_kcal"),
                    "balance_kcal": _avg("balance_kcal"),
                    "protein_g": _avg("protein_g"),
                    "carbs_g": _avg("carbs_g"),
                    "fat_g": _avg("fat_g"),
                },
                "days": entries,
                "hint": (
                    "Diario vuoto nel periodo richiesto."
                    if not entries
                    else (
                        "Copertura parziale del diario: i totali medi "
                        "sottostimano l'assunzione reale."
                        if len(entries) < days * 0.7
                        else None
                    )
                ),
            }

    @mcp.tool()
    def get_food_diary(date: str) -> dict[str, Any]:
        """Cosa ha mangiato l'atleta in un giorno, voce per voce.

        Usalo quando la domanda riguarda **cosa** c'era nel piatto — "da dove
        vengono i miei carboidrati?", "come mi sono alimentato prima della
        lunga?" — non per il bilancio del giorno, che è già in `get_nutrition`.

        Una voce per riga, con pasto e quantità. `energy_kcal` c'è solo dove
        Yazio lo dichiara (voci scritte a mano): per i prodotti a catalogo è
        assente di proposito, perché ricavarlo richiederebbe un'assunzione sulla
        porzione. Il totale del giorno affidabile è quello di `get_nutrition`.
        """
        day = _parse_date(date, "date")
        with _db() as session:
            if not yazio_connected(session):
                return {"connected": False, "items": [], "hint": "Yazio non è collegato."}
            rows = food_log(session, day)
            return {
                "connected": True,
                "date": date,
                "items_found": len(rows),
                "items": [
                    {
                        "meal": r.meal,
                        "name": r.name,
                        "amount": _r(r.amount, 0),
                        "serving": r.serving,
                        "energy_kcal": _r(r.energy_kcal, 0),
                    }
                    for r in rows
                ],
                "hint": (
                    "Nessuna voce registrata per questo giorno."
                    if not rows
                    else None
                ),
            }

    @mcp.tool()
    def preview_garmin_week(week_number: int | None = None) -> dict[str, Any]:
        """Mostra cosa finirebbe sull'orologio per una settimana del piano.

        Non scrive nulla: rende la settimana esattamente come arriverebbe su
        Garmin — step per step, con i range di passo — e restituisce un
        `confirm_code`.

        Usalo **solo quando l'atleta chiede di esportare**. Mostragli
        `sessions_to_push` per intero e chiedi conferma esplicita prima di
        chiamare `push_garmin_week`: quello che sta approvando non è un numero
        su uno schermo, è la seduta che poi corre davvero.

        Guarda anche `not_exported`: le sedute senza struttura non vengono
        inviate di proposito, e vale la pena dirglielo.
        """
        with _db() as session:
            try:
                return preview_week(session, week_number)
            except CollectionError as exc:
                return {"error": str(exc), "sessions_to_push": []}

    @mcp.tool()
    def push_garmin_week(week_number: int, confirm_code: str) -> dict[str, Any]:
        """Carica su Garmin Connect le sedute della settimana, a calendario.

        **L'unico tool di questo server che scrive**, e l'unico che tocca il
        mondo esterno. Richiede il `confirm_code` di `preview_garmin_week`.

        Chiamalo solo dopo che l'atleta ha visto l'anteprima e ha detto
        esplicitamente di procedere. Non chiamarlo per iniziativa tua, non
        incatenarlo all'anteprima nella stessa risposta, e non riusare un codice
        di una conversazione precedente: se il piano nel frattempo si è
        adattato, il codice non è più valido — è voluto, e significa che
        l'atleta deve rivedere la settimana aggiornata prima di mandarla.
        """
        with _db() as session:
            try:
                result = push_week(session, week_number, confirm_code)
            except CollectionError as exc:
                return {"pushed": 0, "error": str(exc)}
            return {
                **result.as_dict(),
                "week_number": week_number,
                "hint": (
                    "Sedute caricate e messe a calendario su Garmin Connect."
                    if result.pushed or result.updated
                    else "Nessuna seduta caricata."
                ),
            }

    @mcp.prompt()
    def running_coach() -> str:
        """Istruzioni per far ragionare Claude da allenatore di corsa."""
        return (
            "Sei il mio allenatore personale di corsa. Hai accesso ai miei dati "
            "reali di allenamento tramite i tool di questo server.\n\n"
            "Come lavori:\n"
            "1. Parti da `get_athlete_overview` per capire dove sono adesso, "
            "prima di dire qualsiasi cosa.\n"
            "2. Ragiona sui dati, non su generalità: cita i numeri che guardi "
            "(TSB, ACWR, volume, readiness) e spiega cosa significano per me.\n"
            "3. Approfondisci con gli altri tool solo quando la domanda lo "
            "richiede davvero — non fare il dump di tutto.\n"
            "4. Sii concreto e diretto come un allenatore esperto: una "
            "raccomandazione chiara, il perché in una riga, e i rischi se ci "
            "sono. Niente disclaimer generici.\n"
            "5. Se i dati non bastano per rispondere, dillo e indica cosa "
            "manca, invece di inventare.\n\n"
            "Quando prescrivi ritmi: chiama prima `get_athlete_physiology` e "
            "ancorali alla mia soglia reale (LT2), mai al tempo obiettivo. "
            "Guarda anche il Digital Twin: se la mia tolleranza alla rampa è "
            "bassa o il recupero è lento, tienine conto invece di applicare "
            "regole generiche — e se un valore è ancora in apprendimento, "
            "dimmelo.\n\n"
            "Quando serve un piano: usa `generate_plan_draft`, non scriverlo a "
            "mano. Poi commentalo — cosa ti convince, cosa cambieresti, cosa "
            "dipende da vincoli miei che il motore non conosce (giorni "
            "disponibili, viaggi, palestra). Ricordami che è una bozza e non "
            "il piano attivo dell'app.\n\n"
            "Il carico e la forma sono già calcolati dal motore: interpretali, "
            "non ricalcolarli."
        )

    return mcp
