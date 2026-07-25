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
                                                  │  SQLAlchemy ──▶ SQLite       │
      ┌──────────────────┐   cron notturno        │    (volume Fly persistente) │
      │ GitHub Actions   │ ──── POST /sync ──────▶│  GarminRawFetcher ─▶ Tigris │
      └──────────────────┘                        │  garminconnect (non uff.)   │
                                                  └─────────────────────────────┘
                                                    Hosting: Fly.io (GIÀ attivo)
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

### Stack a costo zero — **si riusa quello che c'è già**

> ⚠️ **Correzione rispetto alla prima stesura.** L'app è **già deployata su
> Fly.io** (`fly.toml` + `.github/workflows/deploy-fly.yml`) con un **volume
> persistente** e una **macchina always-on**. Non serve migrare a Render/Neon:
> quei servizi risolverebbero problemi (disco effimero, cold start) che questo
> setup **non ha**. Si aggiunge il server MCP alla stessa app; nient'altro si
> sposta.

| Componente | Servizio | Stato | Perché va bene così |
|---|---|---|---|
| Hosting | **Fly.io** (`app = "ai-running-coach"`, region cdg) | ✅ già attivo | HTTPS forzato su 443 (`force_https`), deploy via `deploy-fly.yml` da GitHub. Il mobile app lo usa già. |
| Database | **SQLite su volume Fly** (`coach_data` → `/app/data`) | ✅ già persistente | Il volume sopravvive a restart/redeploy; le migrazioni Alembic girano già lì. **Nessun Postgres, nessuna migrazione dati.** |
| Sempre caldo | `min_machines_running = 1`, `auto_stop_machines = "off"` | ✅ già configurato | Niente cold start a metà conversazione (già risolto per il 503 del mobile). **Keep-alive workflow non necessario.** |
| Storage raw | **Tigris** | da configurare | Già scelto in `docs/GARMIN_DATA_PLAN.md`; `ObjectStore` implementato. Tiene i raw fuori dal volume da 1 GB. *Alternativa*: raw direttamente sul volume Fly (~100–200 MB/anno) e alzare il volume a 3 GB (free), se si vuole zero dipendenze esterne. |
| Cron sync | **GitHub Actions** (scheduled) | da aggiungere | `POST /api/ingest` notturno protetto da `API_TOKEN`. Nessun ping keep-alive (la macchina è già always-on). |
| LLM | Nessuno lato server | ✅ | Claude è il client. `AI_ENABLED=false` in produzione. |

Il volume Fly da 1 GB basta ampiamente per il DB (decine di MB anche con un anno
di storico). Se un giorno servisse più capacità di calcolo, la memoria è già a
512 MB (vedi commento in `fly.toml`); resta sotto il free usage buffer.

### Prerequisiti account

- [ ] Piano claude.ai **Pro o Max** (i custom connector richiedono un piano a pagamento — già disponibile)
- [ ] Fly.io + `FLY_API_TOKEN` in GitHub secrets — **già configurati** (il deploy gira)
- [ ] Bucket Tigris + credenziali S3 (solo se si sceglie Tigris per i raw; altrimenti si usa il volume)
- [ ] Secrets su Fly (`fly secrets set …`): `GARMIN_EMAIL/PASSWORD`, `API_TOKEN`, credenziali Tigris — **solo** negli env di Fly/GitHub, mai nel repo

---

## Fase 0 — Verifica del deploy esistente (quasi nulla da fare)

*Obiettivo: confermare che l'app su Fly.io è pronta a ospitare anche l'MCP.*

L'app è **già** su Internet con HTTPS, volume persistente e macchina always-on.
Qui non si costruisce infrastruttura, si verifica soltanto:

1. Confermare che il deploy Fly è vivo: `https://ai-running-coach.fly.dev/api/health`
   risponde; un `fly deploy` non perde il DB (volume `coach_data`).
