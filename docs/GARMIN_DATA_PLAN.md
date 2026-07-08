# Dati Garmin — analisi architetturale e piano d'implementazione

Documento in due parti: **(A) analisi** — quali dati Garmin esistono, quanto
valgono, se sono recuperabili e con quale decisione; **(B) piano** — ordine di
implementazione derivato dall'analisi, non dall'effort.

Ogni fase segue il workflow di `docs/AGENT_PROMPT.md` (contratto in
`schemas.py` → funzioni pure → test → migration → wiring → Android → gate).

> Le valutazioni di **copertura dispositivo** sono fatti Garmin generali e vanno
> confermate sul modello dell'utente. Le voci marcate `?` vanno verificate
> contro la versione di `python-garminconnect` installata prima di impegnarsi.

---

# PARTE A — Analisi

## A0. Stato attuale (perché serve questo lavoro)

- `sources.py::_fetch_enrichment` **scarica già** lo stream per-secondo
  (`get_activity_details` → `activityDetailMetrics`) ma lo usa solo per GPS +
  profilo altimetrico ridotto, poi lo **scarta**.
- `synthesize.py` distilla un sottoinsieme compatto in `RunSummary` (HR
  media/max, cadenza media, split per-km, zone HR, VO2max, TE, GAP…). Niente
  serie temporali, potenza, ripetute, dinamica.
- `GarminRawFetcher` archivierebbe i grezzi completi ma è gated su `s3_enabled`
  → senza bucket non conserviamo nulla. Esistono solo `ObjectStore` (S3) e
  `InMemoryObjectStore` (test): **manca** uno store su filesystem.

## A1. Matrice decisionale principale

Colonne: **Coach** = valore per il ragionamento del coach; **UI** = valore per
la visualizzazione; **Costo** = implementazione; **Device** = copertura
hardware; **N/D** = Native (Garmin lo calcola, non ricalcolabile) o Derived
(ricavabile da altro dato). Decisione: Implementare / Valutare / Rimandare /
Scartare.

| Dato | Disponibile | Coach | UI | Costo | N/D | Device | **Decisione** |
|------|-------------|-------|----|-------|-----|--------|---------------|
| **HR stream** | ✅ già scaricato | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | Basso | Native | Quasi tutti | **Implementare** |
| **Pace/Speed stream** | ✅ già scaricato | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | Basso | speed Native / pace Derived | Tutti | **Implementare** |
| **Elevation stream** | ✅ già scaricato | ⭐⭐⭐ | ⭐⭐⭐⭐ | Basso | Native | Tutti | **Implementare** |
| **Cadence stream** | ✅ già scaricato | ⭐⭐⭐ | ⭐⭐⭐ | Basso | Native (media Derived) | Tutti | **Implementare** |
| **Ripetute** (`typed_splits`) | ✅ da chiamare | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | Basso | Native | Tutti | **Implementare** |
| **Power** (stream+medie+zone) | ✅ già scaricato¹ | ⭐⭐⭐⭐ | ⭐⭐⭐ | Basso | Native | Solo alcuni | **Implementare** (se device) |
| **Sleep** (notte prima) | ✅ da chiamare | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | Medio | Native | Quasi tutti | **Implementare** |
| **HRV** (overnight+status) | ✅ da chiamare | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | Medio | Native | Recenti | **Implementare** |
| **Training Readiness** | ✅? da chiamare | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | Medio | Native | Solo recenti | **Implementare** |
| **Resting HR** (trend) | ✅ da chiamare | ⭐⭐⭐⭐ | ⭐⭐ | Basso | Native | Quasi tutti | **Implementare** |
| **Body Battery timeline** | ✅ da chiamare² | ⭐⭐⭐ | ⭐⭐⭐ | Medio | Native | Modern | **Valutare** |
| **Training Status / Load** | ✅? da chiamare | ⭐⭐⭐ | ⭐⭐ | Medio | Native | Recenti | **Valutare** |
| **Recovery Time** | ? verificare | ⭐⭐⭐ | ⭐⭐ | ? | Native | Modern | **Valutare** |
| **Race predictions** (Garmin) | ✅? `get_max_metrics` | ⭐⭐ | ⭐⭐⭐ | Basso | Native | Recenti | **Valutare** |
| **Stress** | ✅ da chiamare | ⭐⭐ | ⭐⭐ | Basso | Native | Modern | **Rimandare** |
| **Running Dynamics** (GCT, osc. vert., stride) | ✅ se HRM-Pro/device | ⭐⭐ | ⭐⭐ | Medio | Native | Solo HRM/top | **Rimandare** |
| **Stamina** (curva) | ? alcuni device | ⭐⭐ | ⭐⭐⭐ | Alto | Native | Pochi | **Rimandare** |
| **Respiration** | ✅ alcuni | ⭐ | ⭐ | Medio | Native | Alcuni | **Non ora** |
| **Temperature stream** | ✅ già scaricato | ⭐ | ⭐ | Basso | Native | Tutti | **Scartare** |
| **Calories / moving-elapsed** | ✅ già scaricato | ⭐ | ⭐⭐ | Basso | Native/Derived | Tutti | **Scartare** |
| **Sweat Loss** | ✅? | ⭐ | ⭐ | Medio | Native | Alcuni | **Scartare** |
| **SpO2** | ✅ da chiamare | ✩ quasi nullo | ⭐ | Medio | Native | Alcuni | **Scartare** |

