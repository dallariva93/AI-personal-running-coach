# Running Coach Platform (app Android)

App Android nativa (**Kotlin + Jetpack Compose**, stile Strava/Garmin) per il
coach di corsa AI. Mostra allenamenti, stato di forma, periodizzazione e il
**piano generato dall'AI**, e consuma **lo stesso backend** del progetto
principale (un solo motore, niente duplicazioni).

- **`android/`** — l'app Android.
- **Backend** — è la radice di questo repository (`app/`, FastAPI + il
  "cervello" del coach), con l'endpoint aggregato per il mobile
  `/api/mobile/overview`. Non c'è più una copia separata del backend qui.

---

## Architettura

```
┌────────────────────┐         HTTPS/JSON          ┌─────────────────────────┐
│   App Android       │  ───────────────────────►   │  Backend FastAPI (root) │
│  (Compose, MVVM)    │   /api/mobile/overview      │  SQLite + cervello AI    │
│  Oggi · Allenamenti │   /api/profile /api/checkin │  Claude / coach offline  │
│  Piano · Impostaz.  │   /api/analyze /api/plan    │  deploy gratuito         │
└────────────────────┘                             └─────────────────────────┘
```

L'app non contiene logica di coaching: la chiede al backend, unica fonte di
verità (e funziona in demo/offline senza credenziali).

---

## Avvio rapido (end-to-end in locale)

### 1. Backend (radice del repository)
```bash
# dalla root del repository
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

Dettagli backend: [`../README.md`](../README.md) e [`../docs/`](../docs).

---

## Deploy gratuito del backend (per usare l'app ovunque)

Il backend vive nella root del repo ed è già pronto al deploy (Dockerfile,
`fly.toml`, `render.yaml`). Esempio Fly.io con volume persistente:

```bash
# dalla root del repository
fly launch --no-deploy --copy-config
fly volume create coach_data --size 1
fly secrets set ANTHROPIC_API_KEY=... API_TOKEN=<token-robusto>
fly deploy
```

Poi, nell'app → **Impostazioni**: inserisci `https://<tuo-app>.fly.dev/` e lo
stesso `API_TOKEN`. Guida completa: [`../docs/DEPLOYMENT.md`](../docs/DEPLOYMENT.md).

---

## Funzionalità dell'app

- **Oggi**: stato di forma (TSB/CTL/ATL + ACWR), distribuzione intensità
  easy/medio/intenso, rischio infortunio, recupero, VO2max, **previsione gara**,
  grafico del carico settimanale, ultime corse, azioni *Sincronizza*/*Analizza*.
- **Allenamenti**: elenco completo delle corse.
- **Piano**: **periodizzazione** verso la gara (timeline fasi) + piano
  settimanale dell'AI + analisi dell'ultima corsa.
- **Impostazioni**: URL/token del backend, **obiettivo gara + livello/tolleranza
  al rischio**, e **check-in giornaliero** (sonno/fatica/dolori/motivazione).

---

## Stack tecnico

| | |
|---|---|
| App | Kotlin, Jetpack Compose (Material 3), Navigation, MVVM, StateFlow |
| Rete | Retrofit + Gson, OkHttp (logging + auth interceptor) |
| Storage app | DataStore Preferences (URL + token) |
| Backend | FastAPI, SQLAlchemy/SQLite, Alembic, Anthropic Claude (+ coach offline) |
| Deploy | Docker, Fly.io, Render, Railway, Raspberry Pi |