2. Assicurarsi che i secrets di produzione siano impostati su Fly
   (`fly secrets list`): `GARMIN_EMAIL/PASSWORD`, `API_TOKEN`, e — se si userà
   Tigris — le credenziali S3. In produzione `AI_ENABLED=false` (Claude è il
   client) e modalità demo spenta.
3. Nessun `render.yaml`, nessun Neon, nessun workflow keep-alive: già coperti da
   `fly.toml` (`min_machines_running=1`) e da `deploy-fly.yml`.

**Effort**: XS (verifica/config, non sviluppo). **Verifica**: `/api/health` in
HTTPS con token; `fly secrets list` completo.

## Fase 1 — Backfill storico (≥ 1 anno) ✅ FATTA

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
3. Esecuzione: **dentro la macchina Fly**, che scrive direttamente sul volume:
   `fly ssh console -C "python -m app.cli backfill --months 12"` (riprendibile
   grazie al checkpoint, quindi eventuali disconnessioni ssh non sono un
   problema). ~300 corse/anno × 3–4 chiamate = ~20–40 minuti a regime di throttle.
   In alternativa in locale su una copia del DB e poi upload del file sul volume.

Implementato in `app/services/backfill.py` + CLI `backfill`, 17 test.
Due passate separate perché il costo differisce di ~100x (le sintesi prendono
~100 attività per chiamata, l'arricchimento ne costa diverse *per attività*).
Un cutoff diverso fa ripartire da capo invece di riprendere: riprendere in una
finestra che il run precedente non stava percorrendo salterebbe dati.

**Verifica**: `SELECT count(*)` per mese copre 12 mesi;
`compute_metrics` su `ref` di 6 mesi fa produce CTL/ATL sensati; i raw esistono
su Tigris.

## Fase 2 — Server MCP montato nell'app (test locale) ✅ FATTA

*Obiettivo: tool MCP funzionanti, provati da Claude Code prima del deploy.*

Implementata in `app/mcp_server.py` (+ mount in `app/main.py`), 23 test in
`tests/integration/test_mcp_server.py`.

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
4. Test locale: `MCP_DEV_UNPROTECTED=true` serve `/mcp` senza segreto su
   localhost, per MCP Inspector e `claude mcp add`.

**Verifica**: 23 test coprono handshake, superficie dei tool e payload
(overview, metriche con `ref_date` storica, filtri per data, dettaglio corsa,
confronto periodi, piano) più i casi degeneri — DB vuoto, id inesistente, data
malformata, finestra senza corse (niente divisione per zero).

**Scelte di implementazione non ovvie:**

- **`stateless_http=True`** — ogni chiamata è autosufficiente. Con le sessioni
  MCP un redeploy invaliderebbe l'`Mcp-Session-Id` del connettore, che
  resterebbe appeso a una sessione morta.
- **`streamable_http_path="/"`** — così l'URL montato è esattamente il path
  segreto, senza suffisso `/mcp` in coda.
- **Il session manager gira nel lifespan di FastAPI** — le sub-app montate non
  ricevono il proprio lifespan, e senza questo ogni tool fallisce con
  *"task group is not initialized"*.
- **Import di `mcp` dentro la funzione** — se la dipendenza manca o il build
  fallisce, il connettore si disattiva e la dashboard resta in piedi.

## Fase 3 — Esposizione remota + auth ✅ FATTA (MVP; OAuth resta hardening)

*Obiettivo: il server MCP raggiungibile da claude.ai in sicurezza.*

1. Deploy della Fase 2 su Fly (`fly deploy`, stesso servizio già esistente).
2. **Auth MVP (fatta)**: difesa a strati attorno al path segreto —
   - `MCP_PATH_TOKEN` → il server monta su `/mcp-<token>`; **senza token non
     esiste alcun endpoint** (fail closed, verificato da test);
   - il path segreto **è** la credenziale: l'auth middleware lo lascia passare
     perché un custom connector non-OAuth non può inviare header
     `Authorization`. Un test verifica che questo **non** apra l'API REST, che
     continua a rispondere 401 senza token;
   - rate limiting con bucket dedicato (`RATE_LIMIT_MCP_PER_MINUTE`, default
     240/min): è l'unica barriera davanti al layer dei tool, dato che l'auth è
     bypassata;
   - tool **sola lettura**: un test asserisce che nessun tool esposto crei,
     modifichi o cancelli. Ingest e scritture restano sull'API con `API_TOKEN`;
   - `MCP_DEV_UNPROTECTED` è ignorato quando `APP_ENV=production`, così non può
     mai diventare un buco non autenticato.
3. **Auth definitiva (hardening, può slittare)**: OAuth 2.1 del protocollo MCP
   con l'auth provider integrato nell'SDK `mcp` (issuer self-hosted nella
   stessa app; un solo utente = un solo client registrato). Da fare quando
   l'MVP è stabile — a costo zero resta self-hosted.

> ⚠️ **Trappola trovata in fase di sviluppo.** L'SDK MCP applica una
> protezione anti-DNS-rebinding che di default **accetta solo `localhost`**:
> deployato su Fly, ogni richiesta del connettore riceverebbe `421 Misdirected
> Request` senza spiegazioni. Per questo esiste `MCP_ALLOWED_HOSTS`: valorizzato
> con l'hostname pubblico la protezione è attiva (verificato: un `Host` diverso
> → 421); lasciato vuoto il controllo viene disattivato e l'avvio logga un
> warning, perché un connettore che non parte è un guasto peggiore del rischio
> evitato (l'endpoint è dietro un path segreto e non usa credenziali ambientali
> tipo cookie).

