# Roadmap

Stato corrente: **MVP esteso completo e funzionante** (demo + offline out of the
box, AI + Garmin con chiavi). Di seguito le evoluzioni previste, derivate dal
documento di analisi originale.

## ✅ Fatto (oltre l'MVP del documento)
- Persistenza SQLite (al posto dei file JSON).
- REST API (FastAPI) + dashboard (HTMX/Jinja/Bootstrap).
- Analisi singola corsa **e** analisi/piano settimanale.
- Stato di forma + andamento carico (ACWR, monotonia, 80/20, trend).
- Moduli separati: raccolta / elaborazione / coaching.
- Coach offline a regole come fallback senza costi.
- Unit + integration test + fixtures, lint, coverage ~87%.
- Dockerfile, docker-compose, script di bootstrap/run, `.env.example`, CI.

## 🔜 Fase 2 — chiudere il cerchio
- **Push allenamento sull'orologio**: creare workout strutturati e schedularli
  sul calendario Garmin (`upload_running_workout`, `schedule_workout`).
- **RPE input**: campo nel form della dashboard e flag CLI per lo sforzo percepito.
- **Scheduling automatico**: cron/GitHub Action che fa ingest+analyze a ogni
  nuova corsa sincronizzata.

## 🔭 Fase 3 — coach "serio"
- **Obiettivo gara + taper**: pianificazione verso una data con scarico finale.
- **Deriva cardiaca** e rapporto FC/passo nel tempo come metriche aggiuntive.
- **Notifiche** (Telegram/email) con il workout del giorno.
- **Self-tuning del prompt** in base ai risultati.

## 🧰 Tecnico
- Migrazioni schema (Alembic) quando il modello dati evolve.
- Export/import dati (CSV/FIT) per backup e portabilità.
- Autenticazione sulla dashboard se esposta fuori da localhost.
