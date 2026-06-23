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
from app.config import get_settings
from app.db.database import get_session, init_db
from app.exceptions import CoachError, CollectionError
from app.logging_config import configure_logging, get_logger
from app.middleware import AuthMiddleware, RequestLogMiddleware, SecurityHeadersMiddleware
from app.processing import compute_metrics, weekly_buckets
from app.services import (
    ingest_runs,
    list_activities,
    list_reports,
    run_single_analysis,
    run_weekly_plan,
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
    metrics = compute_metrics(summaries)
    weekly = weekly_buckets(summaries, weeks=8)
    max_week = max((w.distance_km for w in weekly), default=0.0) or 1.0
    return {
        "request": request,
        "settings": get_settings(),
        "activities": list_activities(session, limit=20),
        "reports": list_reports(session, limit=10),
        "metrics": metrics,
        "weekly": weekly,
        "max_week": max_week,
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
