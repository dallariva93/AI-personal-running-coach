# Running Coach Platform

Piattaforma completa del coach di corsa AI:

- **`backend/`** — API FastAPI (lo stesso motore di AI Running Coach) pronta al
  **deploy gratuito** (Fly.io, Render, Railway, Docker, Raspberry Pi), con un
  endpoint aggregato pensato per il mobile (`/api/mobile/overview`).
- **`android/`** — app Android nativa (**Kotlin + Jetpack Compose**, stile
  Strava/Garmin) per visualizzare allenamenti, stato di forma e soprattutto il
  **piano di allenamento proposto dall'AI**.

> Questo è un progetto **separato** dal repository del backend originale, pensato
> per essere estratto in un proprio repo GitHub (vedi "Estrazione" in fondo).

---

## Architettura

```
┌────────────────────┐         HTTPS/JSON          ┌─────────────────────┐
│   App Android       │  ───────────────────────►   │   Backend FastAPI    │
│  (Compose, MVVM)    │   /api/mobile/overview      │  (SQLite, Claude/AI) │
│  Oggi · Allenamenti │   /api/analyze              │  deploy gratuito     │
│  Piano · Impostaz.  │   /api/plan/weekly          │  Fly.io / Render ...  │
└────────────────────┘                             └─────────────────────┘
```

L'app non contiene logica di coaching: la chiede al backend, che resta l'unica
fonte di verità (e funziona in demo/offline senza credenziali).

---

## Avvio rapido (end-to-end in locale)

### 1. Backend
```bash
cd backend
./scripts/bootstrap.sh
source .venv/bin/activate
python -m app.cli serve --host 0.0.0.0 --port 8000
```
Verifica: <http://localhost:8000/api/health> e <http://localhost:8000/api/mobile/overview>.

### 2. App Android
1. Apri la cartella `android/` in **Android Studio** (Giraffe o successivo).
2. Avvia un emulatore (API 26+) e premi **Run**.
3. L'app usa di default `http://10.0.2.2:8000/` (= `localhost` del tuo PC visto
   dall'emulatore). Cambialo in **Impostazioni** se necessario.

Dettagli: [`android/README.md`](android/README.md) ·
[`backend/README.md`](backend/README.md).

---

## Deploy gratuito del backend (per usare l'app ovunque)

Per usare l'app fuori da casa, il backend deve stare online. Opzione consigliata
**Fly.io + volume** (gratis e con dati persistenti):

```bash
cd backend
fly launch --no-deploy --copy-config
fly volume create coach_data --size 1
fly secrets set ANTHROPIC_API_KEY=... API_TOKEN=<token-robusto>
fly deploy
```

Poi, nell'app → **Impostazioni**: inserisci `https://<tuo-app>.fly.dev/` e il
`API_TOKEN`. Guida completa: [`backend/docs/DEPLOYMENT.md`](backend/docs/DEPLOYMENT.md).

> Se imposti `API_TOKEN` sul backend (consigliato quando è pubblico), inserisci
> lo stesso token nelle impostazioni dell'app.

---

## Funzionalità dell'app

- **Oggi**: stato di forma (semaforo + ACWR, carico 7/28 gg, quota 80/20),
  grafico del carico settimanale, ultime corse, azioni *Sincronizza* / *Analizza*.
- **Allenamenti**: elenco completo delle corse.
- **Piano**: il **piano settimanale generato dall'AI** + l'analisi dell'ultima
  corsa, con pulsante per rigenerarlo.
- **Impostazioni**: URL del backend e token di accesso (salvati con DataStore).

---

## Stack tecnico

| | |
|---|---|
| App | Kotlin, Jetpack Compose (Material 3), Navigation, MVVM, StateFlow |
| Rete | Retrofit + Gson, OkHttp (logging + auth interceptor) |
| Storage app | DataStore Preferences (URL + token) |
| Backend | FastAPI, SQLAlchemy/SQLite, Alembic, Anthropic Claude (+ coach offline) |
| Deploy | Docker, Fly.io, Render, Railway, Raspberry Pi |

---

## Estrazione in un repository dedicato

Questa cartella è auto-contenuta. Per spostarla in un nuovo repo GitHub:

```bash
# dalla root del monorepo
git subtree split --prefix=running-coach-platform -b running-coach-platform
# poi, in una cartella nuova:
git clone <repo-origine> tmp && cd tmp
git push <nuovo-repo-url> running-coach-platform:main
```
oppure, più semplice, copia la cartella in un repo vuoto e fai il primo commit.
