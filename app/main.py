"""FastAPI application: REST API + minimal HTMX/Jinja/Bootstrap dashboard."""

from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app import __version__
from app.api import router as api_router
from app.config import get_settings
from app.db.database import get_session, init_db
from app.processing import compute_metrics, weekly_buckets
from app.services import (
    ingest_runs,
    list_activities,
    list_reports,
    run_single_analysis,
    run_weekly_plan,
)
from app.services.ingest import _all_summaries

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="AI Running Coach", version=__version__)
app.include_router(api_router)

_static_dir = BASE_DIR / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


@app.on_event("startup")
def _startup() -> None:
    init_db()


def _dashboard_context(session: Session, request: Request) -> dict:
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
    }


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, session: Session = Depends(get_session)):
    return templates.TemplateResponse(
        request, "dashboard.html", _dashboard_context(session, request)
    )


@app.post("/ui/ingest", response_class=HTMLResponse)
def ui_ingest(request: Request, session: Session = Depends(get_session)):
    ingest_runs(session)
    session.commit()
    return templates.TemplateResponse(
        request, "partials/main.html", _dashboard_context(session, request)
    )


@app.post("/ui/analyze", response_class=HTMLResponse)
def ui_analyze(
    request: Request,
    activity_id: int | None = Form(default=None),
    session: Session = Depends(get_session),
):
    try:
        run_single_analysis(session, activity_id=activity_id)
        session.commit()
    except ValueError:
        session.rollback()
    return templates.TemplateResponse(
        request, "partials/main.html", _dashboard_context(session, request)
    )


@app.post("/ui/plan", response_class=HTMLResponse)
def ui_plan(request: Request, session: Session = Depends(get_session)):
    try:
        run_weekly_plan(session)
        session.commit()
    except ValueError:
        session.rollback()
    return templates.TemplateResponse(
        request, "partials/main.html", _dashboard_context(session, request)
    )