**Verifica** (simulazione con la configurazione di produzione esatta —
`APP_ENV=production`, path segreto, `MCP_ALLOWED_HOSTS`, `API_TOKEN`):
handshake 200, tool call 200 con dati reali, path sbagliato respinto,
`/api/metrics` senza token 401, `Host` non consentito 421.

## Fase 4 — Collegamento a claude.ai + cron di sync

*Obiettivo: il connettore vive nelle chat e i dati restano freschi.*

### Runbook: attivare il connettore (da fare al PC)

```sh
# 1. Genera il token del path — è una password, trattalo come tale.
python -c "import secrets; print(secrets.token_urlsafe(32))"

# 2. Configura i secret su Fly (l'app si riavvia da sola).
fly secrets set MCP_PATH_TOKEN="<token del passo 1>" \
                MCP_ALLOWED_HOSTS="ai-running-coach.fly.dev"

# 3. Deploy del codice che monta l'MCP.
fly deploy

# 4. Verifica: deve rispondere 200 con un frame JSON-RPC.
curl -sS -X POST "https://ai-running-coach.fly.dev/mcp-<token>/" \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{
       "protocolVersion":"2025-06-18","capabilities":{},
       "clientInfo":{"name":"curl","version":"1"}}}'
```

Poi: claude.ai → Settings → Connectors → **Add custom connector** → URL
`https://ai-running-coach.fly.dev/mcp-<token>/` (con lo slash finale).
Abilitalo nelle chat.

**Diagnosi rapida se qualcosa non va:**

| Sintomo | Causa | Rimedio |
|---|---|---|
| `404` | `MCP_PATH_TOKEN` non impostato, oppure URL/token diverso | `fly secrets list`, ricontrolla il path |
| `421 Misdirected Request` | `MCP_ALLOWED_HOSTS` non contiene l'hostname usato | correggilo, o lascialo vuoto per disattivare il controllo |
| `401` | stai colpendo un path che non è quello dell'MCP | l'URL deve iniziare esattamente con `/mcp-<token>` |
| `429` | rate limit del bucket MCP | alza `RATE_LIMIT_MCP_PER_MINUTE` |
| tool assenti nella UI | connettore non abilitato in quella chat | attivalo dal selettore dei connettori |

