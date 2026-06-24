"""Command-line interface for the AI Running Coach.

Examples::

    python -m app.cli ingest            # pull + store recent runs
    python -m app.cli analyze           # analyse the latest run
    python -m app.cli weekly            # weekly analysis + plan
    python -m app.cli metrics           # print current form metrics
    python -m app.cli serve             # launch the web dashboard
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from app.config import get_settings
from app.db.database import init_db, session_scope
from app.logging_config import configure_logging
from app.processing import compute_metrics
from app.schemas import CoachingResult
from app.services import ingest_runs, run_single_analysis, run_weekly_plan
from app.services.ingest import _all_summaries

REPORTS_DIR = Path("data/reports")


def _save_report_md(result: CoachingResult, prefix: str) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = REPORTS_DIR / f"{prefix}-{stamp}.md"
    header = f"# Report coach ({result.scope}) — {stamp}\n\n_Modello: {result.model}_\n\n"
    path.write_text(header + result.as_markdown(), encoding="utf-8")
    return path


def cmd_ingest(args: argparse.Namespace) -> int:
    with session_scope() as session:
        saved = ingest_runs(session, limit=args.limit)
        print(f"Importate/aggiornate {len(saved)} corse.")
        for a in saved[:10]:
            print(
                f"  {a.date} · {a.activity_type:10s} · "
                f"{a.distance_km:5.1f} km · {a.avg_pace or '-'}"
            )
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    with session_scope() as session:
        report = run_single_analysis(session, activity_id=args.activity_id)
        result = CoachingResult(
            scope=report.scope, model=report.model,
            analysis=report.analysis, next_workout=report.next_workout,
        )
        print(result.as_markdown())
        if args.save:
            print(f"\n→ salvato in {_save_report_md(result, 'single')}")
    return 0


def cmd_weekly(args: argparse.Namespace) -> int:
    with session_scope() as session:
        report = run_weekly_plan(session)
        result = CoachingResult(
            scope=report.scope, model=report.model,
            analysis=report.analysis, next_workout=report.next_workout,
        )
        print(result.as_markdown())
        if args.save:
            print(f"\n→ salvato in {_save_report_md(result, 'weekly')}")
    return 0


def cmd_metrics(_: argparse.Namespace) -> int:
    with session_scope() as session:
        metrics = compute_metrics(_all_summaries(session))
        print(json.dumps(metrics.model_dump(), ensure_ascii=False, indent=2))
    return 0


def cmd_migrate(_: argparse.Namespace) -> int:
    from app.db.database import run_migrations

    run_migrations()
    print("Migrazioni applicate (head).")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run("app.main:app", host=args.host, port=args.port, reload=args.reload)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai-running-coach", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_ingest = sub.add_parser("ingest", help="Scarica e salva le corse recenti")
    p_ingest.add_argument("--limit", type=int, default=None)
    p_ingest.set_defaults(func=cmd_ingest)

    p_analyze = sub.add_parser("analyze", help="Analizza una corsa (default: l'ultima)")
    p_analyze.add_argument("--activity-id", type=int, default=None)
    p_analyze.add_argument("--save", action="store_true", help="Salva anche un report .md")
    p_analyze.set_defaults(func=cmd_analyze)

    p_weekly = sub.add_parser("weekly", help="Analisi e piano settimanale")
    p_weekly.add_argument("--save", action="store_true")
    p_weekly.set_defaults(func=cmd_weekly)

    p_metrics = sub.add_parser("metrics", help="Stampa le metriche di carico/forma")
    p_metrics.set_defaults(func=cmd_metrics)

    p_migrate = sub.add_parser("migrate", help="Applica le migrazioni del database (Alembic)")
    p_migrate.set_defaults(func=cmd_migrate)

    p_serve = sub.add_parser("serve", help="Avvia la dashboard web")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument("--reload", action="store_true")
    p_serve.set_defaults(func=cmd_serve)

    return parser


# Commands that manage the schema themselves and must not auto-create tables.
_SCHEMA_MANAGED = {"migrate", "serve"}


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command not in _SCHEMA_MANAGED:
        init_db()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