¹ Nel medesimo payload `get_activity_details`; medie/max anche in `summaryDTO`;
zone via `get_activity_power_in_timezones`. Presente solo se il device registra
la potenza. ² Oggi salviamo solo `body_battery_delta`, non la curva.

## A2. Disponibilità reale via API Garmin

Distingue **dati persi perché non li leggiamo** da **recuperabili** da **non
esposti**. Nomi metodo riferiti a `python-garminconnect`.

| Informazione | API esiste | Già scaricata | Da chiamare | Incerto/Verificare |
|--------------|-----------|---------------|-------------|--------------------|
| HR / speed / cadence / elevation stream | ✅ `get_activity_details` | ✅ (scartata) | — | — |
| Power stream / avg / max | ✅ `get_activity_details` / `..._power_in_timezones` | ✅ (scartata)¹ | zone | — |
| Training Effect / VO2max / Load / GAP / fastest splits | ✅ `get_activity` | ✅ | — | — |
| Ripetute per-rep | ✅ `get_activity_typed_splits` | — | ✅ | — |
| Running Dynamics (GCT, osc, stride) | ✅ (nello stream) | parziale | ✅ | esposizione nel descrittore `?` |
| Respiration stream | ✅ (nello stream) | — | ✅ | `?` |
| Sleep | ✅ `get_sleep_data(date)` | — | ✅ | — |
| HRV overnight + status | ✅ `get_hrv_data(date)` | — | ✅ | device `?` |
| Training Readiness | ✅? `get_training_readiness(date)` | — | ✅ | metodo/versione `?` |
| Resting HR | ✅ `get_rhr_day(date)` | — | ✅ | — |
| Body Battery timeline | ✅ `get_body_battery(...)` | delta sì | ✅ curva | — |
| Stress | ✅ `get_stress_data(date)` | — | ✅ | — |
| Training Status / Load Focus / A:C Garmin | ✅? `get_training_status` | — | ✅ | forma payload `?` |
| Recovery Time | `?` | — | `?` | dove viva `?` |
| Stamina real-time | `?` | — | `?` | esposizione `?` |
| Race predictions | ✅? `get_max_metrics` | — | ✅ | `?` |
| SpO2 | ✅ `get_spo2_data(date)` | — | ✅ | — |

¹ La potenza passa nel payload che già scarichiamo ma non viene estratta.

## A3. Storico vs Live — recuperabilità nel tempo (punto critico)

Non tutti i dati sono recuperabili quando vogliamo. Due classi con
comportamento opposto:

- **Storico / immutabile** — legato all'attività, ri-scaricabile in qualsiasi
  momento: `get_activity_details`, splits, typed_splits, TE, VO2max. *Nessuna
  urgenza di cattura*: se ci serve tra un anno, lo prendiamo.
- **Live / a scadenza** — snapshot giornalieri che Garmin **può smettere di
  esporre** con l'andare del tempo: **Body Battery, Training Readiness, Stress,
  HRV giornaliero, (in parte) Sleep**. Il Body Battery di ieri potrebbe non
  essere più recuperabile fra mesi.

