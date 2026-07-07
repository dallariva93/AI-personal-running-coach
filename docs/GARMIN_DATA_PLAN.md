# Piano di implementazione — dati Garmin non ancora sfruttati

Ordine dettagliato per catturare i dati Garmin che oggi scartiamo o non
leggiamo. Ogni fase è **spedibile in autonomia** e segue il workflow di
`docs/AGENT_PROMPT.md` (contratto in `schemas.py` → funzioni pure in
`collection`/`processing` → test → migration → wiring → Android → gate verdi).

## Stato attuale (perché serve questo piano)

- `sources.py::_fetch_enrichment` **scarica già** lo stream per-secondo
  (`get_activity_details` → `activityDetailMetrics`) ma lo usa solo per la
  traccia GPS + un profilo altimetrico ridotto (`_extract_gps_from_metric_stream`),
  poi lo **scarta**.
- `synthesize.py` distilla di proposito un sottoinsieme compatto in `RunSummary`
  (HR media/max, cadenza media, split per-km, zone HR, VO2max, TE, GAP, ecc.).
  Niente serie temporali, niente potenza, niente ripetute, niente dinamica.
- `GarminRawFetcher` archivierebbe i payload grezzi **completi**, ma è gated su
  `s3_enabled`: senza bucket S3 non conserviamo nulla.
- Storage: esistono solo `ObjectStore` (S3) e `InMemoryObjectStore` (test).
  **Manca** uno store su filesystem.

## Principi trasversali (validi per tutte le fasi)

1. **Le serie grezze NON vanno all'LLM.** `RunSummary` verso il coach resta
   compatto. Le serie per-secondo servono a UI e `processing`; per il coach si
   derivano **scalari** (es. decoupling HR/passo %, drift cardiaco, CV del
   passo, negative split) come funzioni pure in `app/processing/`.
2. **Additivo e nullable.** Ogni campo nuovo è opzionale; le migration sono
   additive (`alembic check` senza drift). L'app resta eseguibile senza
   credenziali (demo/offline): aggiungere dati campione ai fixture demo.
3. **Un solo campo JSON per le serie** (`sample_streams`) invece di N colonne:
   aggiungere una serie in futuro non richiede migration.
4. **Downsampling obbligatorio.** Serie riallineate su griglia comune a ~300
   punti: payload/piccolo storage, grafici fluidi.
5. **Riuso endpoint.** Le serie si ricavano dal `get_activity_details` che
   **già** scarichiamo: nessuna chiamata Garmin extra per la Fase 1.
6. **Gate per ogni fase.** `pytest --cov=app --cov-fail-under=80`,
   `ruff check app tests`, `alembic upgrade head && alembic check`. Android:
   check sintassi/bilanciamento + build APK in CI (niente SDK locale).

---

## FASE 0 — Non perdere più nulla: archivio grezzo su filesystem
**Leva massima, sblocca tutto il resto. Effort: S.**

Preserva **ogni** payload Garmin (details per-secondo, `typed_splits`, potenza,
GPX/TCX/FIT) con zero configurazione cloud, così qualunque dato futuro è
recuperabile a posteriori dai file salvati.

- `app/storage/object_store.py`: nuovo `LocalObjectStore` (stessa interfaccia
  `put_bytes/get_bytes/exists/delete`, scrive su directory).
- `app/config.py`: `raw_archive_dir` (default `./data/raw_archive`).
  `get_object_store()` → `LocalObjectStore` quando
  `raw_archive_enabled and not s3_enabled and raw_archive_dir`. S3 ha
  precedenza se configurato.
- Wiring: `_try_sync_raw_assets` è **già** invocato in `ingest.py:218`; con lo
  store non-`None` l'archiviazione parte da sola.
- DB: tabella `raw_activity_assets` **già esistente** (migration
  `c4d9f1a2b3e7`) → nessuna migration nuova.
- Erasure: `erasure.py` cancella già gli asset via `get_object_store()` →
  verificare che `LocalObjectStore.delete` sia coperto.
- Test: round-trip `LocalObjectStore`; ingest archivia details/typed_splits/
  power su dir locale; re-sync idempotente (skip `already_archived_kinds`).
- Nota retention: un `details.json` pesa ~1-5 MB. Documentare una policy
  (es. tenere N attività recenti + gare) — non implementarla ora.
- **Android: nessuna modifica.**

---

## FASE 1 — Serie per-secondo (HR, passo, cadenza, quota, potenza)
**Il salto di qualità più grande. Effort: L → 3 milestone.**

Alimenta i grafici densi in stile Garmin (`MetricAreaChart` già pronto) e le
metriche derivate per il coach.

### M1 — Estrazione backend + schema + migration
- `synthesize.py`: nuova pura `extract_sample_streams(details) -> dict`,
  generalizzando `_extract_gps_from_metric_stream`. Da `metricDescriptors`
  mappare per indice: `directheartrate`, `directspeed` (→ passo s/km),
  `directdoublecadence`/`directruncadence`, `directelevation`, `directpower`,
  più asse tempo (`sumduration`/`directtimestamp`). Riallineo su ~300 punti.
- Output compatto:
  `{"t":[...], "hr":[...], "pace_s":[...], "cadence":[...], "elev":[...], "power":[...]}`
  — solo le serie effettivamente presenti.
- `schemas.py`: `RunSummary.sample_streams: dict | None`.
- `db/models.py`: colonna `activities.sample_streams` (JSON/Text). Migration
  additiva.
- Test: estrazione da fixture `details` realistico (descrittori + righe),
  correttezza downsampling/allineamento, serie assenti gestite.

