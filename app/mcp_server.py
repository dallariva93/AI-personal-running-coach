"""MCP server: exposes the coaching data + engine as tools for Claude.

This is the server half of the Claude *custom connector* (see
``docs/MCP_CONNECTOR_ROADMAP.md``). It is deliberately a **thin adapter** over
the existing service layer — the same relationship the REST routes already have
with ``app/services`` — so there is exactly one implementation of every metric.

Two design rules the tools follow:

* **Read-only.** Nothing here mutates state. The connector is reachable from
  the public internet behind an unguessable path, so the blast radius of a
  leaked URL stays "someone read my running data", never "someone changed my
  plan". Writes stay on the authenticated REST API.
* **Parsimonious.** The chat context window is the scarce resource, not CPU.
  Tools return compact, pre-digested dicts (rounded floats, ISO dates, no ORM
  dumps); the expensive per-activity detail is a separate opt-in call.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.coaching.prompts import semantic_summary
from app.config import get_settings
from app.db.database import get_session_factory
from app.db.models import Activity
from app.logging_config import get_logger
from app.processing import compute_metrics
from app.schemas import RunSummary, TrainingMetrics
from app.services import get_profile, hrv_history, latest_checkin
from app.services.ingest import _activity_to_summary, _all_summaries
from app.services.plan_service import get_current_plan

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
"""


@contextmanager
def _db() -> Iterator[Session]:
    """A short-lived read-only session, one per tool call.

    Tools never write, so this deliberately does not commit: it opens, reads
    and closes, keeping no transaction open between calls.
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
        Per i dettagli di una singola seduta usa poi get_activity_detail.
        """
        start = _parse_date(from_date, "from_date")
        end = _parse_date(to_date, "to_date")
        limit = max(1, min(limit, 200))
        with _db() as session:
            runs = _in_range(_all_summaries(session), start, end)
            window = runs[:limit]
            return {
                "range": {
                    "from": start.isoformat() if start else None,
                    "to": end.isoformat() if end else None,
                },
                "returned": len(window),
                "matching_total": len(runs),
                "totals": _aggregate(window),
                "activities": [_summary_payload(r) for r in window],
            }

    @mcp.tool()
    def get_activity_detail(activity_id: int) -> dict[str, Any]:
        """Dettaglio completo di una corsa: split al km, zone HR, meteo, note.

        Chiamalo solo quando l'analisi richiede davvero il dentro-della-seduta
        (es. valutare la tenuta del ritmo o il drift cardiaco), non per
        scorrere lo storico: gli id vengono da list_activities.
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
                "splits_km": s.splits_km,
                "hr_zones_min": s.hr_zones,
                "temperature_c": _r(s.temperature_c),
                "humidity_pct": _r(s.humidity_pct, 0),
                "garmin_training_load": _r(s.garmin_training_load, 0),
                "notes": s.notes,
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
            "Il carico e la forma sono già calcolati dal motore: interpretali, "
            "non ricalcolarli."
        )

    return mcp
