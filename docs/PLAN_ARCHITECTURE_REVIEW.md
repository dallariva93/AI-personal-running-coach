# Revisione architetturale — Piano di allenamento

Analisi completa del ciclo di vita del piano (generazione, gestione,
adattamento, modifica, visualizzazione) con due lenti: **coach élite**
(debolezze di allenamento) e **AI/software architect** (soluzione target).

**Obiettivo**: un piano *perfetto, tarato sulla persona*, costruito dalla chat
AI e dai dati reali dell'atleta.

**Tesi centrale (una riga)**: oggi l'intelligenza di coaching vive nell'LLM —
inaffidabile, generico, che "inventa" tutto il piano — con un fallback offline
debole e una toppa di enforcement. La soluzione è **spostare l'intelligenza di
periodizzazione in un motore deterministico guidato dai dati**, e ridurre l'LLM
a ciò in cui è forte: **l'intervista** e la **verbalizzazione**. Questo inverte
il design attuale.

---

## Cosa NON buttare (già buono)

- **La chat di negoziazione** (`chat_for_plan` + `PLAN_CHAT_SYSTEM_PROMPT`):
  raccolta vincoli, categorie fatti/preferenze/scelte, budget conferme. È il
  pezzo migliore e va tenuto quasi intatto.
- **Il contratto giorno→tipo** (`enforce_week_structure`): l'istinto giusto —
  rendere deterministico ciò che l'atleta ha confermato.
- **La cattura `base_*`** su `TrainingPlanSession` (idempotenza dell'adattamento
  senza compounding). Ottimo pattern.
- **Lo scoring d'esecuzione** (`execution_service`) e le **warning di
  adiacenza** su `move_session`: buone fondamenta.
- **Il Digital Twin** (`personal_ramp_factor`): il seme giusto per la
  personalizzazione.

---

# PARTE 1 — Lente coach élite: debolezze e incongruenze

Riferimenti al codice reale.

### 1.1 Il modello di volume è fisiologicamente debole
- `_phase_volume_factor` (coach.py) è **costante per fase** (Base 0.85, Build
  1.0, Specifico 1.10, Peak 1.05). Quindi **nessuna progressione settimana-su-
  settimana dentro una fase**: tutte le settimane Base hanno lo stesso volume.
  Un vero sovraccarico progressivo cresce gradualmente (~5-8%/sett) con scarichi
  legati alla fatica, non a "ogni 4ª settimana" fissa.
- Le distanze di seduta sono **frazioni grezze** del target: easy = 10%
  (min 5 km), long = 30% (min 10 km). Su una settimana da 40 km il lungo è
  12 km, l'easy 5 km. La "progressione lungo +2 km/2 sett" è **solo nel prompt
  AI**, assente nel generatore offline.
- **Il volume non torna**: le distanze delle sedute sono costruite indipendenti,
  quindi la loro somma ≠ `target_km`. `target_km` è un'etichetta, non un
  vincolo. Un piano élite ha volumi che tornano.

### 1.2 La distribuzione d'intensità (80/20 / polarizzato) non è garantita
L'app mostra l'80/20 in Home, ma il **generatore non garantisce** che il piano
stesso sia polarizzato. Le sedute di qualità sono assegnate a spanne
(`_quality_for_phase`), senza budget esplicito di tempo-in-zona. Un coach élite
controlla la distribuzione d'intensità deliberatamente.

### 1.3 I passi sono statici e derivati dal tempo-obiettivo (aspirazionale)
`_compute_paces` calcola easy/long/tempo/intervals **una volta** da
livello + goal_time e li applica a **tutte** le settimane. Due errori:
- **Statici**: non progrediscono col migliorare della forma (il passo soglia
  scende durante il blocco). Un piano élite fa progredire i ritmi.
