# Running Coach — Backend

API FastAPI che alimenta l'app Android. È lo stesso motore di AI Running Coach
(ingest Garmin → metriche di carico/forma → coaching Claude o offline), con in
più un endpoint aggregato per il mobile.

## Avvio locale
```bash
./scripts/bootstrap.sh
source .venv/bin/activate
python -m app.cli serve --host 0.0.0.0 --port 8000
```
Funziona **senza credenziali** (dati demo + coach offline). Aggiungi
`GARMIN_*` e `ANTHROPIC_API_KEY` in `.env` per dati reali e AI.

## Endpoint principali per l'app
| Metodo | Endpoint | Uso nell'app |
|--------|----------|--------------|
| `GET` | `/api/mobile/overview` | Carica home + piano in una chiamata |
| `POST` | `/api/ingest` | Pulsante "Sincronizza" |
| `POST` | `/api/analyze` | Pulsante "Analizza" |
| `POST` | `/api/plan/weekly` | Pulsante "Genera piano" |
| `GET` | `/api/health`, `/api/ready` | Probe (pubblici) |

`/api/mobile/overview` restituisce: capacità (modalità/coach), metriche di forma,
carico settimanale, ultime attività, ultima analisi e ultimo piano.

## Deploy gratuito
Configurazioni incluse: `Dockerfile`, `docker-compose.yml`, `fly.toml`,
`render.yaml`, `Procfile`. Le migrazioni partono in automatico all'avvio.

Guide complete in [`docs/`](docs/):
- [DEPLOYMENT.md](docs/DEPLOYMENT.md) — hosting gratuito (Fly.io/Render/Pi) + backup
- [OPERATIONS.md](docs/OPERATIONS.md) — runbook
- [PRODUCTION_READINESS.md](docs/PRODUCTION_READINESS.md) — checklist
- [ARCHITECTURE.md](docs/ARCHITECTURE.md) · [USER_GUIDE.md](docs/USER_GUIDE.md) · [SECURITY.md](docs/SECURITY.md)

## Sicurezza per l'uso con l'app
Quando il backend è pubblico, imposta `API_TOKEN`: l'app invierà
`Authorization: Bearer <token>`. Gli endpoint `health`/`ready` restano pubblici
per i probe della piattaforma.

## Test
```bash
pytest            # 53 test (include /api/mobile/overview)
ruff check app tests
```
