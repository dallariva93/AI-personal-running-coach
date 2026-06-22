# Guida per Claude Code

Contesto rapido per chi lavora su questo repository.

## Cos'è
AI Running Coach: ingest corse Garmin → metriche di carico/forma → coaching
(Claude o regole offline). Stack: FastAPI + SQLAlchemy/SQLite + HTMX/Jinja.
Tutto gira gratis e funziona in demo/offline senza credenziali.

## Comandi
```bash
./scripts/bootstrap.sh        # setup completo (venv, deps, db, dati demo)
source .venv/bin/activate
pytest                        # test (con coverage: pytest --cov=app)
ruff check app tests          # lint
python -m app.cli serve       # dashboard locale
python -m app.cli analyze     # analisi ultima corsa
```

## Struttura (vedi docs/ARCHITECTURE.md)
- `app/collection/` raccolta + sintesi dati (Garmin / demo)
- `app/processing/` metriche pure (ACWR, 80/20, forma, trend)
- `app/coaching/` AICoach (Claude) + OfflineCoach (regole), stessa interfaccia
- `app/services/ingest.py` orchestrazione tra i layer
- `app/db/` modelli SQLAlchemy + sessione
- `app/api/` REST; `app/main.py` dashboard HTMX
- `tests/` unit + integration + fixtures

## Convenzioni
- Schemi Pydantic in `app/schemas.py` = contratto tra i moduli; non far
  dipendere i moduli l'uno dall'altro al di fuori di questi.
- I moduli `processing` sono funzioni pure: niente I/O, niente rete.
- Aggiungere una metrica: estendere `TrainingMetrics` + `metrics.py` + test.
- L'app deve restare eseguibile **senza** credenziali (demo + offline).
- Modelli Claude: `claude-sonnet-4-6` (analisi), `claude-opus-4-8` (piano).

## Test
- `db_env`/`session`/`client`/`demo_source` fixtures in `tests/conftest.py`.
- Usa `ref=date(2026,6,22)` per metriche deterministiche con le fixtures.
- Mantieni coverage ≥ 80% (la CI fallisce sotto soglia).