### M2 — Wiring sync + ingest + API
- `sources.py::_fetch_enrichment`: sullo **stesso** payload `get_activity_details`
  già scaricato per il GPS, chiamare anche `extract_sample_streams`
  (rinominare `skip_gps` → `skip_detail` così non si rifetcha se già in DB).
- `ingest.py`: persistere `sample_streams` in upsert; confermare erasure
  (colonna sulla riga attività → cancellata con l'attività, nessuna tabella
  nuova).
- API dettaglio attività: includere `sample_streams` nella risposta.
- `processing/`: nuove pure opzionali (decoupling HR/passo, drift cardiaco, CV
  passo) → eventualmente in `TrainingMetrics` per il coach.
- Test: API include le serie; feature derivate deterministiche con fixture.

### M3 — Android: grafici per-secondo
- `Models.kt`: `Activity.sampleStreams`.
- `ActivityDetailScreen.kt`: asse X a **tempo** (mm:ss) invece che km quando ci
  sono le serie; nuovo grafico **HR** (rosso), **Passo** per-secondo (blu, al
  posto dei per-km quando disponibile, con fallback a `splits_km`), grafico
  **Potenza** (viola) se presente. Riuso `MetricAreaChart`.
- Fixture demo con `sample_streams` così la demo mostra i grafici densi.
- Gate: bilanciamento + build APK CI.

Dipendenze: indipendente dalla Fase 0 (usa il fetch live), ma conviene dopo la
0 per non perdere i grezzi nel frattempo.

---

## FASE 2 — Struttura ripetute (`typed_splits`)
**Alto valore coaching, effort: M.**

Per gli allenamenti strutturati: passo/HR/recupero di **ogni ripetuta** (la
scheda "Ripetute" di Garmin), base per valutare l'esecuzione vs piano.

- `synthesize.py`: pura `extract_intervals(typed_splits) -> list[dict]`
  (tipo, distanza, durata, passo, HR medio, recupero).
- `sources.py`: chiamare `get_activity_typed_splits` in `_fetch_enrichment`
  (1 chiamata; già mappato in `garmin_raw._JSON_KINDS`).
- `schemas.py`/`models.py`: `laps: list | None` + migration.
- `processing/execution.py`: usare le ripetute per lo scoring per-rep,
  integrandosi con `evaluate_plan_executions`.
- Android: sezione "Ripetute" (tabella per-rep passo/HR).
- Test + gate.

Dipendenze: indipendente.

---

## FASE 3 — Potenza (riepilogo + zone)
**Effort: S (se Fase 1 fatta).**

- Campi `avg_power`/`max_power`/`power_zones` da `summaryDTO` +
  `get_activity_power_in_timezones` (già archiviato dalla Fase 0).
- `schemas.py`/`models.py` + migration; Android: stat potenza + barra zone
  (riuso `StackedBar`).

Dipendenze: la serie potenza arriva dalla Fase 1; i campi riepilogo sono
indipendenti.

---

## FASE 4 — Contesto recupero: Sonno + HRV + Readiness + RHR
**Altissimo valore, effort: L → 3 milestone.** Endpoint separati, per-data.

- Nuova tabella `daily_wellness(date PK, sleep_score, sleep_hours, deep/rem/
  light, hrv_overnight, hrv_status, training_readiness, resting_hr,
  body_battery_high/low, stress_avg)`.
- Nuovo job sync giornaliero: `get_sleep_data`, `get_hrv_data`,
  `get_training_readiness`, `get_rhr_day` su un range di date; join per data
  all'attività per il contesto.
- **M1**: sonno + RHR (tabella, sync, migration, erasure `_DELETE_ORDER`).
- **M2**: HRV + training readiness.
- **M3**: integrazione coaching (`build_today_decision`, debrief, adattamento
  piano) + Android (card "Prontezza" su Oggi; "sonno notte prima" su attività).
- Test + gate ad ogni milestone.

Dipendenze: indipendente da 1-3.

---

## FASE 5 — Dinamica di corsa + respiro + stamina (device-dependent)
**Effort: M, economica se Fase 1 c'è.**

- Dalla stessa infrastruttura serie (Fase 1): GCT, oscillazione verticale,
  vertical ratio, lunghezza passo, respiro, curva stamina + medie.
- `schemas.py`/`models.py`: aggiungere serie a `sample_streams` (nessuna
  migration grazie al JSON unico) + campi medi.
- Android: sezione "Dinamica di corsa".

Dipendenze: costruisce sull'infra della Fase 1.

---

## FASE 6 — Contorno (batch finale)
**Effort: S, priorità minima.**

Calorie (attive/totali), moving vs elapsed, max/min pace, sweat loss, SpO2,
stress medio, timeline Body Battery completa (oggi solo il delta). Campi
riepilogo economici, raggruppati in un'unica passata.

---

## Ordine consigliato e razionale

| Ordine | Fase | Perché prima | Effort |
|--------|------|--------------|--------|
| 1 | **0 — archivio grezzo** | Smette di perdere dati oggi; sblocca recuperi futuri senza rifetch | S |
| 2 | **1 — serie per-secondo** | Massimo valore UX+coaching; dati già scaricati | L (3 ms) |
| 3 | **2 — ripetute** | Sblocca lo scoring per-rep vs piano | M |
| 4 | **3 — potenza** | Piccola dopo la Fase 1 | S |
| 5 | **4 — recupero (sonno/HRV/readiness)** | Nuova superficie ad alto valore, ma più grande | L (3 ms) |
| 6 | **5 — dinamica di corsa** | Economica sull'infra Fase 1, device-dependent | M |
| 7 | **6 — contorno** | Completamento, priorità minima | S |

**Pilota consigliato**: Fase 0 + Fase 1/M1 (solo serie HR) come prova end-to-end
prima di allargare alle altre serie.
