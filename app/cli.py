"""Command-line interface for the AI Running Coach.

Examples::

    python -m app.cli ingest            # pull + store recent runs
    python -m app.cli backfill --months 12   # import the whole history
    python -m app.cli analyze           # analyse the latest run
    python -m app.cli weekly            # weekly analysis + plan
    python -m app.cli metrics           # print current form metrics
    python -m app.cli serve             # launch the web dashboard
"""

from __future__ import annotations

import argparse
import json
import sys
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


def cmd_backfill(args: argparse.Namespace) -> int:
    """Walk the whole Garmin history (see app/services/backfill.py)."""
    from app.collection import get_source
    from app.collection.sources import GarminSource
    from app.services.backfill import (
        backfill_activities,
        enrich_missing,
        reset_checkpoint,
    )

    source = get_source()
    if not isinstance(source, GarminSource):
        print(
            "Backfill non disponibile in modalità demo: servono GARMIN_EMAIL e "
            "GARMIN_PASSWORD."
        )
        return 1

    with session_scope() as session:
        if args.restart:
            reset_checkpoint(session)
            print("Checkpoint azzerato: riparto dall'attività più recente.")

        if not args.enrich_only:
            result = backfill_activities(
                session,
                source,
                months=args.months,
                throttle_s=args.throttle,
                resume=not args.restart,
                progress=print,
            )
            print(
                f"\nSintesi: {result.runs_imported} corse e "
                f"{result.cross_training_imported} sedute cross importate "
                f"({result.skipped_existing} già presenti), "
                f"fino al {result.oldest_date or 'n/d'}."
            )
            if not result.completed:
                print(
                    "Backfill INTERROTTO prima del limite: rilancia lo stesso "
                    "comando per riprendere dal checkpoint."
                )
            for err in result.errors[:5]:
                print(f"  ! {err}")

        if args.enrich or args.enrich_only:
            enriched = enrich_missing(
                session,
                source,
                limit=args.enrich_limit,
                throttle_s=args.throttle,
                progress=print,
            )
            print(f"\nArricchite {enriched.enriched} corse con split e zone HR.")
    return 0


def cmd_weather(args: argparse.Namespace) -> int:
    """Fill in the weather Garmin never recorded (Open-Meteo, no API key)."""
    from app.services.weather_backfill import fill_missing_weather

    with session_scope() as session:
        result = fill_missing_weather(
            session, limit=args.limit, progress=print,
            use_fallback_location=not args.gps_only,
        )
        print(
            f"\nMeteo: {result.filled} attività completate su {result.considered} "
            f"esaminate ({result.no_location} senza posizione, "
            f"{result.no_data} senza dati meteo)."
        )
        if result.filled == args.limit:
            print("Raggiunto il limite del lotto: rilancia per continuare.")
    return 0


def cmd_nutrition(args: argparse.Namespace) -> int:
    """Connect Yazio and import the daily nutrition totals."""
    from datetime import date, timedelta

    from app.exceptions import CollectionError
    from app.services import yazio_sync

    with session_scope() as session:
        if args.disconnect:
            if yazio_sync.disconnect_account(session):
                print("Yazio scollegato. Lo storico già importato resta nel database.")
            else:
                print("Yazio non era collegato.")
            return 0

        if args.connect:
            settings = get_settings()
            username = args.username or settings.yazio_username
            # Never from the command line: argv is visible to every process on
            # the box and lands in the shell history.
            password = settings.yazio_password
            if not password and sys.stdin.isatty():
                import getpass

                username = username or input("Email Yazio: ").strip()
                password = getpass.getpass("Password Yazio: ")
            if not username or not password:
                print(
                    "Credenziali mancanti. Imposta YAZIO_USERNAME e YAZIO_PASSWORD "
                    "(come secret del deploy) oppure lancia il comando da un "
                    "terminale interattivo."
                )
                return 1
            try:
                yazio_sync.connect_account(session, username, password)
            except CollectionError as exc:
                print(f"Collegamento fallito: {exc}")
                # Il caso più probabile non è "password sbagliata": è un account
                # registrato con Google, che su Yazio una password non ce l'ha
                # proprio. Senza questa riga si legge solo un 401 e si perde
                # tempo a riprovare credenziali che non esistono.
                print(
                    "\nSe ti sei registrato su Yazio con Google, una password "
                    "non esiste e questo login non può funzionare. Prova a "
                    "impostarne una dall'app Yazio ('Password dimenticata' con "
                    "la stessa email), poi rilancia questo comando."
                )
                return 1
            print(f"Yazio collegato come {username}.")

        if not yazio_sync.is_connected(session):
            print("Yazio non è collegato: lancia prima `nutrition --connect`.")
            return 1

        end = date.today()
        start = end - timedelta(days=args.days - 1)
        result = yazio_sync.sync_nutrition(session, start=start, end=end, progress=print)
        print(
            f"\nAlimentazione: {result.saved} giorni salvati su "
            f"{result.considered} richiesti ({result.empty} senza dati)."
        )
        for err in result.errors[:5]:
            print(f"  ! {err}")
    return 0