- **Derivati dall'obiettivo, non dalla forma attuale**: prescrive ritmi che
  l'atleta *forse non regge ancora*. I ritmi vanno derivati da **soglia/VO2max
  correnti** (che l'app HA: `metrics.vo2max`, `physiology.lt2_pace`) e fatti
  progredire.

### 1.4 Zero individualizzazione dai dati che l'app già possiede
Il generatore calibra su `level` + `goal_time` + un `baseline_km` da CTL/ATL.
Ma l'app raccoglie: **CTL/ATL/TSB, ACWR, VO2max, LT2 pace, zone HR, storico per
corsa, segnali infortunio, HRV, readiness**. Nulla di tutto ciò entra nella
*struttura* del piano alla generazione. Esempi mancati:
- storico infortuni → dovrebbe limitare intensità/ramp;
- trend HRV basso → ramp più prudente;
- soglia reale → ritmo tempo;
- ACWR → tempistica degli scarichi.
È la lacuna più grave rispetto all'obiettivo ("tarato sulla persona… e ai dati").

### 1.5 Chat e generatore sono due chiamate LLM scollegate
La chat negozia un quadro ricco (fisiologia, vincoli, override, infortuni) →
§CTX§. Ma **solo** week_structure/fixed_sessions/constraints sono enforce-ati
deterministicamente; il **resto** del §CTX§ (weekly_km, threshold_pace,
easy_pace, race_pbs, injuries) è passato come *testo* al generatore e usato
"best effort" — un Haiku può ignorarlo. Il passo easy 5:45 concordato può
essere sovrascritto da `_compute_paces` (derivato da goal_time) se l'AI fallisce
→ offline. Fragile e incoerente.

### 1.6 Piano generato una volta, poi solo "adattato" reattivamente
`adapt_plan_after_sync` ritocca volume/intensità dei **prossimi giorni** da
metriche. Ma il piano è **statico**: non ri-pianifica quando la forma cambia,
quando salti sedute, o quando la gara si avvicina con forma diversa dal previsto.
Un coach élite ri-pianifica di continuo. L'architettura è "genera una volta +
ritocchi locali", non "piano adattivo a orizzonte mobile".

### 1.7 Concetti di coaching mancanti
- **Specificità progressiva** delle qualità (VO2max → soglia → ritmo gara verso
  la fine del blocco): assente.
- **Lunghi specifici gara** (finale a ritmo maratona): il "long" offline è
  sempre lo stesso progressivo easy.
- **Scienza del taper** oltre il −40/50%: il taper offline *toglie* le qualità
  (strides+easy), mentre il taper vero *mantiene l'affilatura* riducendo volume.
- **Scarichi legati all'atleta** (fatica/ACWR accumulati), non "ogni 4ª" fissa.
- **Caldo/altitudine/terreno** ignorati pur avendo meteo + dati trail.
- **Fueling/idratazione lungo e gara** assenti (pur citati in chat).
- **Gare tune-up / B-races** nel blocco: assenti.

### 1.8 La modifica (`move_session`) è swap meccanico, non ribilanciamento
Spostare una seduta scambia due giorni ed emette warning, ma **non ribilancia**
la settimana (i ≥48h tra qualità sono *segnalati*, non risolti; gli easy attorno
non si adattano). Un coach reshape-a, non avvisa soltanto.

### 1.9 "Completato" è un checkbox scollegato dall'esecuzione reale
`toggle_session_complete` è manuale; `evaluate_plan_executions` aggancia le
corse alle sedute e le *scora*. Sono **due verità parallele**. E manca il loop
strutturale: una seduta eseguita troppo forte/piano non reshape-a le
prescrizioni future (solo adattamento locale di volume).

### 1.10 Realismo dell'obiettivo non validato alla generazione
La chat negozia i conflitti, ma il generatore **non** confronta goal_time con la
forma attuale — pur avendo l'app un **race predictor** da VO2max. Prescriverà
ritmi da 3:20 anche se la forma predice 3:50, senza avvisare.

---

# PARTE 2 — Lente architetto: architettura target

### 2.1 Principio guida: separare "spec del piano" (deterministico) da "prosa" (LLM)
Il problema di fondo è una generazione LLM monolitica (un JSON gigante,
inaffidabile, che tronca/allucina) + fallback debole + enforcement bolt-on.
Soluzione: introdurre una **Plan Spec** — rappresentazione intermedia
strutturata — calcolata **deterministicamente** in `app/processing/` da:
- il §CTX§ della chat (week_structure, constraints, fixed_sessions, passi, PB,
  infortuni, override);
- le **metriche reali** (CTL/ATL/TSB, ACWR, VO2max→race prediction, LT2 pace,
  zone HR, infortunio/readiness, trend HRV);
- obiettivo (distanza, data, tempo) e settimane disponibili.

La Spec è lo scheletro periodizzato: per settimana → fase, volume (progressione
liscia + scarichi legati alla fatica), progressione del lungo, prescrizione
qualità (tipo + passo + struttura) con **passi derivati dalla forma corrente e
fatti progredire**, distribuzione d'intensità garantita, scienza del taper.

È un **motore puro e testabile** — il "cervello coaching" — non un LLM. L'LLM si
riduce a: (1) intervista/negoziazione (già buona) e (2) **trasformare ogni
prescrizione strutturata in una bella descrizione** (verbalizzazione, il pattern
A1 già usato altrove). Si **inverte** il design attuale.

Benefici: affidabilità (niente troncamenti/volumi allucinati), correttezza
(fisiologia nel codice, testabile e verificabile da un coach), personalizzazione
(usa tutti i dati), e l'LLM fa ciò in cui è forte (lingua), non aritmetica.

### 2.2 Il piano come sistema vivo, non artefatto one-shot
- Generare la Spec dell'intero blocco, ma **ri-derivare le settimane future** a
  cadenza (settimanale, o dopo cambi di forma / sedute saltate / nuova race
  prediction). Passato immutabile (storia), futuro ri-pianificato dallo stato
  corrente: **orizzonte mobile (rolling horizon)**.
- **Unificare "completato" ed "eseguito"**: la completezza deriva dalle attività
  sincronizzate (execution_service già le aggancia), con override manuale.
  L'esecuzione ri-alimenta lo stato di forma → le settimane future si adattano
  *strutturalmente*, non solo ±volume dei prossimi giorni.

### 2.3 Modello atleta come unica fonte di calibrazione
Un modello `TrainingPaces`/forma derivato dai dati correnti (LT2, VO2max, sforzi
recenti), **progredito** nel blocco. Tutti i passi delle sedute lo referenziano.
Il Digital Twin (`athlete_model_service`, `personal_ramp_factor`) esiste già —
va esteso a contenere soglia corrente, passi-zona, durabilità, e la risposta
appresa al carico.

### 2.4 La seduta come workout strutturato (riuso del Workout Builder)
L'app HA già un builder di workout strutturati (segmenti: riscaldamento/ripetute/
recupero/defaticamento con passi). Le sedute del piano dovrebbero **ESSERE**
workout strutturati (segmenti), non solo titolo+distanza+passo+prosa. Questo dà:
esecuzione precisa, scoring segmento-per-segmento, push-to-watch futuro (con API
Garmin ufficiali) e coerenza con la libreria allenamenti.

