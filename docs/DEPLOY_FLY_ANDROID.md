# Deploy completo su Fly.io + collegamento dell'app Android

Guida passo-passo per mettere **online il backend** (gratis e con database
persistente) e far sì che **l'app Android** ci comunichi. Al termine avrai:

- un URL pubblico HTTPS tipo `https://<tuo-nome>.fly.dev/`,
- il database SQLite su un **volume persistente** (sopravvive a riavvii/deploy),
- l'app Android configurata che parla con quel backend.

> Architettura: l'app Android è un **client**. Tutta la logica (il "cervello",
> i dati, Claude) sta nel backend. L'app chiama solo `…/api/mobile/overview`,
> `…/api/analyze`, ecc. Quindi il backend **deve** stare online.

Tempo richiesto: ~15 minuti. Costo: rientra nel **free tier** di Fly.io.

---

## 0. Prerequisiti

- Account Fly.io: <https://fly.io/app/sign-up> (chiede una carta per
  l'anti-abuso, ma le risorse di questa guida stanno nel piano gratuito).
- **flyctl** (la CLI di Fly):
  ```bash
  # macOS / Linux
  curl -L https://fly.io/install.sh | sh
  # Windows (PowerShell)
  pwsh -Command "iwr https://fly.io/install.sh -useb | iex"
  ```
- Questo repository clonato in locale (il backend è la **radice** del repo:
  `Dockerfile`, `fly.toml` sono lì).
- (Opzionale) una **chiave Anthropic** per il coaching AI: senza, il coach gira
  in modalità **offline/regole** (gratis, sempre funzionante).

```bash
fly auth login
```

---

## 1. Crea l'app su Fly (senza deploy)

Il nome dell'app è **globale**: scegline uno unico (diventa il tuo URL
`https://<nome>.fly.dev`). Dalla **radice del repo**:

```bash
fly launch --no-deploy --copy-config --name il-tuo-running-coach
```