def cmd_dedup(args: argparse.Namespace) -> int:
    """Find (and optionally merge) the same run stored twice from two sources."""
    from app.services.ingest import merge_duplicates

    with session_scope() as session:
        report = merge_duplicates(session, dry_run=not args.apply)
        if not report:
            print("Nessun duplicato trovato.")
            return 0
        verb = "Uniti" if args.apply else "Da unire"
        print(f"{verb} {len(report)} duplicati:\n")
        for r in report:
            print(
                f"  {r['date']}  {r['distance_km']:5.1f} km   "
                f"tengo #{r['kept']['id']} ({r['kept']['source']})   "
                f"elimino #{r['dropped']['id']} ({r['dropped']['source']})"
            )
        if not args.apply:
            print("\nAnteprima: nessuna modifica applicata. Rilancia con --apply.")
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

    p_backfill = sub.add_parser(
        "backfill",
        help="Importa tutto lo storico Garmin (riprendibile, idempotente)",
    )
    p_backfill.add_argument(
        "--months", type=int, default=12, help="Quanti mesi indietro (default: 12)"
    )
    p_backfill.add_argument(
        "--throttle", type=float, default=1.0,
        help="Pausa in secondi fra le chiamate a Garmin (default: 1.0)",
    )
    p_backfill.add_argument(
        "--restart", action="store_true",
        help="Ignora il checkpoint e riparti dall'attività più recente",
    )
    p_backfill.add_argument(
        "--enrich", action="store_true",
        help="Dopo le sintesi, scarica anche split e zone HR (lento)",
    )
    p_backfill.add_argument(
        "--enrich-only", action="store_true",
        help="Salta le sintesi ed esegui solo l'arricchimento",
    )
    p_backfill.add_argument(
        "--enrich-limit", type=int, default=200,
        help="Quante corse arricchire in questa esecuzione (default: 200)",
    )
    p_backfill.set_defaults(func=cmd_backfill)

    p_dedup = sub.add_parser(
        "dedup",
        help="Trova e unisce la stessa corsa salvata due volte (Garmin + Health Connect)",
    )
    p_dedup.add_argument(
        "--apply", action="store_true",
        help="Applica davvero l'unione (senza, mostra solo l'anteprima)",
    )
    p_dedup.set_defaults(func=cmd_dedup)

    p_weather = sub.add_parser(
        "weather",
        help="Recupera il meteo storico delle corse da Open-Meteo (senza API key)",
    )
    p_weather.add_argument(
        "--limit", type=int, default=200,
        help="Quante attività elaborare in questa esecuzione (default: 200)",
    )
    p_weather.add_argument(
        "--gps-only", action="store_true",
        help="Salta le corse senza GPS invece di usare la posizione di casa",
    )
    p_weather.set_defaults(func=cmd_weather)

    p_nutrition = sub.add_parser(
        "nutrition",
        help="Collega Yazio e importa calorie e macro giornaliere",
    )
    p_nutrition.add_argument(
        "--connect", action="store_true",
        help="Esegui il login Yazio e salva i token (la password non viene salvata)",
    )
    p_nutrition.add_argument(
        "--username", default=None,
        help="Email Yazio (in alternativa a YAZIO_USERNAME)",
    )
    p_nutrition.add_argument(
        "--disconnect", action="store_true",
        help="Elimina i token Yazio (lo storico importato resta)",
    )
    p_nutrition.add_argument(
        "--days", type=int, default=30,
        help="Quanti giorni indietro importare (default: 30)",
    )
    p_nutrition.set_defaults(func=cmd_nutrition)

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
