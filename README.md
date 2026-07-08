# 🏃 AI Running Coach

Coach di corsa personale basato su AI con **app Android nativa**. Sincronizza i tuoi
allenamenti da **Garmin Connect**, **Strava** e **Health Connect**, analizza il
carico e lo stato di forma, genera piani di allenamento strutturati e fornisce
coaching conversazionale con **Claude** — il tutto su infrastruttura **100% gratuita**.

> Funziona da subito anche **senza credenziali**: in *demo mode* usa dati di esempio
> e un coach *offline* basato su regole. Aggiungi le tue chiavi quando vuoi passare
> ai dati reali e all'AI.

---

## ✨ Funzionalità

### Backend (Python/FastAPI)

| Area | Cosa fa |
|------|---------|
| **Raccolta dati** | Garmin Connect (polling), Strava (webhook OAuth 2.0), Health Connect (Android) |
| **Persistenza** | SQLite via SQLAlchemy + Alembic, archivio raw payloads su S3-compatible |
| **Analisi carico** | CTL/ATL/TSB (Fitness/Fatigue), ACWR, monotonia, 80/20, stato di forma, trend |
| **Coaching AI** | Analisi singola corsa + piano settimanale con Claude (Haiku/Sonnet/Opus) |
| **Coach offline** | Fallback deterministico a regole, senza costi né API key |
| **Decision Engine** | Decisione giornaliera strutturata (train/rest/reduce/defer/race) |
| **Piani strutturati** | Piani multi-settimana (8-20 settimane) con fasi periodizzate |
| **Workout Builder** | Builder visuale per workout con segmenti + AI suggest |
| **Chat AI** | Chat conversazionale persistente con routing modello e memoria |
| **Digital Twin** | Costanti apprese (ramp tolerance, recovery half-life, heat sensitivity) |
| **Adaptive Plan** | Adattamento automatico piano post-sync in base a execution score |
| **Wellness nativo** | Snapshot Garmin body battery, HRV, stress, training readiness |
| **Per-second streams** | Estrazione streams Garmin con downsampling adattivo + feature scalari |
| **REST API** | FastAPI con 40+ endpoint JSON documentati (`/docs`) |
| **Dashboard** | UI minimale HTMX + Jinja + Bootstrap (no React) |
| **CLI** | `ingest`, `analyze`, `weekly`, `metrics`, `migrate`, `serve` |
| **Resilienza** | Retry/backoff su Garmin/Strava/Claude, fallback automatico |
| **Osservabilità** | Log JSON strutturati, request-id, probe `/api/health` e `/api/ready` |
| **Sicurezza** | Auth token opzionale, encryption at-rest (Fernet), security headers |
| **Push** | FCM HTTP v1 per notifiche push (Android) |
| **GDPR** | Right to erasure endpoint, token Strava encrypted |
| **Backup** | Litestream → Cloudflare R2 per replica real-time SQLite |

### App Android (Jetpack Compose)

