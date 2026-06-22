# 🏃 AI Running Coach

Coach di corsa personale basato su AI. Legge i tuoi allenamenti da **Garmin
Connect**, analizza il **carico e lo stato di forma**, e genera analisi +
proposta del prossimo allenamento con **Claude** — il tutto su infrastruttura
**100% gratuita** (SQLite, file locali, Docker, GitHub Actions).

> Funziona da subito anche **senza credenziali**: in *demo mode* usa dati di
> esempio e un coach *offline* basato su regole. Aggiungi le tue chiavi quando
> vuoi passare ai dati reali e all'AI.

---

## ✨ Funzionalità

| Area | Cosa fa |
|------|---------|
| **Raccolta dati** | Login Garmin con token cache, download corse, sintesi compatta |
| **Persistenza** | SQLite via SQLAlchemy (niente file JSON sparsi) |
| **Analisi carico** | ACWR, carico acuto/cronico, monotonia, 80/20, stato di forma, trend |
| **Coaching AI** | Analisi singola corsa + pianificazione settimanale con Claude |
| **Coach offline** | Fallback deterministico a regole, senza costi né API key |
| **REST API** | FastAPI con endpoint JSON documentati (`/docs`) |
| **Dashboard** | UI minimale HTMX + Jinja + Bootstrap (no React) |
| **CLI** | `ingest`, `analyze`, `weekly`, `metrics`, `serve` |
| **Deploy** | Dockerfile, docker-compose, script di bootstrap, CI GitHub Actions |

---

## 🚀 Avvio rapido (60 secondi)

```bash
git clone <repo> && cd AI-personal-running-coach
./scripts/bootstrap.sh          # crea venv, installa, importa dati demo
source .venv/bin/activate
python -m app.cli analyze       # analizza l'ultima corsa (coach offline)
python -m app.cli serve         # dashboard su http://127.0.0.1:8000
```

### Con Docker

```bash
cp .env.example .env            # opzionale: aggiungi le credenziali
docker compose up --build       # dashboard su http://localhost:8000
```

---

## 🔑 Configurazione

Copia `.env.example` in `.env`. **Tutto è opzionale**: senza chiavi l'app gira
in demo/offline.

| Variabile | Scopo | Senza |
|-----------|-------|-------|
| `GARMIN_EMAIL` / `GARMIN_PASSWORD` | Dati reali da Garmin | usa `data/demo_activities.json` |
| `ANTHROPIC_API_KEY` | Coaching con Claude | usa il coach offline a regole |
| `COACH_MODEL` | Modello analisi (default `claude-sonnet-4-6`) | — |
| `PLANNER_MODEL` | Modello piano settimanale (default `claude-opus-4-8`) | — |
| `DATABASE_URL` | Posizione SQLite | `sqlite:///data/running_coach.db` |
| `FETCH_LIMIT` | Quante corse scaricare | `10` |
| `ATHLETE_PROFILE` | Contesto atleta per il prompt | testo generico |

> Le credenziali restano **solo** nel tuo `.env` locale (mai committato) e i
> token Garmin in `.garmin_tokens/`. Vedi [`docs/SECURITY.md`](docs/SECURITY.md).

---

## 🖥️ Uso da riga di comando

```bash
python -m app.cli ingest                 # scarica e salva le corse recenti
python -m app.cli analyze                # analizza l'ultima corsa
python -m app.cli analyze --activity-id 3 --save   # corsa specifica + salva .md
python -m app.cli weekly --save          # analisi e piano settimanale
python -m app.cli metrics                # stampa metriche di carico/forma (JSON)
python -m app.cli serve --reload         # dashboard in sviluppo
```

I report `.md` vengono salvati in `data/reports/`.

---

## 🌐 REST API

Documentazione interattiva su `http://localhost:8000/docs`.

| Metodo | Endpoint | Descrizione |
|--------|----------|-------------|
| `GET` | `/api/health` | Stato e modalità (demo/garmin, ai/offline) |
| `POST` | `/api/ingest` | Scarica e salva le corse |
| `GET` | `/api/activities` | Elenco corse |
| `POST` | `/api/activities` | Inserimento manuale di una corsa |
| `GET` | `/api/metrics` | Metriche di carico/forma correnti |
| `GET` | `/api/metrics/weekly` | Carico aggregato per settimana |
| `POST` | `/api/analyze` | Analisi di una corsa (`?activity_id=`) |
| `POST` | `/api/plan/weekly` | Analisi e piano settimanale |
| `GET` | `/api/reports` | Report generati |

---

## 🧠 Come stima lo stato di forma

L'indicatore principale è l'**ACWR** (Acute:Chronic Workload Ratio): carico
degli ultimi 7 giorni diviso per la media settimanale degli ultimi 28.

| ACWR | Stato | Interpretazione |
|------|-------|-----------------|
| `< 0.8` | `detraining` | Carico in calo, hai margine per spingere |
| `0.8–1.3` | `balanced` | Fascia ottimale (basso rischio infortuni) |
| `1.3–1.5` | `fatigued` | Crescita rapida, attenzione |
| `> 1.5` | `fatigued` | Sovraccarico, riduci volume/intensità |

Si calcolano anche **monotonia** (uniformità del carico), **quota 80/20**
(volume facile vs intenso) e il **trend** settimanale. Dettagli in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## 🧪 Test & qualità

```bash
pytest                       # tutta la suite
pytest --cov=app             # con coverage (~87%)
ruff check app tests         # lint
```

La pipeline [CI](.github/workflows/ci.yml) esegue lint, test (Python 3.11/3.12)
e build+smoke-test dell'immagine Docker a ogni push.

---

## 🏗️ Architettura

Tre moduli indipendenti orchestrati da un service layer:

```
collection/  →  processing/  →  coaching/
 (raccolta)     (metriche)      (AI / regole)
       \            |            /
        \           ▼           /
         services/ingest.py  ─►  SQLite + REST API + Dashboard
```

Dettagli completi in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) e la
roadmap in [`docs/ROADMAP.md`](docs/ROADMAP.md).

---

## ⚠️ Note

- `python-garminconnect` è una libreria **non ufficiale**: può rompersi se
  Garmin cambia il sito. Le chiamate sono difensive e c'è sempre il demo mode.
- **2FA Garmin**: il primo login potrebbe richiedere interazione; i token
  vengono poi messi in cache.
- Il coach **non fornisce diagnosi mediche**: per dolori persistenti, riposo e
  consulto medico.

## Licenza

MIT — vedi [`LICENSE`](LICENSE).