### 2.5 Gate di realismo obiettivo
Alla generazione, girare il race predictor esistente sulla forma corrente. Se
goal_time è aggressivo vs predetto, riportarlo (già in parte negoziato in chat)
e annotare il piano con "miglioramento settimanale richiesto" + probabilità →
ri-alimentare la chat prima di confermare.

### 2.6 Modifica che ribilancia, non che avvisa
Move/skip innescano un **ribilanciamento deterministico** della settimana
toccata (rispetto ≥48h qualità, redistribuzione volume) con lo stesso motore
Spec; l'LLM solo ri-verbalizza. "Il coach ha ribilanciato la settimana" invece
di "attenzione: due giorni duri".

### 2.7 Spiegabilità (explainability) di grado-coach
Ogni settimana/seduta annotata col **perché** (intento di fase, quale segnale ha
guidato un adattamento). Il decision engine già verbalizza le note giornaliere:
estenderlo al piano. È trust + didattica.

---

# PARTE 3 — Feature nuove / sostitutive, prioritizzate

| # | Feature | Sostituisce / migliora | Valore | Effort |
|---|---------|------------------------|--------|--------|
| 1 | **Motore di periodizzazione deterministico** (Plan Spec) | generatore LLM monolitico + template offline + enforcement | ⭐⭐⭐⭐⭐ | L |
| 2 | **Passi derivati dalla forma e progressivi** | `_compute_paces` statico | ⭐⭐⭐⭐⭐ | M |
| 3 | **Ri-pianificazione settimanale (rolling)** | genera-una-volta + adapt locale | ⭐⭐⭐⭐ | L |
| 4 | **Sedute = workout strutturati** | title+distanza+passo+prosa | ⭐⭐⭐⭐ | M |
| 5 | **Gate realismo obiettivo + progressione richiesta** | (assente) usa race predictor | ⭐⭐⭐⭐ | S |
| 6 | **Ribilanciatore di settimana sulle modifiche** | swap+warning | ⭐⭐⭐ | M |
| 7 | **Spiegabilità del piano** (perché di ogni scelta) | (assente) | ⭐⭐⭐ | S |
| 8 | **Fueling/idratazione lungo+gara da meteo+distanza** | (assente) | ⭐⭐ | S |
| 9 | **Gare tune-up / B-races nel blocco** | (assente) | ⭐⭐ | M |
| 10 | **What-if sull'intero piano** (deterministico, istantaneo) | what-if parziale | ⭐⭐ | S |

