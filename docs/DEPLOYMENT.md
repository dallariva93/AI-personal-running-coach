# Guida al deployment (servizi gratuiti)

L'obiettivo è far girare l'app in modo **stabile e gratuito**. Il punto critico
è la **persistenza del database SQLite**: molti host gratuiti hanno un
filesystem effimero (i dati spariscono a ogni riavvio). Qui sotto le opzioni in
ordine di consiglio.

| Opzione | Costo | Persistenza dati | Difficoltà | Quando usarla |
|---|---|---|---|---|
| **Raspberry Pi / self-host** | €0 | ✅ disco locale | bassa | hai un Pi o un PC sempre acceso |
| **Fly.io + volume** | free tier | ✅ volume 1-3 GB | bassa | deploy cloud semplice e durevole |
| **Render/Railway + Litestream→R2** | free tier | ✅ replica su R2 | media | cloud senza disco persistente |
| Render/Railway "nudo" | free tier | ❌ effimero | bassa | solo demo/test |

> **Regola d'oro**: non usare un host con filesystem effimero **senza**
> Litestream, o perderai i dati. Per il free durevole "senza pensieri", scegli
> **Fly.io con volume** o il **Raspberry Pi**.

---

## Prerequisiti comuni

Prima del deploy, prepara i segreti (nessuno è obbligatorio, ma consigliati in
produzione):

- `ANTHROPIC_API_KEY` — per il coaching AI (altrimenti coach offline).
- `GARMIN_EMAIL` / `GARMIN_PASSWORD` — per i dati reali (altrimenti demo).
- `API_TOKEN` — **fortemente consigliato** se esponi la dashboard su internet:
  protegge l'accesso con un token. Generane uno con:
  ```bash
  python -c "import secrets; print(secrets.token_urlsafe(24))"
  ```
- `APP_ENV=production` e `LOG_JSON=true` per log strutturati.

---

## 1. Raspberry Pi / self-host (Docker)

Il modo più semplice e davvero gratuito se hai un dispositivo sempre acceso.

```bash
git clone <repo> && cd AI-personal-running-coach
cp .env.example .env        # compila i segreti
docker compose up -d --build
```

- I dati vivono in `./data` sul disco del Pi (persistenti).
- L'app si riavvia da sola (`restart: unless-stopped`).
- Aggiornamenti: `git pull && docker compose up -d --build` (le migrazioni
  vengono applicate automaticamente all'avvio).

Per l'esecuzione schedulata (analisi automatica), aggiungi un cron:
```cron
0 21 * * * cd /home/pi/AI-personal-running-coach && docker compose exec -T coach python -m app.cli ingest && docker compose exec -T coach python -m app.cli analyze --save
```

---

## 2. Fly.io + volume (cloud free, durevole) — consigliata

Fly include un piccolo volume persistente gratuito: ideale per SQLite.

```bash
# 1. Installa flyctl e fai login
curl -L https://fly.io/install.sh | sh
fly auth login

# 2. Crea l'app (modifica il nome in fly.toml se occupato)
fly launch --no-deploy --copy-config

# 3. Crea il volume persistente per il database
fly volume create coach_data --size 1   # 1 GB

# 4. Imposta i segreti
fly secrets set ANTHROPIC_API_KEY=... GARMIN_EMAIL=... GARMIN_PASSWORD=... API_TOKEN=...

# 5. Deploy
fly deploy
```

Il file [`fly.toml`](../fly.toml) monta il volume su `/app/data`, attiva HTTPS,
gli health check su `/api/health` e l'auto-stop/start delle macchine per
risparmiare risorse. Le migrazioni partono da sole a ogni deploy.

### Automatizzare il deploy con GitHub Actions

Per evitare di dover eseguire `fly deploy` manualmente a ogni commit, puoi automatizzare il deploy al push sul branch `main` usando GitHub Actions.

1. **Ottieni il token Fly.io** (nel tuo terminale locale):
   ```bash
   fly auth token
   ```

2. **Aggiungi il secret su GitHub**:
   - Vai su: Settings → Secrets and variables → Actions → New repository secret
   - Name: `FLY_API_TOKEN`
   - Secret: il token copiato sopra

3. **Workflow di deploy**:
   Il repository include già il workflow `.github/workflows/deploy-fly.yml` che esegue automaticamente `fly deploy` al push su `main`. Puoi anche lanciarlo manualmente dalla tab Actions su GitHub.

Da ora in poi, ogni push su `main` attiverà automaticamente il deploy su Fly.io.

---

## 3. Render / Railway + Litestream → Cloudflare R2

Per host **senza disco persistente** nel free tier. Litestream replica il file
SQLite su storage S3-compatibile in continuo e lo ripristina al riavvio.

### 3a. Crea il bucket (Cloudflare R2, free 10 GB)
1. Crea un bucket R2 (es. `running-coach`).
2. Crea un API token R2 (Access Key ID + Secret).
3. Annota l'endpoint: `https://<account_id>.r2.cloudflarestorage.com`.

### 3b. Costruisci l'immagine con Litestream
```bash
docker build -t ai-running-coach:latest .
docker build -f deploy/litestream/Dockerfile -t ai-running-coach:litestream .
```

### 3c. Imposta i segreti sull'host
```
APP_ENV=production
DB_PATH=/app/data/running_coach.db
DATABASE_URL=sqlite:///data/running_coach.db
LITESTREAM_REPLICA_URL=s3://running-coach/db
LITESTREAM_ENDPOINT=https://<account_id>.r2.cloudflarestorage.com
LITESTREAM_ACCESS_KEY_ID=...
LITESTREAM_SECRET_ACCESS_KEY=...
ANTHROPIC_API_KEY=...        # opzionale
API_TOKEN=...                # consigliato
```

All'avvio l'entrypoint:
1. ripristina il DB dall'ultima replica (se esiste),
2. applica le migrazioni,
3. avvia il server **sotto** `litestream replicate` (backup continuo).

> Render: usa [`render.yaml`](../render.yaml) come blueprint. Ricorda che il free
> tier Render va in sleep dopo inattività: al risveglio Litestream ripristina i
> dati.

---

## Backup e ripristino manuale

Il database è un singolo file: il backup è una copia.

```bash
# Backup (a caldo è sicuro grazie alla modalità WAL)
cp data/running_coach.db backup-$(date +%F).db

# Con Docker
docker compose exec coach sh -c "cp /app/data/running_coach.db /app/data/backup.db"

# Ripristino: ferma l'app, sostituisci il file, riavvia
```

Con Litestream puoi ripristinare l'ultima versione ovunque:
```bash
litestream restore -o running_coach.db s3://running-coach/db
```

---

## Verifica post-deploy

```bash
curl https://<tuo-host>/api/health    # stato e capacità
curl https://<tuo-host>/api/ready     # 200 se il DB è raggiungibile
```

`/api/health` e `/api/ready` sono **pubblici** (servono ai probe della
piattaforma) anche quando `API_TOKEN` è attivo; tutto il resto richiede il token.

---

## Note sulla scalabilità

SQLite è perfetto per uso personale (un utente). Se un giorno servissero più
utenti concorrenti:
- tieni **un solo processo/worker** (SQLite non ama molti writer), oppure
- migra a Postgres gratuito (es. Neon/Supabase free) cambiando solo
  `DATABASE_URL` — il codice usa SQLAlchemy e le migrazioni Alembic, quindi il
  passaggio è indolore.