- `--copy-config` usa il `fly.toml` già presente nel repo (volume, healthcheck,
  porta 8000, migrazioni all'avvio: è tutto preconfigurato).
- `--no-deploy` perché prima dobbiamo creare il volume e i segreti.
- Se chiede di impostare Postgres/Redis: **rispondi no**.
- Regione: lascia quella proposta (es. `cdg`). **Annòtala**: deve combaciare con
  quella del volume al passo 2.

> Se preferisci non passare `--name`, modifica a mano la riga `app = "..."` in
> `fly.toml` con un nome unico.

---

## 2. Crea il volume persistente (il database vive qui)

```bash
fly volume create coach_data --size 1 --region cdg
```

- `coach_data` è **esattamente** il nome atteso dal `fly.toml`
  (`[[mounts]] source = "coach_data"` → montato su `/app/data`).
- `--region` deve essere la **stessa** dell'app (passo 1). 1 GB basta e avanza.
- Conferma con `y` quando avvisa che un solo volume = nessuna ridondanza (ok per
  uso personale).

---

## 3. Imposta i segreti

Genera un **token di accesso** robusto (proteggerà il backend pubblico) e
impostalo insieme alle chiavi opzionali:

```bash
# token forte (copialo: ti servirà identico nell'app)
fly secrets set API_TOKEN="$(openssl rand -hex 24)"

# (opzionale) coaching AI con Claude
fly secrets set ANTHROPIC_API_KEY="sk-ant-..."

# (opzionale) dati reali da Garmin Connect (altrimenti parte in demo)
fly secrets set GARMIN_EMAIL="tu@email.com" GARMIN_PASSWORD="la-tua-password"
```

Per rivedere il token impostato in seguito: `fly secrets list` (mostra solo i
nomi) — se non l'hai salvato, rigeneralo con il comando sopra.

> Senza `ANTHROPIC_API_KEY` → coach **offline** (gratis). Senza credenziali
> Garmin → modalità **demo** con dati di esempio. L'app funziona comunque.

---

## 3-bis. (Opzionale) Archivio raw delle attività su Tigris

L'app può archiviare per ogni attività Garmin (running e non) **tutti i
payload nativi** (summary, stream second-by-second con cadenza/potenza/
oscillazione verticale/ground contact/respiration, splits, weather,
hr_in_timezones, power_in_timezones, exercise sets, gear, GPX, TCX e FIT
originale) su object storage S3-compatible. Su Fly conviene **Tigris**,
che è S3-compatible e integrato nativamente (zero egress verso le app
Fly nella stessa regione, free tier per uso personale).

Crea il bucket e attacca i secrets all'app in un solo comando:

```bash
fly storage create
# Segui il wizard: dai un nome (es. running-coach-raw) e seleziona l'app
# corrente. Fly inietta automaticamente come secrets:
#   AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION,
#   AWS_ENDPOINT_URL_S3, BUCKET_NAME
```

Verifica i secrets:

```bash
fly secrets list | findstr /R "AWS_ BUCKET_"
```

Il backend rileva da solo le variabili Tigris (grazie agli alias in
`app/config.py`) e attiva l'archivio raw al successivo ingest. Per
disattivare temporaneamente l'archivio senza rimuovere il bucket:

```bash
fly secrets set RAW_ARCHIVE_ENABLED=false
```

> **Nota**: l'archivio è opt-in. Se non crei il bucket Tigris, l'app
> continua a funzionare come prima (solo summary running nel DB).

---

## 4. Deploy

```bash
fly deploy
```

Fly costruisce l'immagine dal `Dockerfile`, all'avvio applica le **migrazioni
del database** (`python -m app.cli migrate`) e avvia il server. Attendi il
messaggio di deploy riuscito.

---

## 5. Verifica che il backend sia vivo

Sostituisci `<nome>` con il nome scelto al passo 1:

```bash
# stato salute (nessun token richiesto su /api/health)
curl https://<nome>.fly.dev/api/health

# overview per l'app (richiede il token se l'hai impostato)
curl -H "Authorization: Bearer IL_TUO_API_TOKEN" \
     https://<nome>.fly.dev/api/mobile/overview
```

`/api/health` deve rispondere `{"status":"ok", ...}`. Comandi utili:

```bash
fly status      # macchine e volume
fly logs        # log in tempo reale
fly open        # apre la dashboard web nel browser
```

> Nota free tier: con `auto_stop_machines` la macchina si **ferma quando è
> inattiva** e si riavvia alla prima richiesta (primo accesso un po' lento, è
> normale e fa risparmiare). I dati restano sul volume.

---

## 6. Carica i primi dati

- **Modalità demo** (senza Garmin): popola dati di esempio una volta:
  ```bash
  curl -X POST -H "Authorization: Bearer IL_TUO_API_TOKEN" \
       https://<nome>.fly.dev/api/ingest
  ```
  …oppure, più semplice, premi **Sincronizza** dentro l'app (passo 8).
- **Con Garmin**: l'analisi/sincronizzazione scarica le tue corse reali.

---

## 7. Compila l'app Android

1. Apri la cartella `running-coach-platform/android/` in **Android Studio**
   (Giraffe o successivo, JDK 17).
2. Lascia scaricare le dipendenze Gradle, poi **Run** su un dispositivo/emulatore
   (Android 8.0+/API 26).
3. Per generare un APK installabile senza Android Studio:
   ```bash
   cd running-coach-platform/android
   ./gradlew assembleDebug
   # APK in: app/build/outputs/apk/debug/app-debug.apk
   ```

> L'HTTPS verso `*.fly.dev` è già consentito dall'app (CA di sistema): non serve
> alcuna configurazione di rete aggiuntiva.

---

## 8. Collega l'app al backend

Nell'app → tab **Impostazioni**:

- **URL del backend**: `https://<nome>.fly.dev/` (con lo `/` finale; l'app lo
  normalizza comunque).
- **Token di accesso**: lo **stesso** valore di `API_TOKEN` del passo 3.
- Premi **Salva connessione**.

Poi nella tab **Oggi** premi **Sincronizza** → dovresti vedere stato di forma,
carico, e (se hai impostato un obiettivo in Impostazioni) **previsione gara** e
**periodizzazione**. Imposta obiettivo/livello e fai il **check-in** dalla stessa
schermata Impostazioni.

---

## 9. Aggiornare il backend in futuro

Dopo aver aggiornato il codice:

```bash
git pull            # se lavori da più macchine
fly deploy          # rebuild + redeploy; le migrazioni girano da sole
```

Il database sul volume **non** viene toccato dal deploy.

---

## 10. Automatizzare il deploy con GitHub Actions

Per evitare di dover eseguire `fly deploy` manualmente a ogni commit, puoi automatizzare il deploy al push sul branch `main` usando GitHub Actions.

### 10a. Ottieni il token Fly.io

Nel tuo terminale locale:

```bash
fly auth token
```

Copia il token generato.

### 10b. Aggiungi il secret su GitHub

Vai su GitHub → Settings → Secrets and variables → Actions → New repository secret:
- **Name**: `FLY_API_TOKEN`
- **Secret**: il token copiato sopra

### 10c. Workflow di deploy

Il repository include già il workflow `.github/workflows/deploy-fly.yml` che esegue automaticamente `fly deploy` al push su `main`. Puoi anche lanciarlo manualmente dalla tab Actions su GitHub.

Da ora in poi, ogni push su `main` attiverà automaticamente il deploy su Fly.io.

---

## Risoluzione problemi

| Sintomo | Causa / Soluzione |
|---|---|
| `Error: app name … is already taken` | Scegli un nome unico (passo 1 o `app=` in `fly.toml`). |
| Deploy ok ma l'app dà "Backend non raggiungibile" | URL errato o senza `https://`. Verifica con `curl …/api/health`. |
| L'app dà **401 / Non autorizzato** | Il **token** nell'app non coincide con `API_TOKEN`. Reimposta entrambi uguali. |
| `volume … not found` / pending in deploy | Volume mancante o in **regione diversa** dall'app. Ricrea con `--region` corretta. |
| Dati spariti dopo un redeploy | Il DB non è sul volume: verifica in `fly.toml` `DATABASE_URL=sqlite:///data/running_coach.db` e il mount su `/app/data` (già così di default). |
| Prima richiesta lenta | Cold start del free tier (macchina ferma da inattività). Normale. |
| Voglio la macchina sempre accesa | In `fly.toml` metti `min_machines_running = 1` (può uscire dal free tier). |

---

## Riepilogo comandi (copia-incolla)

```bash
fly auth login
fly launch --no-deploy --copy-config --name il-tuo-running-coach
fly volume create coach_data --size 1 --region cdg
fly secrets set API_TOKEN="$(openssl rand -hex 24)"
fly secrets set ANTHROPIC_API_KEY="sk-ant-..."     # opzionale
fly deploy
curl https://il-tuo-running-coach.fly.dev/api/health
```

Poi: app → Impostazioni → URL `https://il-tuo-running-coach.fly.dev/` + token → Salva → Oggi → Sincronizza. ✅