La #1 è il fulcro: da sola risolve 1.1, 1.2, 1.5, gran parte di 1.3/1.4 e rende
tutte le altre facili (il motore è puro e riusabile per adapt, edit, what-if).

---

# PARTE 4 — Percorso di migrazione (incrementale, basso rischio)

Ogni fase è spedibile e testabile; nessun big-bang.

- **Fase A — Motore Spec (cuore)**: nuovo modulo puro
  `app/processing/periodization.py` che produce la Plan Spec da §CTX§ +
  metriche + obiettivo. Il **generatore offline delega ad esso** (sostituisce
  subito i template deboli: deterministico, testabile, volumi che tornano,
  progressione liscia, scarichi legati ad ACWR). Test fisiologici deterministici
  con `ref` fissa (come da convenzioni).
- **Fase B — LLM come verbalizzatore**: il path AI diventa "motore → Spec →
  l'LLM scrive solo le descrizioni per seduta" (pattern A1, injectable
  `call_fn`, fallback template). `enforce_week_structure` diventa ridondante
  (il motore onora già §CTX§) → assorbito.
- **Fase C — Passi dalla forma + gate obiettivo**: `TrainingPaces` da LT2/VO2max
  correnti, progressione nel blocco; race-predictor gate alla generazione e in
  chat.
- **Fase D — Rolling re-plan + esecuzione unificata**: ri-derivazione settimanale
  delle settimane future dallo stato; "completato" guidato dalle attività
  sincronizzate; loop esecuzione→forma→futuro.
- **Fase E — Sedute strutturate + ribilanciatore**: le sedute diventano workout
  a segmenti (riuso builder); move/skip ribilanciano via motore.
- **Fase F — Contorno ad alto tocco**: spiegabilità piano, fueling/heat, B-races,
  what-if completo istantaneo.

### Nota sul modello LLM
Finché l'LLM genera il piano intero, serve almeno Sonnet/Opus per la generazione
(`PLANNER_MODEL`) — Haiku è troppo debole (vedi i bug di passo/volume già visti).
Dopo la Fase B il problema **sparisce**: l'LLM non fa più aritmetica/periodizzazione,
scrive solo prosa, quindi anche Haiku va bene e i costi crollano.

---

## Sintesi
Il singolo cambiamento a più alta leva è **spostare la periodizzazione
dall'LLM a un motore deterministico guidato dai dati reali dell'atleta**,
lasciando all'AI l'intervista e la verbalizzazione. Da lì discendono
affidabilità, personalizzazione vera (tutti i dati), ri-pianificazione viva,
modifiche intelligenti e spiegabilità — cioè il "piano perfetto tarato sulla
persona" che è l'obiettivo.