**Conseguenza architetturale forte**: la cattura dei dati *live* va avviata
**presto**, anche se la loro UI arriva dopo. Un job giornaliero economico che
fa uno snapshot in `daily_wellness` evita di perdere storia irripetibile.
Questo **cambia l'ordine**: non basta "prima ciò che ha UI"; i dati live vanno
catturati subito (vedi Parte B).

## A4. Native vs Derived — evitare ridondanza

- **Pace**: Derived da `speed`. Salvare **solo speed** (m/s), derivare il passo
  in UI/processing. (I `splits_km` per-km restano come sono: già in DB.)
- **Cadenza media**: Derivabile dalla serie cadenza. Se salviamo la serie, la
  media diventa ridondante — la teniamo solo per attività **senza** serie e per
  retro-compatibilità.
- **Elevation gain/loss**: Derivabili dalla serie quota, ma Garmin applica
  correzioni proprietarie → teniamo il valore **Native** di Garmin.
- **Training Effect / VO2max / Load / Readiness / HRV status**: **Native puri**,
  non ricalcolabili → vanno salvati sempre.

Regola: salvare Native; derivare il resto a runtime. Un campo Derived si
persiste solo se il ricalcolo è costoso o serve indicizzarlo.

## A5. Tier di priorità (cosa manca "davvero" se ci fermiamo al 60%)

- **Tier A — Fondamentali**: HR, pace/speed, cadence, elevation, splits,
  ripetute, power. Sono il cuore dell'esperienza corsa.
- **Tier B — Molto utili**: sleep, HRV, training readiness, RHR, body battery.
  Contesto recupero/prontezza; **time-sensitive** (vedi A3).
- **Tier C — Accessori**: running dynamics, stamina, respiration, sweat loss,
  SpO2, stress, temperature. Nice-to-have, spesso device-dependent.

## A6. Copertura dispositivi Garmin (influenza il ROI)

Fatti generali — confermare sul device dell'utente (le schermate mostrano
**Potenza 327 W** → device di fascia medio-alta con power nativo).

| Dato | FR55 | FR255/955 | FR265/965 · Fenix7 · Epix | HRM-Pro |
|------|------|-----------|---------------------------|---------|
| HR / pace / cadence / elevation | ✅ | ✅ | ✅ | — |
| Running Power | ❌ | ✅ | ✅ | ✅ (aggiunge) |
| Running Dynamics | ❌ | parz. | ✅ | ✅ |
| Stamina real-time | ❌ | ✅ | ✅ | — |
| HRV status | parz. | ✅ | ✅ | — |
| Training Readiness | ❌ | ❌/parz. | ✅ | — |
| Body Battery / Respiration | ✅ | ✅ | ✅ | — |

Implicazione: Tier A (tranne power) ha ROI massimo perché copre **tutti** i
device; power/dynamics/stamina hanno ROI condizionato al modello.

## A7. Costo storage (stime, per decidere consapevolmente)

**Serie per-secondo (`sample_streams`)** — con downsampling adattivo (A8), in
media ~600 punti × ~6 serie. Come JSON di numeri: ~5 byte/valore →
~18 KB/attività non compresso, ~5 KB gz.

| Scala | Attività | Non compresso | gz |
|-------|----------|---------------|----|
| 1 utente, 10 anni (~300/anno) | 3.000 | ~54 MB | ~15 MB |
| 100.000 utenti, 10 anni | 300 M | ~5,4 TB | ~1,5 TB |

→ **Trascurabile** in single-tenant; gestibile in object storage a scala SaaS.

**Archivio grezzo (FIT + JSON)** — il vero costo: un FIT pesa ~0,3–1 MB.

| Scala | Non compresso |
|-------|---------------|
| 1 utente, 10 anni | ~1,5–3 GB |
| 100.000 utenti | ~150–300 TB |

→ Le serie downsampled costano poco; **l'archivio grezzo richiede una policy di
retention** a scala (tenere N recenti + gare, il resto su storage freddo o
scaduto). In single-tenant è irrilevante.

## A8. Downsampling adattivo (non fisso a 300)