| Area | Cosa fa |
|------|---------|
| **Dashboard** | Stato di forma (TSB, ACWR), decisione del giorno, metriche settimana |
| **Attività** | Lista con color coding intensità, badge PR, filtri sport |
| **Dettaglio attività** | Mappa OSM interattiva, profilo altitudine + passo, splits Strava-style |
| **Piano attivo** | Vista calendario, countdown gara, check-off sessioni, execution score |
| **Workout Builder** | Builder visuale con segmenti espandibili, AI suggest |
| **Chat AI** | Chat persistente con routing modello, memoria contestuale |
| **Statistiche** | Stats annuali/mensili, export CSV/JSON |
| **Gamification** | Streak adherence, badge/milestones, personal records automatici |
| **Tracking live** | GPS tracking con FusedLocationProvider, offline queue |
| **Health Connect** | Import sessioni running + wellness da app compatibili |
| **Widget** | Home screen widget con TSB, forma, km settimana |
| **Notifiche** | Push FCM per decisioni, recap settimanale, debrief |
| **Dark mode** | Material 3 theme con dark mode automatica |
| **Offline-first** | Cache Room locale, upload queue crash-safe |

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
| `STRAVA_CLIENT_ID` / `STRAVA_CLIENT_SECRET` | Strava OAuth 2.0 + webhook | Strava disabilitato |
| `STRAVA_PUBLIC_BASE_URL` | Base URL per OAuth redirect (es. `https://coach.fly.dev`) | — |
| `ANTHROPIC_API_KEY` | Coaching con Claude | usa il coach offline a regole |
| `COACH_MODEL` | Modello analisi (default `claude-haiku-4-5-20251001`) | — |
| `PLANNER_MODEL` | Modello piano (default `claude-haiku-4-5-20251001`) | — |
| `CHAT_ROUTER_MODEL` | Routing chat (default `claude-haiku-4-5-20251001`) | — |
| `FCM_CREDENTIALS_PATH` | Path a Firebase service-account JSON per push | Push disabilitato |
| `DATABASE_URL` | Posizione SQLite | `sqlite:///data/running_coach.db` |
| `FETCH_LIMIT` | Quante corse scaricare | `50` |
| `ATHLETE_PROFILE` | Contesto atleta per il prompt | testo generico |
| `WEATHER_ENABLED` | Abilita weather-window optimizer (Open-Meteo) | `false` |
| `DATA_ENCRYPTION_KEY` | Chiave Fernet per encryption at-rest (generata se vuota) | Generata automaticamente |

> Le credenziali restano **solo** nel tuo `.env` locale (mai committato) e i
> token Garmin in `.garmin_tokens/`. I token Strava sono encrypted at-rest.
> Vedi [`docs/SECURITY.md`](docs/SECURITY.md).

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

### Core
| Metodo | Endpoint | Descrizione |
|--------|----------|-------------|
| `GET` | `/api/health` | Stato e modalità (demo/garmin, ai/offline) |
| `GET` | `/api/ready` | Readiness probe (database check) |
| `GET` | `/api/activities` | Elenco corse |
| `POST` | `/api/activities` | Inserimento manuale di una corsa |
| `POST` | `/api/activities/live` | Upload live run da Android |
| `PATCH` | `/api/activities/{id}` | Aggiorna RPE/notes |
| `POST` | `/api/ingest` | Scarica e salva le corse Garmin |
| `POST` | `/api/ingest/wellness` | Sync wellness Garmin |
| `POST` | `/api/ingest/daily-wellness` | Snapshot wellness nativo Garmin |
| `POST` | `/api/import/health-connect` | Import da Health Connect |

### Coaching
| Metodo | Endpoint | Descrizione |
|--------|----------|-------------|
| `GET` | `/api/coach/today` | Decisione del giorno |
| `POST` | `/api/coach/today/action` | Agisci su decisione (done/reduce/defer) |
| `GET` | `/api/coach/decisions` | Storico decisioni |
| `GET` | `/api/coach/events` | Audit log coaching |
| `GET` | `/api/notifications` | Notifiche pending |
| `POST` | `/api/notifications/ack` | Ack notifiche |
| `POST` | `/api/analyze` | Analisi di una corsa |
| `POST` | `/api/plan/weekly` | Analisi e piano settimanale |
| `GET` | `/api/reports` | Report generati |

### Training Plans
| Metodo | Endpoint | Descrizione |
|--------|----------|-------------|
| `POST` | `/api/plan/generate` | Genera piano multi-settimana |
| `GET` | `/api/plan/current` | Piano attivo |
| `GET` | `/api/plan/{id}` | Piano per ID |
| `POST` | `/api/plan/chat` | Chat pre-generazione |
| `PATCH` | `/api/plan/sessions/{id}/complete` | Segna sessione completata |
| `PATCH` | `/api/plan/sessions/{id}/move` | Sposta sessione |
| `POST` | `/api/plan/whatif` | Simula scenario |

### Workouts
| Metodo | Endpoint | Descrizione |
|--------|----------|-------------|
| `GET` | `/api/workouts` | Lista template |
| `POST` | `/api/workouts` | Crea template |
| `POST` | `/api/workouts/suggest` | AI suggest workout |

