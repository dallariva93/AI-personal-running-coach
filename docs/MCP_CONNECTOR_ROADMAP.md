# Roadmap — Server MCP Garmin come connettore Claude (remoto, costo zero)

Piano di sviluppo per esporre i dati Garmin e il "cervello coaching" di questo
progetto come **server MCP remoto**, collegato a claude.ai come **custom
connector**, così che Claude possa comportarsi da running coach sui dati reali.

**Vincoli di progetto (non negoziabili):**

| Vincolo | Implicazione |
|---|---|
| Costo zero | Solo free tier: hosting, DB, storage, cron. Nessuna API a pagamento lato server. |
| Uso personale | Un solo utente → niente multi-tenancy; auth minima ma seria (il server è esposto su Internet). |
| Storico completo (≥ 1 anno) | Serve un **backfill** paginato da Garmin, oggi assente (l'ingest prende solo le ultime N attività). |
| Claude come coach | Tool disegnati per il *ragionamento* di un coach, non un dump di endpoint; il server non chiama mai l'API Anthropic. |

**Intuizione chiave sul costo zero**: in questa architettura l'intelligenza è
Claude *client* (coperto dall'abbonamento claude.ai). Il server MCP serve solo
dati + calcoli deterministici (`app/processing/` è puro). Quindi in deploy
`AI_ENABLED=false`: **zero chiamate LLM lato server**, zero API key Anthropic
sul server.

---

## Architettura target

```
┌──────────────┐   MCP (Streamable HTTP, HTTPS)   ┌─────────────────────────────┐
│  claude.ai   │ ───────────────────────────────▶ │  FastAPI esistente          │
│  (connector) │      tools + prompts             │   └─ mount /mcp (SDK mcp)   │
└──────────────┘                                  │  services / processing      │
                                                  │  SQLAlchemy ──▶ DB (Neon)   │
      ┌──────────────────┐  cron notturno         │  GarminRawFetcher ─▶ Tigris │
      │ GitHub Actions   │ ──── POST /sync ──────▶│  garminconnect (non uff.)   │
      └──────────────────┘  + ping keep-alive     └─────────────────────────────┘
                                                        Hosting: Render free
```

Decisioni architetturali:

1. **Il server MCP è la stessa app FastAPI**, non un servizio separato: l'SDK
   Python `mcp` (FastMCP) si monta come sub-app ASGI su `/mcp` (transport
   **Streamable HTTP**, quello richiesto dai custom connector). Un processo,
   un deploy, stessa sessione DB, stessi service. Zero duplicazione.
2. **I tool MCP sono adattatori sottili** sui service esistenti — la stessa
   relazione che le rotte REST hanno già con i service.
3. **Il DB è ricostruibile**: fonte di verità = Garmin + archivio raw su Tigris
   (`app/storage/object_store.py` + `GarminRawFetcher` esistono già). Perdere il
   DB non è un disastro: si ri-esegue il backfill.

### Stack a costo zero (scelta primaria)

| Componente | Servizio | Free tier | Perché |
|---|---|---|---|
| Hosting | **Render** (free web service) | 750 h/mese (> un mese intero), HTTPS automatico, deploy da GitHub | Il minor attrito operativo. Spin-down dopo 15′ di inattività → mitigato dal ping (sotto). |
| Database | **Neon** (Postgres serverless) | 0.5 GB | Il disco di Render free è **effimero**: SQLite sparirebbe a ogni deploy/restart. SQLAlchemy è già in uso → cambio di `DATABASE_URL`. |
| Storage raw | **Tigris** | 5 GB | Già scelto in `docs/GARMIN_DATA_PLAN.md`; `ObjectStore` già implementato. ~1 anno di raw JSON+FIT ≈ 100–200 MB. |
| Cron + keep-alive | **GitHub Actions** (scheduled workflow) | Gratis (un curl dura secondi) | Sync notturno via `POST /sync` protetto + ping ogni 10′ nelle ore di veglia per evitare lo spin-down. |
| TLS/dominio | Incluso in Render (`*.onrender.com`) | Gratis | I connector richiedono HTTPS su 443. |
| LLM | Nessuno lato server | — | Claude è il client. `AI_ENABLED=false`. |

**Alternativa (più robusta, più setup): Oracle Cloud Always Free** — VM ARM
persistente, SQLite invariato, zero cold start; ma richiede gestire VM,
systemd, Caddy/TLS e un DNS gratuito (DuckDNS). Da considerare solo se i cold
start di Render (~1′ a freddo) risultassero fastidiosi nella pratica.

**Nota Postgres**: le migrazioni Alembic sono nate su SQLite; qualcuna potrebbe
non applicarsi pulita su Postgres. Essendo il DB ricostruibile, il fallback
pragmatico è `Base.metadata.create_all()` + `alembic stamp head` sul primo
avvio Postgres, poi backfill. (SQLite resta il DB di sviluppo/test.)

### Prerequisiti account (tutti gratuiti tranne il primo)

- [ ] Piano claude.ai **Pro o Max** (i custom connector richiedono un piano a pagamento — già disponibile)
- [ ] Account Render collegato a GitHub
- [ ] Account Neon (DB `running_coach`)
- [ ] Bucket Tigris + credenziali S3 (già previsto dal GARMIN_DATA_PLAN)
- [ ] Secrets: `GARMIN_EMAIL/PASSWORD`, `DATABASE_URL`, credenziali Tigris, `API_TOKEN` — **solo** negli env di Render/GitHub, mai nel repo

---

## Fase 0 — Fondamenta deploy (DB remoto + app su Render)

*Obiettivo: l'app esistente gira su Internet, senza ancora MCP.*

1. Astrarre le due assunzioni SQLite rimaste (se presenti) dietro
   `DATABASE_URL`; smoke test locale con un Postgres (docker o Neon dev branch):
   `create_all` + avvio + `/api/health`.
2. `render.yaml` (o setup da dashboard): build `pip install -r requirements.txt`,
   start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`; env vars da secrets.
3. Deploy con `AI_ENABLED=false`, modalità demo spenta, `API_TOKEN` attivo
   (l'auth middleware e la rotazione token esistono già in `auth_service`).
4. Workflow GitHub Actions `keepalive.yml`: ping `GET /api/health` ogni 10′
   dalle 6 alle 24 (di notte può dormire: il cron di sync lo sveglia).

**Effort**: S. **Verifica**: l'app risponde su `https://<nome>.onrender.com`
con token; un restart non perde il DB (Neon).

## Fase 1 — Backfill storico (≥ 1 anno) ✅ requisito esplicito

*Obiettivo: tutta la cronologia in DB + raw archiviati su Tigris.*

Oggi `GarminSource.get_recent_activities(limit)` chiama
`client.get_activities(0, limit)`: la paginazione (`start, limit`) c'è già
nella libreria, manca solo il loop.

1. Nuovo `app/services/backfill.py`:
   - pagina `get_activities(start, batch)` a ritroso fino a `--months N`
     (default 12, opzione `--all`);
   - **idempotente** per `garmin_activity_id` (skip se già in DB);
   - **checkpoint** persistente (riuso pattern `sync_state`): riprendibile dopo
     interruzione/ban temporaneo;
   - **throttling deliberato**: ~1 richiesta/secondo + backoff esponenziale su
     429/errore — la libreria non ufficiale è tollerata finché non si martella;
   - per ogni attività: sintesi via `synthesize.py` esistente + archivio raw
     (JSON + FIT) via `GarminRawFetcher` → Tigris;
   - enrichment (splits, HR zone, GPS) in seconda passata, così la prima passata
     veloce mette in DB almeno le sintesi.
2. Comando CLI `python -m app.cli backfill --months 12` (il parser argparse in
   `app/cli.py` è pronto per un nuovo sottocomando).
3. Esecuzione: dal PC locale puntando al DB Neon (consigliato: niente timeout
   di piattaforma), in 2–3 sessioni serali se serve. ~300 corse/anno × 3–4
   chiamate = ~20–40 minuti a regime di throttle per la passata completa.

**Effort**: M. **Verifica**: `SELECT count(*)` per mese copre 12 mesi;
`compute_metrics` su `ref` di 6 mesi fa produce CTL/ATL sensati; i raw esistono
su Tigris.

## Fase 2 — Server MCP montato nell'app (test locale)

*Obiettivo: tool MCP funzionanti, provati da Claude Code prima del deploy.*

1. Dipendenza `mcp` (SDK Python ufficiale). Nuovo `app/mcp_server.py`:
   `FastMCP("running-coach")`, montato in `app/main.py` su `/mcp`
   (Streamable HTTP). Ogni tool apre la propria sessione DB (stesso
   `get_session_factory` dell'app).
2. **Set di tool v1** (pochi, descrittivi — le description dicono *quando*
   usarli, non solo cosa fanno):

   | Tool | Sorgente riusata | Note |
   |---|---|---|
   | `get_athlete_overview()` | `get_profile` + `compute_metrics` + `prompts.semantic_summary` | Il punto d'ingresso del coach: profilo, forma, fase, prossima gara. |
   | `get_training_metrics(ref_date?)` | `compute_metrics` | CTL/ATL/TSB, ACWR, 80/20, readiness, predizione gara. `ref_date` per analisi storiche. |
   | `list_activities(from, to, limit?)` | query su `Activity` + `_activity_to_summary` | Sintesi compatte, non payload interi. |
   | `get_activity_detail(id)` | summary + splits + HR zone | Il dettaglio solo su richiesta (parsimonia di contesto). |
   | `get_current_plan()` / `get_plan_week(n)` | `plan_service` | Piano attivo con rationale/fueling (Fase F già in API). |
   | `get_race_prediction()` | `predict_race_time` via metriche | |
   | `compare_periods(a_from, a_to, b_from, b_to)` | aggregazioni su summaries | Il tool "da coach" per i confronti (es. "questo autunno vs lo scorso"). |
3. **Prompt MCP** `running_coach`: istruzioni di persona ("Sei il mio running
   coach: parti sempre da `get_athlete_overview`, cita i numeri, ragiona da
   allenatore élite…") esposte come prompt del server, riusabili in ogni chat.
4. Test: MCP Inspector in locale, poi `claude mcp add` da Claude Code contro
   `http://localhost:8000/mcp` e una conversazione di coaching reale come
   collaudo.

**Effort**: M (i tool sono ~15 righe l'uno: il lavoro vero è la selezione e le
description). **Verifica**: da Claude Code, "come sta andando la mia
preparazione?" produce risposte coerenti con la dashboard.

## Fase 3 — Esposizione remota + auth

*Obiettivo: il server MCP raggiungibile da claude.ai in sicurezza.*

1. Deploy della Fase 2 su Render (stesso servizio della Fase 0).
2. **Auth MVP (subito)**: i custom connector supportano anche server senza
   OAuth → proteggere `/mcp` con difesa a strati:
   - path non indovinabile (`/mcp-<token lungo random>`);
   - rate limiting (il middleware esiste già) + logging accessi;
   - tool **sola lettura** (nessun tool di scrittura/cancellazione esposto);
     l'endpoint `/sync` resta fuori da MCP, protetto da `API_TOKEN`.
3. **Auth definitiva (hardening, può slittare)**: OAuth 2.1 del protocollo MCP
   con l'auth provider integrato nell'SDK `mcp` (issuer self-hosted nella
   stessa app; un solo utente = un solo client registrato). Da fare quando
   l'MVP è stabile — a costo zero resta self-hosted.

**Effort**: S (MVP) + M (OAuth). **Verifica**: `curl` sul path segreto risponde
al handshake MCP; un path sbagliato dà 404; scanner comuni non trovano nulla.

## Fase 4 — Collegamento a claude.ai + cron di sync

*Obiettivo: il connettore vive nelle chat e i dati restano freschi.*

1. claude.ai → Settings → Connectors → **Add custom connector** → URL
   `https://<nome>.onrender.com/mcp-<token>`. Abilitarlo nelle chat.
2. Workflow GitHub Actions `sync.yml` (cron notturno): warm-up ping, poi
   `POST /api/ingest` con `API_TOKEN` → la pipeline esistente fa il resto
   (ingest → metriche → execution scoring → adaptive → re-plan settimanale
   della Fase D → refresh del twin).
3. **Progetto Claude "Running Coach"**: istruzioni di progetto con la persona
   del coach (equivalente user-side del prompt MCP), così ogni chat nel
   progetto parte già calibrata.
4. Collaudo end-to-end su casi d'uso reali: analisi post-corsa, "come
   modifico la settimana?", confronto con l'anno scorso, preparazione gara.

**Effort**: S. **Verifica**: in una chat claude.ai, Claude chiama i tool
(visibili nella UI) e risponde da coach con i numeri veri; la mattina i dati
del giorno prima ci sono senza intervento manuale.

## Fase 5 — Rifiniture da coach (opzionale, incrementale)

- Tool `get_readiness_today()` (check-in + HRV + decision engine già esistenti).
- Tool `log_debrief(text)` — prima *scrittura* controllata (il debrief vocale
  esiste già lato app): valutare solo dopo l'hardening OAuth.
- Risorse MCP (`resources`) per i documenti lunghi (es. il piano completo in
  markdown) invece che tool-call ripetute.
- Ottimizzazione parsimonia: budget di output per tool (~1–2 KB), liste sempre
  paginate — il contesto della chat è la risorsa scarsa.

---

## Rischi e mitigazioni

| Rischio | Prob. | Mitigazione |
|---|---|---|
| Ban/blocco account Garmin (libreria non ufficiale) | Media | Throttle 1 req/s, backfill in sessioni brevi, sync 1×/giorno, backoff aggressivo. I raw su Tigris rendono il danno non catastrofico. Exit path: Strava/FIT import (vedi `INTEGRATION_STRATEGY.md`). |
| Breaking change della libreria `garminconnect` | Media | `synthesize.py` è già tollerante agli schemi; pin di versione + test di collaudo dopo ogni upgrade. |
| Cold start Render a metà conversazione | Media | Keep-alive diurno; al primo tool-call fallito Claude ritenta. Se insopportabile → migrazione a Oracle VM (Fase 0 rifatta, resto invariato). |
| Free tier che cambia condizioni | Bassa | Tutto è portabile: FastAPI+Postgres+S3 girano ovunque; nessun lock-in. |
| Esposizione dati sanitari su Internet | — | Path segreto + token, tool read-only, niente credenziali Garmin leggibili via MCP, `erasure.py` già disponibile; OAuth in hardening. |
| Migrazioni SQLite→Postgres sporche | Media | Fallback `create_all` + `stamp head` (DB ricostruibile by design). |

## Ordine, effort complessivo e prompt di avvio

| Fase | Dipende da | Effort | Prompt per avviare la sessione di sviluppo |
|---|---|---|---|
| 0 — Deploy fondamenta | — | S | "Esegui la Fase 0 di docs/MCP_CONNECTOR_ROADMAP.md: porta l'app su Render free con DB Neon, AI_ENABLED=false e keep-alive GitHub Actions." |
| 1 — Backfill storico | 0 (solo per il DB target) | M | "Esegui la Fase 1 di docs/MCP_CONNECTOR_ROADMAP.md: comando backfill paginato, idempotente e riprendibile, con throttling e archivio raw su Tigris." |
| 2 — Server MCP locale | — (parallelo a 0/1) | M | "Esegui la Fase 2 di docs/MCP_CONNECTOR_ROADMAP.md: monta FastMCP su /mcp con i tool v1 e il prompt running_coach, testabile da Claude Code in locale." |
| 3 — Remoto + auth | 0+2 | S (+M OAuth) | "Esegui la Fase 3 di docs/MCP_CONNECTOR_ROADMAP.md: esponi /mcp su Render con path segreto, rate limit e tool read-only." |
| 4 — Connettore + cron | 1+3 | S | "Esegui la Fase 4 di docs/MCP_CONNECTOR_ROADMAP.md: workflow di sync notturno e collaudo del custom connector su claude.ai." |
| 5 — Rifiniture coach | 4 | S/M ciascuna | "Dalla Fase 5 di docs/MCP_CONNECTOR_ROADMAP.md implementa <item>." |

Percorso critico: **0 → 3 → 4** (il connettore funziona anche con pochi mesi di
dati); **1** può girare in parallelo e completare lo storico dopo. Stima
complessiva fino alla Fase 4: **3–5 sessioni di sviluppo**.

## Cosa si riusa (riepilogo)

| Esistente | Ruolo nella roadmap |
|---|---|
| `app/collection/` (sources, synthesize, garmin_raw) | Fetch + parsing Garmin del backfill e del sync — invariati |
| `app/storage/object_store.py` (Tigris) | Archivio raw del backfill — invariato |
| `app/processing/*` (metriche, periodizzazione, predizioni, twin) | Il contenuto dei tool MCP — invariato (funzioni pure) |
| `app/services/*` (ingest, plan, replan, decision, execution) | Orchestrazione dietro i tool e il cron — invariati |
| `app/schemas.py` | Schemi input/output dei tool MCP — invariati |
| `prompts.semantic_summary` | Cuore di `get_athlete_overview` |
| `auth_service` (API_TOKEN + rotazione), rate limiting, `erasure.py` | Sicurezza del deploy |
| `sync_state` | Pattern per il checkpoint del backfill |
| **Nuovo da scrivere** | `backfill.py`, `mcp_server.py` (tool + prompt), `render.yaml`, 2 workflow GitHub Actions, config Postgres |