300 punti fissi appiattiscono un 6 ore quanto un 20 minuti. Adottiamo soglie
per durata (target ~1 punto ogni 2–4 s, con tetto):

| Durata sessione | Punti/serie |
|-----------------|-------------|
| ≤ 30 min | 300 |
| 30–90 min | 600 |
| > 90 min | 1200 |

In alternativa un LTTB (Largest-Triangle-Three-Buckets) per preservare i picchi.
Per la v1 bastano le soglie; l'importante è **non** fissare 300.

## A9. Perché `sample_streams` come JSON unico (con i suoi limiti)

**Vantaggi**: evolvere senza migration (nuova serie = nuova chiave); lettura
per-attività a oggetto intero (il pattern reale: render grafico + estrazione
feature della singola corsa).

**Svantaggi da mettere in chiaro**: non indicizzabile; niente query SQL sui
valori interni; niente `GROUP BY`/aggregati cross-attività dal DB; analytics più
lente se un giorno servissero.

**Perché è accettabile**: le serie non si interrogano *mai* trasversalmente in
SQL — si leggono per singola attività. Le domande aggregate ("drift medio del
mese", "CV del passo") si rispondono su **scalari derivati** (decoupling, drift
cardiaco, CV passo) che calcoliamo in `processing/` e salviamo in **colonne
vere, indicizzabili**. Quindi: serie grezze in JSON blob; feature aggregate in
colonne. Se in futuro servisse analytics sulle serie, si esporta il blob in un
formato colonnare (Parquet) offline — non è il caso d'uso del DB operativo.

## A10. Archivio grezzo: FIT canonico, non 4 formati

Oggi `_DOWNLOAD_KINDS` archivia GPX + TCX + FIT. Ma **GPX/TCX sono viste
derivate del FIT**: dal FIT si rigenerano (parser `fitdecode`/`fitparse`).
Decisione: archiviare **FIT (originale) come canonico** + `details.json`/
`summary.json` per comodità (evita un parse nel caso comune); trattare GPX/TCX
come **rigenerabili on-demand** → non archiviarli di default. Riduce lo storage
grezzo di ~2× senza perdita d'informazione.
Caveat: verificare che il FIT contenga davvero tutti i campi calcolati che oggi
leggiamo dal `details.json` (alcuni valori Garmin-computed potrebbero vivere
solo nel JSON) prima di dismettere l'archivio JSON.

## A11. Robustezza futura del parser

Garmin aggiunge/rinomina descrittori nel tempo. Il parser delle serve deve
essere **tollerante**: mappatura per `metricsKey` (come già in
`_extract_gps_from_metric_stream`), descrittore sconosciuto →
`log.warning` → ignora la colonna → prosegui. **Mai** eccezione che aborta
l'ingest. Un test dedicato con un descrittore ignoto deve dimostrare che le
altre serie sopravvivono.

## A12. Dati volutamente ignorati (per chiudere le discussioni future)

**NON implementiamo** (con motivo):

- **SpO2** — valore coaching quasi nullo per la corsa.
- **Sweat loss** — stima grezza, poco azionabile.
- **Respiration** — segnale secondario ridondante con HR.
- **Temperature/meteo per-secondo** — la media già la teniamo; il resto è
  rumore (il meteo lo trattiamo altrove).
- **Calorie** — basso valore coaching, derivato.
- **Gear/segmenti Strava** — le scarpe le tracciamo già (`shoe_id`); i segmenti
  non rientrano nel modello del coach.
- **Live tracking di terzi** — abbiamo la nostra pipeline live (G1/G5).

Riesaminare solo se emerge un caso d'uso concreto.

---

# PARTE B — Piano d'implementazione (ordinato per valore + scadenza)

Ordine derivato dall'analisi: prima ciò che **vale di più** e ciò che **non è
recuperabile dopo** (dati live, A3), non ciò che è più comodo.

## FASE 0 — Fondamenta: archivio grezzo su filesystem + cattura wellness
**Effort: S–M. Sblocca tutto e ferma la perdita di dati irripetibili.**

Due mosse indipendenti ma entrambe "non perdere dati":