### Metrics & Stats
| Metodo | Endpoint | Descrizione |
|--------|----------|-------------|
| `GET` | `/api/metrics` | Metriche carico/forma correnti |
| `GET` | `/api/metrics/weekly` | Carico aggregato per settimana |
| `GET` | `/api/snapshot` | Snapshot atleta |
| `GET` | `/api/stats` | Statistiche aggregate (month/year/all-time) |
| `GET` | `/api/vo2max/history` | Trend VO2max |
| `GET` | `/api/activities/heatmap` | Heatmap GPS |
| `GET` | `/api/personal-records` | PR per distanza |
| `GET` | `/api/gamification` | Streak + badges |
| `GET` | `/api/export` | Export CSV/JSON |

### Profile & Check-in
| Metodo | Endpoint | Descrizione |
|--------|----------|-------------|
| `GET` | `/api/profile` | Profilo atleta |
| `PUT` | `/api/profile` | Aggiorna profilo |
| `GET` | `/api/checkin` | Check-in del giorno |
| `POST` | `/api/checkin` | Salva check-in |
| `POST` | `/api/debrief` | Debrief post-corsa (voice/text) |

### Mobile
| Metodo | Endpoint | Descrizione |
|--------|----------|-------------|
| `GET` | `/api/mobile/overview` | Aggregato per home screen Android |

### Other
| Metodo | Endpoint | Descrizione |
|--------|----------|-------------|
| `GET` | `/api/plan/periodization` | Piano periodizzazione |
| `GET` | `/api/predict` | Previsione gara |
| `GET` | `/api/activities/{id}/trail` | Metriche trail |
| `GET` | `/api/athlete-model` | Digital Twin (costanti apprese) |
| `GET` | `/api/recap/weekly` | Recap settimanale |
| `GET` | `/api/recap/race/{id}` | Recap gara |
| `GET` | `/api/onboarding` | Status onboarding |
| `GET` | `/api/shoes` | Tracking scarpe |
| `POST` | `/api/shoes` | Crea scarpa |
| `PUT` | `/api/shoes/{id}` | Aggiorna scarpa |
| `DELETE` | `/api/shoes/{id}` | Elimina scarpa |
| `PATCH` | `/api/activities/{id}/shoe` | Assegna scarpa |
| `POST` | `/api/devices` | Registra device FCM |
| `DELETE` | `/api/devices/{token}` | Rimuovi device FCM |
| `DELETE` | `/api/me/data` | GDPR right to erasure |

---

## 🧠 Come stima lo stato di forma

Il modello principale è **Fitness/Fatigue** (Banister impulse-response):

- **CTL** (Chronic Training Load) — fitness, media ponderata esponenziale a 42 giorni del carico giornaliero
- **ATL** (Acute Training Load) — fatica, media ponderata esponenziale a 7 giorni
- **TSB** (Training Stress Balance) — forma = CTL − ATL. Positivo = fresco, negativo = affaticato

Il carico giornaliero è calcolato come **Session Load = RPE × minuti** (sRPE), con calibrazione automatica per Garmin Training Load.

L'**ACWR** (Acute:Chronic Workload Ratio) è mantenuto come check secondario:
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

## 🚢 Produzione e deploy gratuito

L'app è **production-ready** e pensata per girare **stabile su servizi
gratuiti**. Opzioni consigliate:

- **Fly.io + volume** (cloud free, dati durevoli) — vedi [`fly.toml`](fly.toml)
- **Raspberry Pi / self-host** con `docker compose` (davvero gratis)
- **Render/Railway + Litestream → Cloudflare R2** per host senza disco persistente

In produzione imposta almeno:
```bash
APP_ENV=production
LOG_JSON=true
API_TOKEN=$(python -c "import secrets; print(secrets.token_urlsafe(24))")
```

Le migrazioni del database vengono applicate **automaticamente all'avvio**.
Guida passo-passo Fly.io + app Android: [`docs/DEPLOY_FLY_ANDROID.md`](docs/DEPLOY_FLY_ANDROID.md).
Guida completa: [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) · runbook operativo:
[`docs/OPERATIONS.md`](docs/OPERATIONS.md) · checklist e dettagli:
[`docs/PRODUCTION_READINESS.md`](docs/PRODUCTION_READINESS.md).

## 📚 Documentazione

