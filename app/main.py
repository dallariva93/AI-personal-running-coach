"""FastAPI application: REST API + minimal HTMX/Jinja/Bootstrap dashboard."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Form, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.middleware.cors import CORSMiddleware

from app import __version__
from app.api import router as api_router
from app.api.mobile import router as mobile_router
from app.config import get_settings
from app.db.database import get_session, init_db
from app.exceptions import CoachError, CollectionError
from app.logging_config import configure_logging, get_logger
from app.middleware import AuthMiddleware, RequestLogMiddleware, SecurityHeadersMiddleware
from app.processing import (
    build_periodization,
    build_snapshot,
    compute_metrics,
    weekly_buckets,
)
from app.schemas import AthletePhysiology, AthleteProfile, DailyCheckin, Goal, HRZones
from app.services import (
    get_profile,
    ingest_runs,
    latest_checkin,
    list_activities,
    list_reports,
    run_single_analysis,
    run_weekly_plan,
    save_checkin,
    save_profile,
)
from app.services.ingest import _all_summaries

logger = get_logger("app.main")
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    init_db()
    logger.info(
        "AI Running Coach v%s started (env=%s, mode=%s, ai=%s)",
        __version__, settings.app_env,
        "garmin" if settings.garmin_enabled else "demo",
        "claude" if settings.ai_enabled else "offline",
    )
    yield


app = FastAPI(title="AI Running Coach", version=__version__, lifespan=lifespan)

# Middleware (outermost first): security headers, logging, auth, gzip, CORS.
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestLogMiddleware)
app.add_middleware(AuthMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=512)

_settings = get_settings()
if _settings.cors_origin_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_settings.cors_origin_list,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(api_router)
app.include_router(mobile_router)

_static_dir = BASE_DIR / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


@app.exception_handler(CoachError)
async def _coach_error_handler(_request: Request, exc: CoachError):
    status = 502 if isinstance(exc, CollectionError) else 503
    logger.warning("Domain error (%s): %s", exc.__class__.__name__, exc)
    return JSONResponse({"detail": str(exc)}, status_code=status)


def _dashboard_context(session: Session, request: Request, flash: str | None = None) -> dict:
    summaries = _all_summaries(session)
    profile = get_profile(session)
    checkin = latest_checkin(session)
    metrics = compute_metrics(summaries, profile=profile, checkin=checkin)
    weekly = weekly_buckets(summaries, weeks=8)
    max_week = max((w.distance_km for w in weekly), default=0.0) or 1.0
    goal = profile.goal if profile else None
    plan = None
    if goal and goal.target_date:
        baseline = max(metrics.chronic_load_km, metrics.acute_load_km / 1.5, 20.0)
        plan = build_periodization(goal, baseline_km=baseline)
    return {
        "request": request,
        "settings": get_settings(),
        "activities": list_activities(session, limit=20),
        "reports": list_reports(session, limit=10),
        "metrics": metrics,
        "weekly": weekly,
        "max_week": max_week,
        "profile": profile,
        "goal": goal,
        "days_to_goal": goal.days_to_go() if goal else None,
        "plan": plan,
        "snapshot": build_snapshot(summaries),
        "checkin": checkin,
        "version": __version__,
        "flash": flash,
    }


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, session: Session = Depends(get_session)):
    return templates.TemplateResponse(
        request, "dashboard.html", _dashboard_context(session, request)
    )


@app.post("/ui/ingest", response_class=HTMLResponse)
def ui_ingest(request: Request, session: Session = Depends(get_session)):
    flash = None
    try:
        saved = ingest_runs(session)
        session.commit()
        flash = f"Sincronizzate {len(saved)} corse."
    except CollectionError as exc:
        session.rollback()
        flash = f"⚠️ {exc}"
    return templates.TemplateResponse(
        request, "partials/main.html", _dashboard_context(session, request, flash)
    )


@app.post("/ui/analyze", response_class=HTMLResponse)
def ui_analyze(
    request: Request,
    activity_id: int | None = Form(default=None),
    session: Session = Depends(get_session),
):
    flash = None
    try:
        run_single_analysis(session, activity_id=activity_id)
        session.commit()
    except ValueError as exc:
        session.rollback()
        flash = f"⚠️ {exc}"
    except CoachError as exc:
        session.rollback()
        flash = f"⚠️ {exc}"
    return templates.TemplateResponse(
        request, "partials/main.html", _dashboard_context(session, request, flash)
    )


@app.post("/ui/plan", response_class=HTMLResponse)
def ui_plan(request: Request, session: Session = Depends(get_session)):
    flash = None
    try:
        run_weekly_plan(session)
        session.commit()
    except ValueError as exc:
        session.rollback()
        flash = f"⚠️ {exc}"
    except CoachError as exc:
        session.rollback()
        flash = f"⚠️ {exc}"
    return templates.TemplateResponse(
        request, "partials/main.html", _dashboard_context(session, request, flash)
    )


def _int(v: str | None) -> int | None:
    try:
        return int(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _float(v: str | None) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


@app.post("/ui/profile", response_class=HTMLResponse)
def ui_profile(  # noqa: PLR0913 - one field per form input
    request: Request,
    age: str | None = Form(default=None),
    sex: str | None = Form(default=None),
    max_hr: str | None = Form(default=None),
    resting_hr: str | None = Form(default=None),
    weekly_runs: str | None = Form(default=None),
    experience_years: str | None = Form(default=None),
    level: str | None = Form(default="intermediate"),
    risk_tolerance: str | None = Form(default="moderate"),
    lt2_pace: str | None = Form(default=None),
    goal_type: str | None = Form(default=None),
    goal_target_date: str | None = Form(default=None),
    goal_target_time: str | None = Form(default=None),
    goal_priority: str | None = Form(default="A"),
    session: Session = Depends(get_session),
):
    physiology = AthletePhysiology(lt2_pace=lt2_pace or None) if lt2_pace else None
    goal = None
    if (goal_type and goal_type != "general") or goal_target_date:
        goal = Goal(
            goal_type=goal_type or "general",
            target_date=goal_target_date or None,
            target_time=goal_target_time or None,
            priority=goal_priority or "A",
        )
    profile = AthleteProfile(
        age=_int(age),
        sex=sex or None,
        max_hr=_int(max_hr),
        resting_hr=_int(resting_hr),
        weekly_runs=_int(weekly_runs),
        experience_years=_float(experience_years),
        level=level or "intermediate",
        risk_tolerance=risk_tolerance or "moderate",
        zones=_zones_from_max_hr(_int(max_hr)),
        physiology=physiology,
        goal=goal,
    )
    save_profile(session, profile)
    session.commit()
    flash = "Profilo aggiornato."
    return templates.TemplateResponse(
        request, "partials/main.html", _dashboard_context(session, request, flash)
    )


@app.post("/ui/checkin", response_class=HTMLResponse)
def ui_checkin(
    request: Request,
    sleep_h: str | None = Form(default=None),
    fatigue: str | None = Form(default=None),
    soreness: str | None = Form(default=None),
    motivation: str | None = Form(default=None),
    session: Session = Depends(get_session),
):
    from datetime import date as _date

    save_checkin(
        session,
        DailyCheckin(
            date=_date.today().isoformat(),
            sleep_h=_float(sleep_h),
            fatigue=_int(fatigue),
            soreness=_int(soreness),
            motivation=_int(motivation),
        ),
    )
    session.commit()
    return templates.TemplateResponse(
        request, "partials/main.html",
        _dashboard_context(session, request, "Check-in salvato."),
    )


def _zones_from_max_hr(max_hr: int | None) -> HRZones | None:
    """Derive default HR zones from max HR (% of max) when not set explicitly.

    A pragmatic 5-zone split so "run in Z2" becomes actionable immediately; the
    athlete can refine later. GAP 6.
    """
    if not max_hr:
        return None
    pct = [(0.50, 0.60), (0.60, 0.70), (0.70, 0.80), (0.80, 0.90), (0.90, 1.00)]
    z = [(round(lo * max_hr), round(hi * max_hr)) for lo, hi in pct]
    return HRZones(z1_hr=z[0], z2_hr=z[1], z3_hr=z[2], z4_hr=z[3], z5_hr=z[4])
