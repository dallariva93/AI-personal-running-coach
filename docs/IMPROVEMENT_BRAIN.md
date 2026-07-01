# Coach Brain 2.0 — Piano di miglioramento del "cervello"

> Documento di lavoro derivato da *Coach Brain 2.0 – Gap Analysis e Roadmap
> evolutiva*. Descrive **come il coach gestisce le informazioni oggi**, **quali
> sono i limiti**, e **un piano incrementale** per trasformarlo da analizzatore
> reattivo a coach che pianifica verso un obiettivo.

Stato: ✅ tutte e 4 le fasi completate. Tutti i 23 gap del documento sono coperti
(alcuni parziali, vedi tabella). Dettaglio delle slice nella sezione 4.

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
   dislivello, salti di volume/intensità) al posto del solo ACWR/monotonia. ✅
8. **Gare multiple** (A/B/C). ✅

### Fase 3 — Coach avanzato
9. Deriva cardiaca, decoupling, **Aerobic Efficiency Index** (progresso). ✅
10. Evoluzione automatica delle soglie. Meteo. ✅

### Fase 4 — Coach elite
11. Trail engine, Goal/Race predictor, **Adaptive Planning Engine** dinamico. ✅

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

**Sesta slice — Fase 4, coach elite:**

- `app/processing/performance.py` — **Race/Goal Pace Predictor** (Riegel dai
  migliori sforzi, corretto dall'efficienza) con probabilità di centrare il
  target; **stima dinamica delle soglie** (LT2/critical speed) dagli sforzi
  intensi, auto-compilate all'ingest. API `GET /api/predict`.
- `app/processing/adaptive.py` — **Adaptive Planning Engine**: piega rischio
  infortunio, readiness e gap-obiettivo in un moltiplicatore di volume applicato
  al target di fase, con note esplicative. Esposto in `TrainingMetrics`.
- `app/processing/trail.py` (GAP 20) — **Trail engine**: vertical speed (VAM),
  D+/km, time on feet, distanza equivalente in piano; nota trail nell'analisi.
  API `GET /api/activities/{id}/trail`.
- `app/processing/load.py` — **correzione meteo del carico** (heat factor su
  temperatura/umidità), oltre alla nota qualitativa (GAP 18).
- **Sinergia con i dati Garmin ricchi**: l'efficienza usa la GAP pace quando
  disponibile; VO2max esposto a coach e dashboard; carico interno per `medio`/
  `trail`.
- Migrazione `bf76056f2179` per le colonne Garmin su `activities`.

**Settima slice — ricalibrazione del carico sui dati Garmin reali:**

- `internal_load` ora preferisce la **training load misurata da Garmin**
  (`activityTrainingLoad`, EPOC-based) quando presente, mappandola sulla scala
  sRPE; ricade su sRPE in demo/manuale (path offline invariato). Il caldo NON
  viene riapplicato alla load di Garmin (riflette già la FC elevata).
- `calibrate_garmin_factor`: fattore **per-atleta** = somma(sRPE)/somma(Garmin)
  sulle corse con entrambi i segnali (RPE o FC affidabili). Il rapporto-somma
  **preserva il carico totale** ma adotta la distribuzione per-seduta di Garmin;
  CTL/ATL/TSB restano sulla scala già tarata. Default 1.5 (ancorato a dati reali:
  corsa dura 42′ → Garmin 258 vs sRPE ~294).
- `TrainingMetrics.load_source` (garmin | mixed | srpe) per trasparenza, mostrato
  nel prompt.

### Stato finale
Tutti i 23 gap del documento sono coperti e le 4 fasi della roadmap completate,
con il modello di carico ora ancorato ai dati fisiologici reali di Garmin quando
disponibili. Possibili evoluzioni future: VDOT/Daniels per la previsione,
difficoltà tecnica del trail, UI dedicata per gare B/C e zone.

---

## 5. Limitazioni note e problemi non risolvibili

I seguenti limiti sono stati identificati durante il refactoring (P0-P3) ma non
sono risolvibili nel dominio del software, o lo sono solo parzialmente. Sono
documentati qui per trasparenza e per guidare future decisioni.

### 5.1 HR zone data non sempre disponibile (P0-5)

Il time-in-zone check in `execution.py` funziona solo quando `run.hr_zones` è
popolato. Attività inserite manualmente o senza sensore HR non hanno zone FC,
quindi il check viene saltato silenziosamente. Non è possibile inferire le zone
 dalla FC media sola senza conoscere le soglie individuali e la distribuzione
temporale. **Mitigazione**: il punteggio finale non viene penalizzato quando i
dati HR mancano (il check è additivo, non sostitutivo).

### 5.2 Streak: rest days solo dal piano attivo (P0-8)

Il bridging dei rest day in `compute_streak` considera solo i rest day del piano
attivo. Periodi senza piano, o rest day non pianificati, interrompono ancora la
streak. Non è possibile distinguere un "giorno di riposo pianificato" da un
"giorno saltato" senza un piano di riferimento. **Mitigazione**: quando un piano
è attivo, i rest day pianificati sono bridged correttamente.

### 5.3 days_to_race approssimato (P2-2)

La detection del taper in `adaptive_plan.py` usa `weeks_to_race * 7` come
approssimazione di `days_to_race`. Questo può essere off fino a 6 giorni. Una
stima precisa richiederebbe la `goal_date` del piano, non disponibile in
`TrainingMetrics` (che ha solo `weeks_to_race`). **Mitigazione**: la fase
periodization (`taper`/`race`) è usata come fallback, quindi il taper viene
rilevato comunque quando la fase è corretta.

### 5.4 RPE auto-riferito non validabile (P0-3)

Il RPE richiesto per mark-done è auto-riferito dall'atleta e non può essere
validato per accuratezza. Un atleta può inserire RPE=1 senza aver corso.
**Mitigazione**: il flusso preferito richiede un'attività registrata (con GPS/HR);
l'RPE è un fallback per sessioni indoor o senza dispositivo.

### 5.5 Confidence euristica, non statistica (P0-7)

La confidence basata sul signal disagreement è un'euristica (pesi fissi sui
disallineamenti), non una misura statistica di incertezza (es. intervallo di
confidenza bayesiano). Una calibrazione rigorosa richiederebbe un dataset
storico di decisioni e outcomes per stimare la correlazione tra disagreement e
tasso di errore. **Mitigazione**: i pesi sono ancorati a principi fisiologici
(segnali di carico in conflitto = incertezza reale).

### 5.6 Cooldown notifiche: query per-event (P3-2)

`_recently_notified` esegue una query DB per ogni evento pending, il che può
essere lento con molti eventi. Un'ottimizzazione (batch query per event_type)
è possibile ma non implementata per semplicità. **Mitigazione**: il limite di
20 notifiche e il dedupe_key mantengono il volume basso in pratica.

### 5.7 Adaptive plan: orizzonte fisso per fase (P2-2)

L'horizon dinamico è determinato dalla fase periodization, ma non si adatta a
eventi eccezionali (es. infortunio improvviso potrebbe richiedere orizzonte più
lungo per riprogrammare l'intera settimana). **Mitigazione**: il factor di
volume si applica a tutte le sessioni nell'orizzonte, e l'evento di infortunio
viene loggato e notificato con priority high.

