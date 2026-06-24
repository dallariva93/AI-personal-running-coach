# Runbook operativo

Guida rapida per chi gestisce l'app in produzione.

## Endpoint di servizio
| Endpoint | Scopo | Auth |
|---|---|---|
| `GET /api/health` | Liveness + capacità (versione, modalità, AI on/off) | pubblico |
| `GET /api/ready` | Readiness: 200 se il DB risponde, 503 altrimenti | pubblico |
| `GET /api/version` | Versione applicativa | pubblico/token |

Configura il probe della piattaforma su `/api/health` (liveness) e, se
disponibile, `/api/ready` (readiness).

## Log
- Formato: testo leggibile in sviluppo, **JSON** in produzione (`LOG_JSON=true`).
- Ogni richiesta ha un `request_id` (header `X-Request-ID` e campo nei log JSON).
- Livello configurabile con `LOG_LEVEL` (default `INFO`).

Esempio (JSON):
```json
{"ts":"...","level":"INFO","logger":"app.http","msg":"GET /api/health -> 200 (3.1ms)","request_id":"0f64..."}
```

## Migrazioni database
- Vengono applicate **automaticamente all'avvio** (entrypoint Docker / `release`
  su PaaS) tramite `python -m app.cli migrate`.
- Manuale: `alembic upgrade head`. Verifica sincronia modello↔schema con
  `alembic check` (gira anche in CI).
- Nuova migrazione dopo una modifica ai modelli:
  ```bash
  alembic revision --autogenerate -m "descrizione"
  # rivedi il file generato, poi:
  alembic upgrade head
  ```

## Backup & restore
- Il DB è un singolo file SQLite (`data/running_coach.db`). Backup = copia file
  (sicura a caldo grazie a WAL).
- Con Litestream attivo, replica continua su S3/R2 e restore automatico al
  cold start. Restore manuale:
  ```bash
  litestream restore -o running_coach.db s3://<bucket>/db
  ```
Dettagli in [DEPLOYMENT.md](DEPLOYMENT.md).

## Aggiornamenti applicativi
```bash
git pull
docker compose up -d --build     # le migrazioni partono da sole
```
Su Fly: `fly deploy`. Su Render/Railway: push sul branch collegato.

## Troubleshooting

| Sintomo | Causa probabile | Azione |
|---|---|---|
| `/api/ready` → 503 | DB non raggiungibile / volume non montato | verifica `DATABASE_URL` e il mount del volume |
| 401 ovunque | `API_TOKEN` impostato | usa `Authorization: Bearer <token>` o `?token=` |
| Ingest fallisce (502) | Garmin irraggiungibile o libreria rotta | riprova (retry automatici), controlla credenziali; demo resta disponibile |
| Coaching "(fallback)" | chiamata Claude fallita | l'app è degradata al coach offline; controlla `ANTHROPIC_API_KEY`/credito |
| Dati persi dopo redeploy | host effimero senza persistenza | usa volume (Fly) o Litestream (vedi DEPLOYMENT) |
| "database is locked" | molti writer concorrenti | tieni un solo worker; WAL+busy_timeout già attivi |

## Sicurezza operativa
- Tieni `API_TOKEN` impostato se la dashboard è pubblica.
- Ruota le credenziali Garmin/Anthropic come segreti della piattaforma (mai nel
  repo).
- HTTPS gestito dalla piattaforma (Fly `force_https`, Render/Cloudflare).
- Header di sicurezza e HSTS attivi automaticamente in `APP_ENV=production`.
