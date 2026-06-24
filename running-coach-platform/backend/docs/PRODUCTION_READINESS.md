# Production readiness — risultato finale

Questo documento riassume **cosa rende l'app pronta alla produzione** e come
soddisfa il vincolo di girare in modo stabile su servizi gratuiti.

## Sintesi

L'app è passata da MVP esteso a **prodotto deployabile e operabile**: resiliente
ai guasti delle integrazioni esterne, osservabile, sicura quando esposta,
con persistenza durevole anche su host gratuiti, migrazioni versionate e una
pipeline CI che blocca le regressioni.

| Dimensione | Stato | Come |
|---|---|---|
| **Affidabilità** | ✅ | Retry+backoff su Garmin e Claude; fallback automatico al coach offline; nessun single point of failure bloccante |
| **Persistenza dati** | ✅ | SQLite con WAL/busy_timeout; volume Fly.io o replica Litestream→R2 su host effimeri |
| **Migrazioni** | ✅ | Alembic; applicate all'avvio; `alembic check` in CI |
| **Osservabilità** | ✅ | Log strutturati JSON, request-id per richiesta, `/api/health` e `/api/ready` |
| **Sicurezza** | ✅ | Auth a token opzionale, header di sicurezza + HSTS, container non-root, segreti fuori dal repo |
| **Configurabilità** | ✅ | 12-factor: tutto via env/`.env`; default sicuri; demo/offline senza segreti |
| **Deploy** | ✅ | Dockerfile multi-host, entrypoint con migrazioni+backup, fly.toml, render.yaml, Procfile, compose |
| **Qualità** | ✅ | 51 test (unit+integration), coverage ~86%, lint ruff, gate CI ≥80% |
| **Supply chain** | ✅ | Dipendenze pinnate, `pip-audit` in CI, Dependabot (pip/actions/docker) |
| **Documentazione** | ✅ | README, guida utente, deployment, runbook, architettura, roadmap, security |

## Dettaglio per area

### Resilienza
- `app/utils.py::retry_call` — backoff esponenziale riutilizzabile.
- **Garmin**: login e fetch con retry; errori incapsulati in `CollectionError`
  e mappati a HTTP 502; la UI mostra un avviso e resta usabile sui dati esistenti.
- **Claude**: timeout e retry configurabili; su fallimento **degrada** al coach
  offline (`AI_FALLBACK_OFFLINE=true`) marcando il report come `(fallback)`.
- Gestione globale delle eccezioni di dominio (`CoachError`) → risposte JSON pulite.

### Persistenza e migrazioni
- PRAGMA di produzione (WAL, `synchronous=NORMAL`, `busy_timeout`, `foreign_keys`).
- `pool_pre_ping` per connessioni sane.
- Alembic con `render_as_batch` (ALTER compatibili con SQLite); migrazione
  iniziale inclusa; comando `app.cli migrate`.

### Osservabilità
- `app/logging_config.py` — formatter JSON senza dipendenze esterne.
- `RequestLogMiddleware` — metodo, path, status, durata, request-id.
- Probe separati liveness (`/api/health`) e readiness (`/api/ready`, verifica DB).

### Sicurezza
- `AuthMiddleware` — token bearer condiviso opzionale (header / `?token=` / cookie),
  confronto a tempo costante; `health`/`ready`/`static` sempre pubblici.
- `SecurityHeadersMiddleware` — `X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy`, `Permissions-Policy`, HSTS in produzione.
- CORS configurabile; GZip attivo.
- Container **non-root** (uid 10001), healthcheck, `.dockerignore` per immagini snelle.
- Segreti solo via env; `.env` e token store ignorati da git.

### Costo e gratuità
- Nessun servizio a pagamento richiesto: SQLite, file locali, Docker, GitHub
  Actions, Fly.io free / Cloudflare R2 free / Raspberry Pi.
- L'unico costo opzionale sono i token Claude (≈€1-2/mese), e anche senza,
  l'app è pienamente funzionale (coach offline).

## Limiti noti e scelte consapevoli
- **Concorrenza**: SQLite + singolo worker è la scelta giusta per uso personale.
  Per multi-utente, `DATABASE_URL` può puntare a Postgres free (Neon/Supabase)
  senza modifiche al codice.
- **Garmin non ufficiale**: rischio intrinseco di rottura lato Garmin; mitigato
  con retry, gestione errori e demo mode di fallback.
- **Auth single-token**: adeguata per una dashboard personale; non è un sistema
  multi-utente (out of scope).

## Checklist go-live
- [ ] `APP_ENV=production`, `LOG_JSON=true`
- [ ] `API_TOKEN` impostato (se pubblica)
- [ ] Persistenza configurata (volume Fly **oppure** Litestream→R2)
- [ ] Segreti Garmin/Anthropic impostati come secret della piattaforma
- [ ] Probe health/ready collegati
- [ ] Primo `migrate` eseguito (automatico all'avvio) e `/api/ready` = 200
- [ ] Backup verificato (copia file o restore Litestream)