**0a. Archivio grezzo locale** — `LocalObjectStore` (filesystem, stessa
interfaccia); `config.raw_archive_dir`; `get_object_store()` lo usa quando
`raw_archive_enabled and not s3_enabled`. `_try_sync_raw_assets` è già invocato
(`ingest.py:218`). Archiviare **FIT + details.json** (A10), non GPX/TCX. Tabella
`raw_activity_assets` già esistente. Test: round-trip, idempotenza, `delete`
per erasure.

**0b. Snapshot wellness giornaliero (cattura, UI dopo)** — job periodico che
salva in nuova tabella `daily_wellness(date PK, …)` gli snapshot **live**
(body battery, readiness, stress, HRV, RHR, sleep). Serve **subito** perché
questi dati scadono (A3). Anche solo scrivere le righe senza UI protegge la
storia. Aggiornare `erasure._DELETE_ORDER`.

## FASE 1 — Serie per-secondo (Tier A) — 3 milestone
**Effort: L. Il salto UX+coaching maggiore; dati già scaricati.**

- **M1 — estrazione+schema+migration**: `extract_sample_streams(details)` pura,
  generalizza `_extract_gps_from_metric_stream`; **parser tollerante** (A11);
  **downsampling adattivo** (A8); salva **speed** (non pace, A4). Colonna JSON
  `activities.sample_streams`. Feature scalari derivate (decoupling, drift, CV)
  in `processing/` → colonne indicizzabili (A9).
- **M2 — wiring+ingest+API**: estrarre dallo **stesso** `get_activity_details`
  già scaricato (rinominare `skip_gps`→`skip_detail`); persistere; esporre in
  API.
- **M3 — Android**: asse X a tempo; grafici HR (rosso), passo per-secondo (blu,
  fallback `splits_km`), potenza (viola) se presente. Riuso `MetricAreaChart`.
  Fixture demo con serie.

## FASE 2 — Ripetute (`typed_splits`) (Tier A)
**Effort: M.** `extract_intervals` pura; chiamare `get_activity_typed_splits`;
campo `laps`; scoring per-rep in `execution.py`; sezione Android "Ripetute".

## FASE 3 — Potenza riepilogo + zone (Tier A/B, se device)
**Effort: S dopo Fase 1.** `avg/max_power` + `power_zones` da `summaryDTO` +
`power_in_timezones`; stat + barra zone (`StackedBar`).

## FASE 4 — Recupero: UI e coaching sui dati wellness (Tier B)
**Effort: L.** La **cattura** è già in Fase 0b; qui si aggiungono lettura,
integrazione nel coach (`build_today_decision`, debrief, adattamento piano) e
Android (card "Prontezza" su Oggi; "sonno notte prima" su attività). Milestone:
M1 sonno+RHR, M2 HRV+readiness, M3 coaching+Android.

## FASE 5 — Dinamica di corsa (Tier C, device-dependent)
**Effort: M, economica sull'infra Fase 1.** GCT, oscillazione verticale,
vertical ratio, stride, + medie, aggiunte a `sample_streams` (nessuna migration
grazie al JSON unico). Solo se il device li espone.

## FASE 6 — Contorno (Tier C, batch, priorità minima)
Solo se emerge un caso d'uso: body battery timeline completa, training status.
Il resto (A12) resta escluso per scelta.

## Ordine consigliato e razionale

| Ordine | Fase | Perché | Tier | Effort |
|--------|------|--------|------|--------|
| 1 | **0 — grezzo + cattura wellness** | Ferma la perdita di dati; i live scadono (A3) | — / B | S–M |
| 2 | **1 — serie per-secondo** | Valore massimo, dati già scaricati | A | L |
| 3 | **2 — ripetute** | Scoring per-rep vs piano | A | M |
| 4 | **3 — potenza** | Piccola dopo Fase 1 | A/B | S |
| 5 | **4 — UI+coaching recupero** | Alto valore; cattura già avviata in Fase 0b | B | L |
| 6 | **5 — dinamica di corsa** | Economica, device-dependent | C | M |
| 7 | **6 — contorno** | Solo su caso d'uso | C | S |

**Pilota consigliato**: Fase 0 (0a+0b) + Fase 1/M1 con la sola **serie HR**,
come prova end-to-end del parser tollerante, del downsampling adattivo e dello
schema `sample_streams`, prima di allargare a tutte le serie.
