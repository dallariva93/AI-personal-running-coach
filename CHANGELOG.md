# Changelog

Tutte le modifiche rilevanti a questo progetto sono documentate qui.
Il formato segue [Keep a Changelog](https://keepachangelog.com/it/1.1.0/).

## [Unreleased]

### Aggiunto
- **Diario alimentare Yazio**: calorie e macronutrienti giornalieri importati
  nel connettore, così un calo di forma da deficit energetico smette di essere
  indistinguibile da uno da troppo carico. Nuovo client
  `app/collection/yazio.py` (OAuth2 password grant + refresh, parsing difensivo:
  uno schema cambiato produce "nessun dato", mai un giorno da 0 kcal), servizio
  `app/services/yazio_sync.py`, tabelle `yazio_accounts` (token cifrati con
  Fernet, come Strava) e `nutrition_days` (un aggregato per giorno), tool MCP
  `get_nutrition` e comando `python -m app.cli nutrition`. La password è usata
  una sola volta al collegamento e non viene mai salvata; i nuovi giorni
  arrivano con il normale sync delle corse, in modalità best-effort. Solo
  totali giornalieri, non i singoli pasti: è ciò che serve a un allenatore e
  costa due ordini di grandezza in meno di contesto. Vedi
  `docs/MCP_ATTIVAZIONE_PASSO_PASSO.md`.
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
- **Moduli archivio**: `app/storage.py` (`ObjectStore` S3-compatible,
  `get_object_store()`) e `app/collection/garmin_raw.py` (`GarminRawFetcher`),
  con `boto3` importato in modo lazy così l'app continua a girare in
  demo/offline senza la dipendenza. Migrazione Alembic per `raw_activity_assets`.
- **Dettaglio attività sull'app**: i campi ricchi già raccolti
  (VO₂max, training load, GAP, frazioni più veloci 1k/5k, zone FC, minuti
  intensi/moderati, temperatura, umidità, D−, Body Battery, stamina, training
  effect aerobico/anaerobico) sono ora esposti da `ActivityOut` →
  `/api/mobile/overview` e mostrati in una nuova schermata di dettaglio Android
  (riga attività tappabile). Dati demo arricchiti perché la vista funzioni
  anche senza credenziali Garmin.
- **Arricchimento profondo delle attività**: la sincronizzazione Garmin ora
  estrae le metriche dagli endpoint di dettaglio (non solo dalla lista, che è
  scarna). `extract_details_enrichment` legge l'intero `summaryDTO`
  (VO₂max, training load, zone FC, training effect, GAP, frazioni veloci,
  temperatura, intensità, body battery, stamina); fallback dedicati per zone FC
  (`get_activity_hr_in_timezones`), parziali al km (`get_activity_splits`) e
  umidità (`get_activity_weather`), tutti best-effort. Aggiunto il Training
  Effect numerico aerobico/anaerobico (0–5) con nuova migrazione Alembic.
  `upsert_activity` non sovrascrive più dati buoni con `null` su fetch falliti.
- **Schermata dettaglio production-ready**: sezioni Performance, Frequenza
  cardiaca (zone), Effetto allenante (barre TE 0–5 + descrizione), Parziali al
  km (grafico a barre + lista), Ambiente & dislivello, Recupero & intensità.

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