- [Guida utente](docs/USER_GUIDE.md) — installazione e uso quotidiano
- [Deploy Fly.io + app Android](docs/DEPLOY_FLY_ANDROID.md) — passo-passo end-to-end
- [Deployment](docs/DEPLOYMENT.md) — hosting gratuito e backup
- [Runbook operativo](docs/OPERATIONS.md) — log, migrazioni, troubleshooting
- [Production readiness](docs/PRODUCTION_READINESS.md) — cosa rende l'app pronta
- [Architettura](docs/ARCHITECTURE.md) · [Roadmap](docs/ROADMAP.md) · [Sicurezza](docs/SECURITY.md)
- [Piano dati Garmin](docs/GARMIN_DATA_PLAN.md) · [World-class roadmap](docs/WORLD_CLASS_ROADMAP.md)
- [Analisi feature Fase 2](docs/FASE2_ANALISI.md) · [Changelog](CHANGELOG.md)

## 🏗️ Architettura

### Backend (Python/FastAPI)

Tre moduli indipendenti orchestrati da un service layer:

```
collection/  →  processing/  →  coaching/
 (raccolta)     (metriche)      (AI / regole)
       \            |            /
        \           ▼           /
         services/  ─►  SQLite + REST API + Dashboard
```

**Moduli principali:**
- `app/collection/` - Ingestion da Garmin/Strava/Health Connect, sintesi payload
- `app/processing/` - Metriche pure (CTL/ATL/TSB, decision engine, adaptive plan)
- `app/coaching/` - AI coaching (Claude) + fallback offline
- `app/services/` - Business logic orchestration (30+ services)
- `app/api/` - REST API (40+ endpoint)
- `app/db/` - SQLAlchemy models (15+ tabelle)

**Database:**
- SQLite 2.0 + Alembic migrations
- 15+ tabelle: activities, coaching_reports, training_plans, chat_sessions, coach_decisions, ecc.
- Archivio raw payloads su S3-compatible (Tigris)
- Backup real-time con Litestream → Cloudflare R2

Dettagli completi in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

### App Android (Jetpack Compose)

**Pattern architetturale:**
- MVVM con Repository pattern
- Offline-first con Room cache
- Retrofit per API calls
- Coroutines + Flow per async

**Package structure:**
```
com.runningcoach.app/
├── data/
│   ├── local/          # Room database (offline cache + upload queue)
│   ├── remote/         # Retrofit API client
│   └── repository/     # Repository pattern
├── ui/
│   ├── screens/        # 17 Compose screens
│   ├── components/     # 10 reusable components
│   ├── viewmodel/      # 7 ViewModels
│   └── theme/          # Material 3 theme
├── tracking/           # GPS tracking (FusedLocationProvider)
├── health/             # Health Connect integration
├── notify/             # FCM push notifications
└── widget/             # Home screen widget
```

**Schermate principali:**
- HomeScreen - Dashboard con stato di forma
- ActivitiesScreen - Lista attività
- ActivityDetailScreen - Dettaglio con mappa OSM
- PlanScreen - Piano multi-settimana
- WorkoutScreen - Builder visuale
- ChatScreen - Chat AI conversazionale
- StatsScreen - Statistiche aggregate
- SettingsScreen - Impostazioni

---

## 📱 App Android

L'app Android nativa è disponibile in `running-coach-platform/android/`.

### Build
```bash
cd running-coach-platform/android
./gradlew assembleDebug          # build APK debug
./gradlew assembleRelease       # build APK release
```

### Requisiti
- Android SDK 26+ (minSdk)
- Kotlin 1.9+
- Gradle 8+

### Funzionalità chiave
- **Offline-first**: Cache Room locale, upload queue crash-safe
- **Mappe**: OSM tiles gratuiti (no API key)
- **Health Connect**: Import da app compatibili (no Garmin richiesto)
- **Push**: FCM per notifiche (opzionale, polling fallback)
- **Widget**: Home screen widget con metriche chiave
- **Dark mode**: Material 3 theme automatico

Guida deployment Android: [`docs/DEPLOY_FLY_ANDROID.md`](docs/DEPLOY_FLY_ANDROID.md).

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