Per **ruotare** il token basta impostarne uno nuovo: il vecchio URL smette
immediatamente di esistere (poi aggiorna il connettore su claude.ai).
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

## Fase 2.5 — Fisiologia e piano deterministico ✅ FATTA

*Obiettivo: chiudere il divario fra "buon piano generico" e "piano di questo
atleta". I dati e il motore c'erano già: mancava il passaggio attraverso i tool.*

| Tool | Perché serve |
|---|---|
| `generate_plan_draft` | Chiama `build_plan_spec` invece di far scrivere il piano a mano libera. È la scelta architetturale delle Fasi A–F (il motore fa i conti, l'LLM verbalizza) portata dentro la chat. Marcato come bozza non salvata. |
| `get_athlete_physiology` | LT1/LT2, zone HR, giorni disponibili, gare B/C e Digital Twin con confidenze. Senza soglia lo dichiara invece di restituire un null plausibile. |
| `get_training_history_summary` | Aggregati mensili: una stagione in contesto senza scaricare centinaia di attività. |
| `get_personal_records`, `get_cross_training`, `get_readiness_history` | PR, carico non-corsa, andamento del recupero. |

**Verifica**: 18 test, fra cui che i volumi settimanali tornino, che la
progressione abbia scarichi prima del picco e taper verso la gara, e che la
bozza non tocchi il piano attivo.

**Resta fuori** (limiti veri, non di esposizione): storia infortuni, stress di
vita e lavoro, percorsi e altimetria disponibili, palestra e biomeccanica,
alimentazione. E il fatto che un allenatore vero ti guarda correre.

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
| Cold start a metà conversazione | Bassa | Già mitigato: `min_machines_running=1` tiene la macchina calda (fatto per il 503 del mobile). |
| Volume Fly da 1 GB insufficiente | Bassa | Il DB è decine di MB; i raw vanno su Tigris (o si alza il volume a 3 GB, free). |
| Free tier / usage buffer che cambia | Bassa | Tutto portabile (FastAPI+SQLite+S3 girano ovunque); il costo Fly attuale è ~$3/mese, sotto il buffer. |
| Esposizione dati sanitari su Internet | — | Path segreto + token, tool read-only, niente credenziali Garmin leggibili via MCP, `erasure.py` già disponibile; OAuth in hardening. |

## Ordine, effort complessivo e prompt di avvio

| Fase | Dipende da | Effort | Prompt per avviare la sessione di sviluppo |
|---|---|---|---|
| 0 — Verifica deploy | — | XS | "Esegui la Fase 0 di docs/MCP_CONNECTOR_ROADMAP.md: verifica il deploy Fly esistente (health, volume persistente, secrets, AI_ENABLED=false)." |
| 1 — Backfill storico | 0 (solo per il DB target) | M | "Esegui la Fase 1 di docs/MCP_CONNECTOR_ROADMAP.md: comando backfill paginato, idempotente e riprendibile, con throttling e archivio raw su Tigris." |
| 2 — Server MCP locale | — (parallelo a 0/1) | M | "Esegui la Fase 2 di docs/MCP_CONNECTOR_ROADMAP.md: monta FastMCP su /mcp con i tool v1 e il prompt running_coach, testabile da Claude Code in locale." |
| 3 — Remoto + auth | 0+2 | S (+M OAuth) | "Esegui la Fase 3 di docs/MCP_CONNECTOR_ROADMAP.md: esponi /mcp su Fly con path segreto, rate limit e tool read-only." |
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
| `fly.toml` + `deploy-fly.yml` (hosting, volume, always-on, CI deploy) | Il deploy esistente — riusato, nessuna modifica strutturale |
| **Nuovo da scrivere** | `backfill.py`, `mcp_server.py` (tool + prompt), 1 workflow GitHub Actions di sync notturno |
