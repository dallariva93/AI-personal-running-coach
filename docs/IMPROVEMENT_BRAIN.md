# Coach Brain 2.0 — Piano di miglioramento del "cervello"

> Documento di lavoro derivato da *Coach Brain 2.0 – Gap Analysis e Roadmap
> evolutiva*. Descrive **come il coach gestisce le informazioni oggi**, **quali
> sono i limiti**, e **un piano incrementale** per trasformarlo da analizzatore
> reattivo a coach che pianifica verso un obiettivo.

Stato: 🟡 in corso. Le sezioni marcate ✅ sono già implementate in questo branch.

---

## 1. Come ragiona il cervello oggi

Il flusso attuale (`app/services/ingest.py`) è:

```
RunSummary[]  ──►  compute_metrics()  ──►  TrainingMetrics  ──►  Coach  ──►  CoachingResult
 (storico)          (processing)            (carico/forma)      (prompt)     (analisi+next)
```

**Informazioni in ingresso** (`RunSummary`): data, tipo (etichetta), durata,
distanza, passo medio, FC media/max, dislivello, cadenza, RPE opzionale, note,
tempo nelle zone FC, splits.

**Come le pesa** (`app/processing/metrics.py`):
- Carico = **solo chilometri** (`acute_load_km`, `chronic_load_km`).
- Metrica principale = **ACWR** (acute 7gg / media settimanale 28gg).
- `form_state` derivato **esclusivamente dall'ACWR**.
- `easy_ratio` 80/20 basato sull'**etichetta** dell'attività.
- `monotony` sui km giornalieri.
- Orizzonte temporale: ultima corsa, ultimi 7 giorni, ultime settimane.

**Come le usa** (`app/coaching/`): il prompt riceve il JSON di `TrainingMetrics`
+ 10-14 corse recenti. Decide il *prossimo* allenamento reagendo allo stato
attuale. Il coach offline applica le stesse regole in modo deterministico.

**Limite di fondo (dal documento):** il sistema è *orientato al presente*. Non
conosce un obiettivo, non periodizza, non stima forma/fatica in modo dinamico,
non misura il progresso, non personalizza sulle soglie reali dell'atleta.

---

## 2. Mappa dei gap → codice

| # | Gap | Impatto | Dove interviene | Stato |
|---|-----|---------|-----------------|-------|
| 1 | Nessun obiettivo sportivo (Goal) | Massimo | `schemas.py` + `db` model + form | ✅ persistito |
| 2 | Nessuna periodizzazione (macro/meso/micro) | Molto alto | `processing/periodization.py` | ✅ |
| 3 | ACWR sovrastimato | Molto alto | `metrics.py` (demota a secondaria) | ✅ |
| 4 | Carico solo su km | Molto alto | nuovo `processing/load.py` | ✅ |
| 5 | Easy ratio poco affidabile (etichetta) | Alto | `load.py` (intensità reale da FC/zone) | ✅ parziale |
| 6 | Zone personalizzate assenti | Molto alto | `schemas.py` `HRZones` | ✅ schema |
| 7 | Soglie fisiologiche assenti (LT1/LT2/CS) | Molto alto | `schemas.py` `AthletePhysiology` | ✅ schema |
| 8 | Nessun modello Fitness/Fatigue | Molto alto | `metrics.py` CTL/ATL/TSB | ✅ |
| 9 | Nessun monitoraggio recupero (sonno/stress) | Alto | `DailyCheckin` + `recovery.py` + form | ✅ |
| 10 | RPE sottoutilizzato | Molto alto | `load.py` (session load) | ✅ |
| 11 | Nessuna deriva cardiaca | Medio-alto | `processing/efficiency.py` | ✅ |
| 12 | Nessun decoupling | Alto | `processing/efficiency.py` | ✅ |
| 13 | Nessuna misura del miglioramento | Molto alto | Aerobic Efficiency Index | ✅ |
| 14 | Modello infortuni troppo semplice | Molto alto | `processing/injury.py` | ✅ |
| 15 | Disponibilità atleta ignorata | Molto alto | `AthleteProfile.available_days` | ✅ schema+prompt |
| 16 | Nessuna gestione gare B/C | Medio-alto | `AthleteProfile.races` (A/B/C) | ✅ persistito |
| 17 | Assenza di taper | Molto alto | `periodization.py` (taper progressivo) | ✅ |
| 18 | Meteo ignorato | Medio | synthesize + nota caldo | ✅ parziale |
| 19 | Dislivello sottostimato | Alto | `load.py` (equivalent flat / GAP) | ✅ parziale |
| 20 | Trail running non supportato | Medio-alto | D-/meteo catturati | ✅ parziale |
| 21 | Prompt troppo grezzo (solo JSON) | Alto | `prompts.py` strato semantico | ✅ parziale |
| 22 | Memoria storica limitata (10-14 corse) | Molto alto | `snapshot.py` (best/medie 6m) | ✅ |
| 23 | Profilo atleta non strutturato | Molto alto | `AthleteProfile` + `db` + form | ✅ persistito |

---

## 3. Roadmap incrementale

Seguo le 4 fasi del documento, ma consegno **slice verticali testabili** che
mantengono l'app eseguibile offline e la coverage ≥ 80%.

### Fase 1 — Fondamenta *(in corso)*
1. **Modelli dati strutturati** — `AthleteProfile`, `AthletePhysiology`,
   `HRZones`, `Goal` in `app/schemas.py`. ✅
2. **Carico interno/esterno** — `app/processing/load.py`:
   `session_load = RPE × durata` con fallback TRIMP (da FC) e stima da tipo;
   carico esterno = km + *equivalent flat distance* per il dislivello. ✅
