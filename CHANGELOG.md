# Changelog

Tutte le modifiche rilevanti a questo progetto sono documentate qui.
Il formato segue [Keep a Changelog](https://keepachangelog.com/it/1.1.0/).

## [Unreleased]

### Aggiunto
- **Archivio raw delle attività Garmin**: ogni attività (running e non-running)
  viene archiviata su object storage S3-compatible (Tigris su Fly.io) come
  payload nativi: `summary`, `details` (stream second-by-second incluse cadenza,
  potenza, oscillazione verticale, ground contact, respiration, ecc.),
  `splits`, `typed_splits`, `split_summaries`, `weather`, `hr_in_timezones`,
  `power_in_timezones`, `exercise_sets`, `gear`, GPX, TCX e FIT originale (zip).
  Nuova tabella `raw_activity_assets` per dedup idempotente per
  `(garmin_activity_id, kind)`. Attivato automaticamente quando le credenziali
  S3 sono configurate; vedi `.env.example` (`S3_*`) e
  `docs/DEPLOY_FLY_ANDROID.md` per il setup Tigris.

## [0.2.0] — 2026-06-23 — Production ready

### Aggiunto
- **Resilienza**: retry con backoff esponenziale per Garmin e Claude
  (`app/utils.retry_call`); fallback automatico dal coach AI a quello offline;
  gerarchia di eccezioni di dominio e handler globale.
- **Osservabilità**: logging strutturato (JSON in produzione), middleware di
  request logging con `X-Request-ID`, endpoint `/api/ready` (readiness) e
  `/api/version`; `/api/health` arricchito con versione e capacità.
- **Sicurezza**: middleware di autenticazione a token opzionale (`API_TOKEN`),
  header di sicurezza + HSTS, CORS configurabile, GZip; container non-root.
- **Migrazioni**: integrazione Alembic con migrazione iniziale, comando
  `app.cli migrate`, `alembic check` in CI.
- **Database**: PRAGMA di produzione (WAL, busy_timeout, foreign_keys),
  `pool_pre_ping`, probe di salute del DB.
- **Deployment**: entrypoint con migrazioni + backup opzionale, `fly.toml`,
  `render.yaml`, `Procfile`, immagine Litestream (`deploy/litestream/`),
  `.dockerignore`, healthcheck e supporto `$PORT`.
- **CI/CD**: job di sicurezza `pip-audit`, verifica migrazioni, configurazione
  Dependabot (pip, github-actions, docker).
- **Documentazione**: guida utente, guida al deployment su servizi gratuiti,
  runbook operativo, documento di production readiness.

### Modificato
- `app/main.py` migrato a `lifespan` (da `on_event` deprecato) con stack di
  middleware e gestione errori; le azioni della dashboard mostrano messaggi
  di esito/errore.
- `.env.example` esteso con le impostazioni di runtime, resilienza, sicurezza e
  backup.

## [0.1.0] — 2026-06-22 — MVP esteso

### Aggiunto
- Ingest Garmin (+ demo), sintesi compatta delle corse.
- Metriche di carico/forma (ACWR, carico acuto/cronico, monotonia, 80/20,
  stato di forma, trend) come funzioni pure.
- Coaching: `AICoach` (Claude) e `OfflineCoach` (regole), analisi singola e
  piano settimanale.
- Persistenza SQLite (SQLAlchemy), REST API (FastAPI), dashboard HTMX/Jinja/
  Bootstrap, CLI.
- Test unit + integration + fixtures, lint, Dockerfile, docker-compose,
  bootstrap/run script, CI GitHub Actions.