3. **Intensità reale** — quota facile/intensa derivata da FC/zone, non solo
   dall'etichetta (riduce il problema del GAP 5). ✅ parziale
4. **Zone personalizzate** nel profilo, usate da prompt e regole. ✅ schema

### Fase 2 — Coach reale
5. **Fitness/Fatigue (CTL/ATL/TSB)** come input principale; ACWR retrocesso a
   metrica secondaria; `form_state` derivato dal TSB. ✅
6. **Periodizzazione** macro→meso→micro verso `Goal.target_date` + **taper**. ✅
7. **Injury Risk Score** composito (giorni consecutivi, qualità ravvicinate,
   dislivello, salti di volume/intensità) al posto del solo ACWR/monotonia.
8. **Gare multiple** (A/B/C).

### Fase 3 — Coach avanzato
9. Deriva cardiaca, decoupling, **Aerobic Efficiency Index** (progresso).
10. Evoluzione automatica delle soglie. Meteo.

### Fase 4 — Coach elite
11. Trail engine, Goal/Race predictor, **Adaptive Planning Engine** dinamico.

---

## 4. Cosa è stato fatto in questo branch

Prima slice verticale (Fase 1 + cuore della Fase 2), perché tocca direttamente
"come pesa le informazioni":

- `app/processing/load.py` — carico interno (RPE/TRIMP/stima) ed esterno
  (km + dislivello), classificazione intensità reale.
- `app/processing/metrics.py` — CTL/ATL/TSB (modello impulso-risposta),
  `form_state` guidato dal TSB, ACWR mantenuto ma **secondario**, easy ratio
  basato sull'intensità reale quando disponibile.
- `app/schemas.py` — `HRZones`, `AthletePhysiology`, `AthleteProfile`, `Goal`,
  campi nuovi in `TrainingMetrics`.
- `app/coaching/prompts.py` — strato semantico (frasi sintetiche oltre al JSON)
  e contesto obiettivo.
- Test nuovi in `tests/unit/`.

**Seconda slice — profilo atleta e obiettivo persistiti:**

- `app/db/models.py` — tabella singleton `athlete_profile` (scalari + JSON per
  zone/fisiologia + colonne goal) e migrazione Alembic `8ea1979f712e`.
- `app/services/profile.py` — `get_profile` / `save_profile` (ORM ↔ Pydantic).
- Pipeline collegata: `compute_metrics` e il coach ora ricevono il profilo;
  il prompt allena *verso la gara* (countdown a settimane, giorni disponibili).
- Zone FC derivate automaticamente dalla FC max (GAP 6).
- Dashboard: banner obiettivo + form profilo/gara (HTMX); card forma con
  TSB/CTL/ATL. API `GET/PUT /api/profile`.

**Terza slice — periodizzazione e taper:**

- `app/processing/periodization.py` — costruisce il macrociclo a ritroso dalla
  data gara: Base→Build→Specific→Peak→Taper→Race, con volume target relativo al
  baseline e focus per fase; taper progressivo (più lungo per la maratona).
- `compute_metrics` espone la **fase attuale** in `TrainingMetrics`
  (`phase`, `phase_focus`, `weeks_to_race`, `phase_volume_target_km`) — così la
  periodizzazione viaggia verso il coach tramite il contratto `schemas`,
  rispettando il disaccoppiamento dei layer.
- Coach: prompt e OfflineCoach rispettano la fase (template di settimana per
  fase; in taper riducono il volume). La rete di sicurezza "affaticato → scarico"
  ha la precedenza.
- Ricalibrato il modello Fitness/Fatigue su scala TSS-like (`LOAD_SCALE`) e i
  threshold del `form_state`; aggiunto stato `detraining` esplicito (nessun
  carico negli ultimi 7 giorni con base presente).
- Dashboard: timeline delle fasi con evidenza della fase corrente.
  API `GET /api/plan/periodization`.

**Quarta slice — rischio infortunio, efficienza e memoria:**

- `app/processing/injury.py` (GAP 14) — Injury Risk Score 0-100 composito
  (ACWR, monotonia, salti di volume, giorni consecutivi, sedute intense
  ravvicinate, quota facile bassa) con livello e fattori spiegabili.
- `app/processing/efficiency.py` (GAP 11/12/13) — Aerobic Efficiency Index
  (passo a pari FC) con trend; decoupling/deriva cardiaca per-corsa dagli split.
- `app/processing/snapshot.py` (GAP 22) — `AthleteSnapshot` a 6 mesi come
  memoria storica nel piano settimanale.

**Quinta slice — recupero, scheduling, gare multiple, meteo/trail:**

- `app/processing/recovery.py` + `DailyCheckin` (GAP 9) — readiness 0-100
  (sonno/fatica/dolori/motivazione) con semaforo; `red` forza lo scarico.
  Form di check-in in dashboard, API `GET/POST /api/checkin`, migrazione
  `f9e70191b8b5`.
- Scheduling sui `available_days` reali nel planner offline (GAP 15).
- Gare secondarie A/B/C in `AthleteProfile.races`, citate nel prompt (GAP 16).
- Cattura meteo (temperatura/umidità) e trail (D-) in `synthesize`, con nota
  "caldo" nell'analisi (GAP 18/20).

## 5. Prossimi passi (Fase 4 — coach elite)
- **Adaptive Planning Engine**: ricalcolo dinamico del piano a ogni nuova corsa.
- **Race/Goal Pace Predictor**: stima del tempo gara da CTL + efficienza.
- Evoluzione automatica di zone e soglie nel tempo (GAP 7 dinamico).
- Trail engine completo (vertical speed, time on feet, difficoltà tecnica) e
  correzione meteo del carico (oltre alla nota qualitativa attuale).
- UI per gestire le gare B/C e affinare manualmente le zone.
