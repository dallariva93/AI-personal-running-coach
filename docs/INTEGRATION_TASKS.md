# Integration TODO — cuciture mancanti tra i passi già fatti

Audit trasversale sui Passi 1-13 (+ A3/A9). Elenca le **integrazioni** rimaste
aperte: feature costruite ma non collegate, superfici mancanti, config di
deploy. Diviso in due categorie:

- **[U] Task utente** — richiedono credenziali, deploy o una decisione di
  prodotto. Qui trovi le istruzioni passo-passo.
- **[C] Task Claude** — codice puro. Qui trovi un *prompt da iniettare* pronto
  all'uso (una sessione per task, disciplina come `docs/AGENT_PROMPT.md`).

Priorità: **P0** = feature che l'utente oggi non vedrebbe mai funzionare;
**P1** = miglioria importante; **P2** = tech-debt/coerenza.

---

## Categoria U — solo tu (istruzioni passo-passo)

### U0 · [P1] Deploy backend affidabile senza collegamento manuale ogni volta

**Perché.** Oggi per usare l'app devi collegare a mano il backend e, con lo
scale-to-zero su Fly, il primo accesso dopo l'inattività dava **503** (cold-start
~2 min oltre il grace period dell'healthcheck). Obiettivo: il backend è sempre
raggiungibile e l'app punta all'URL di produzione senza passaggi manuali.

**Fatto (già applicato in `fly.toml`).**
- `min_machines_running = 1` + `auto_stop_machines = "off"`: una macchina resta
  calda → niente più 503 da risveglio.
- `memory = "512mb"`: niente swap-thrash al boot, regge `/api/mobile/overview`.
- `grace_period = "90s"`: un redeploy non genera 503.
- Costo ~$3.32/mese, dentro il buffer gratuito (~$5) di Fly.

**Da fare tu.**
1. Ridistribuisci per applicare la config: installa flyctl
   (`curl -L https://fly.io/install.sh | sh`), poi `fly deploy -a ai-running-coach`.
2. Verifica: `fly status` → 1 macchina `started` a 512MB; l'app deve ricevere
   **200** su `/api/mobile/overview` senza attese.
3. Nell'app Android, imposta il **DEFAULT_BASE_URL** di produzione
   (`https://ai-running-coach.fly.dev/`) come default in Impostazioni, così non
   devi ricollegare il backend a ogni avvio. (Se vuoi che diventi il default
   compilato, è un task [C]: chiedimi di cambiarlo in `android/app/build.gradle.kts`.)

**Aperto (serve il tuo input).** Errore INSERT allo startup nei log Fly (probabile
`POST /api/ingest`): incollami la **prima riga** del traceback (es.
`IntegrityError: ...`) e apro il task di fix.

---

### U1 · [P0] Credenziali FCM/Firebase (push reali, A3 + nudge debrief A4)

**Perché.** Tutta la catena push è inerte senza credenziali: il backend fa
no-op (`fcm_enabled` False) e l'app non riceve nulla via push. Con FCM spento la
notifica "Com'è andata?" (A4) e i trigger (A1) arrivano solo col polling in-app.

**Passi.**
1. **Crea il progetto Firebase.** Vai su <https://console.firebase.google.com> →
   *Add project* → associa il package Android `com.runningcoach.app`.
2. **Scarica `google-services.json`.** In *Project settings → Your apps → Android*
   registra l'app e scarica il file. Mettilo in
   `running-coach-platform/android/app/google-services.json`.
   → è già in `.gitignore` (verificalo): **non** committarlo.
3. **Attiva il plugin Gradle.** In `android/app/build.gradle.kts` assicurati che
   ci sia `id("com.google.gms.google-services")` e in `android/build.gradle.kts`
   il classpath `com.google.gms:google-services`. (Se manca, è un task [C] —
   chiedimi di aggiungerlo.)
4. **Service account backend.** In *Project settings → Service accounts →
   Generate new private key* → ottieni un JSON. Caricalo sul server (NON nel
   repo) e imposta la env `FCM_CREDENTIALS_PATH=/percorso/al/service-account.json`.
5. **Verifica.** `GET /api/health` deve mostrare il progetto attivo; registra un
   device dall'app e controlla che `POST /api/devices` salvi il token. Un evento
   notifiable (es. una decisione) deve arrivare come push.

**Fatto quando:** una corsa sincronizzata fa arrivare "Com'è andata?" come push
e il tap apre il bottom-sheet debrief.

---

### U2 · [P0] Feature flag in produzione (verbalizer A1 + weather Q6)

**Perché.** Sono **off di default** per non toccare la rete nei test/offline. In
prod restano spenti finché non li attivi: la voce LLM e il suggerimento
meteo-finestra non si vedono.

**Passi.**
1. Individua dove passi le env in prod: `render.yaml`, `fly.toml`, o il tuo
   pannello di hosting.
2. Aggiungi:
   - `VERBALIZER_ENABLED=true`  (riscrittura LLM della nota giornaliera, A1)
   - `WEATHER_ENABLED=true`     (weather-window optimizer, Q6)
   - assicurati che `ANTHROPIC_API_KEY` sia impostata (senza, il verbalizer fa
     comunque fallback al template: nessun errore, ma nessuna voce nuova).
3. Ridistribuisci. Verifica su `GET /api/health` che `ai_enabled` sia true.

**Fatto quando:** la nota giornaliera varia di giorno in giorno e, con meteo
avverso, appare l'evento "finestra migliore per correre".

---

### U3 · [P1] Secret CI per i test golden notturni (A9)

**Perché.** I test marcati `eval_llm` (14 note distinte, estrazione debrief,
golden coach) girano solo con una API key e sono `skipif` senza. In CI vanno
eseguiti come job notturno.

**Passi.**
1. GitHub → repo → *Settings → Secrets and variables → Actions → New secret*:
   `ANTHROPIC_API_KEY`.
2. Nel workflow notturno (o crea `.github/workflows/eval-nightly.yml`) esegui
   `pytest -m eval_llm` con `env: ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}`.
   (La creazione del workflow è un task [C]: vedi C-nota in fondo.)
3. Facoltativo: budget/limite di spesa sull'account per i run notturni.

**Fatto quando:** il job notturno gira i golden e fallisce se un prompt regredisce.

---

### U4 · [P1] Decisioni di prodotto (mi servono le tue risposte)

Non sono codice: sono scelte che sbloccano dei task [C]. Rispondi e io procedo.

1. **Cap ramp attivo o hook da rimuovere?** (A5) Oggi il fattore volume di
   `adapt_plan` non supera mai 1.0, quindi il cap ramp personale non ha effetto
   lì. Vuoi (a) rendere il ramp personale realmente operativo sulla progressione
   del volume, oppure (b) tenerlo solo nel prompt di generazione piano e rimuovere
   l'hook morto? → sblocca **C4**.
2. **Serve una schermata Weather su Android?** Il suggerimento meteo-finestra oggi
   è solo una notifica. Vuoi anche una card dedicata? → eventuale nuovo task [C].
3. **"Execution score push" (riga A3) = prompt debrief?** `execution_service` non
   emette un evento notifiable proprio: il nudge post-corsa reale è "Com'è andata?"
   (A4). Confermi che è quello il "push dell'execution score", o vuoi un push
   dedicato col punteggio? → eventuale nuovo task [C].

---

## Categoria C — posso farlo io (prompt da iniettare)

> Ogni prompt è una sessione a sé. Regole comuni (già incluse nei prompt):
> `git pull` sul branch `claude/running-analytics-platform-a017s4`; gate verdi
> prima del commit (`pytest --cov=app --cov-fail-under=80`, `ruff check app tests`,
> e `alembic upgrade head && alembic check` se tocco i modelli); ogni criterio
> coperto da un test; commit + push sul branch designato.

### C1 · [P0] Consumo di `heat_sensitivity` nelle prescrizioni

```text
Collega la heat_sensitivity del Digital Twin (A5) alle prescrizioni di pace, che
oggi la calcolano e persistono ma non la usano mai.

Prima del codice: git pull sul branch corrente; verifica lo stato reale di
app/services/athlete_model_service.py (load_athlete_model / heat_sensitivity),
app/processing/decision.py (dove si formano i target pace) e app/schemas.py
(TrainingMetrics / CoachDecision).

Obiettivo: quando la temperatura prevista/attuale supera i 15°C, il target pace
di una prescrizione easy/long viene ammorbidito di
heat_sensitivity_s_per_c * (temp - 15) secondi/km, con una nota esplicita
("+Ns/km per ~T°C"). Usa il valore personale quando learning=False, altrimenti il
default di popolazione. Mantieni app/processing/ puro: la funzione di
aggiustamento riceve il coefficiente e la temperatura come parametri; il service
(decision_service) legge il twin e la temperatura e li inietta.

Perimetro: NON toccare la stima del twin né altre feature. Se la temperatura del
giorno non è disponibile, no-op (nessun aggiustamento).

Accettazione (test): a 25°C con slope 3 s/km/°C, un target 5:30/km diventa
~6:00/km con nota; a <=15°C nessun cambiamento; twin in learning usa il default.
Gate verdi, commit + push sul branch.
```

### C2 · [P0] `deep_link`/`activity_id` in `NotificationOut` + consegna in-app

```text
Fai sì che il deep-link (A4) sopravviva anche alla consegna in-app (polling), non
solo al push FCM: oggi NotificationOut non porta deep_link/activity_id, quindi il
prompt debrief e l'evento debrief_pain consegnati via overview non aprono il
bottom-sheet.

Prima del codice: git pull; verifica app/schemas.py (NotificationOut),
app/services/event_service.py (pending_notifications, dove si costruisce
NotificationOut da CoachEvent.after) e lato Android data/model/Models.kt
(AppNotification) + il flusso overview→CoachNotifications.post in AppScaffold.kt.

Obiettivo: propaga deep_link e activity_id da CoachEvent.after fino a
NotificationOut e fino ad AppNotification (già ha i campi), così il tap di una
notifica consegnata in-app instrada come quella push. Nessun cambiamento quando
after non contiene deep_link.

Accettazione (test backend): un CoachEvent con after.deep_link="debrief" e
activity_id produce un NotificationOut con quei campi valorizzati; un evento senza
deep_link resta invariato. Android: verifica solo bilanciamento/sintassi/import
(niente SDK), dichiaralo nel report. Gate verdi, commit + push sul branch.
```

### C3 · [P1] Routing deep-link Android generalizzato

```text
Generalizza la gestione dei deep-link in MainActivity: oggi riconosce solo
"debrief" e ignora gli altri (i trigger A1 emettono after.deep_link="coach/today").

Prima del codice: git pull; verifica MainActivity.kt (parseDebrief / EXTRA_*),
CoachNotifications.kt (contentIntent), CoachFirebaseService.kt e la navigazione in
AppScaffold.kt (rotte disponibili, es. "coachlog", Home).

Obiettivo: un deep_link generico instrada alla destinazione giusta —
"debrief" → bottom-sheet (come ora); "coach/today" → schermata Home/Oggi;
sconosciuto → apertura normale senza crash. Mantieni retro-compatibilità col
flusso debrief esistente.

Perimetro: solo Android, solo routing. Nessun SDK in questo ambiente: verifica
bilanciamento graffe/parentesi, import, esistenza rotte/icone, e dichiara nel
report che la build non è stata eseguita (la valida la CI android.yml). Commit +
push sul branch.
```

### C4 · [P1] (dipende da U4.1) Cap ramp personale operativo o hook rimosso

```text
PRE-REQUISITO: la decisione U4.1 in docs/INTEGRATION_TASKS.md (cap ramp attivo
oppure hook da rimuovere). Non partire senza quella risposta.

Se "attivo": fai sì che il ramp personale del Digital Twin (A5) limiti davvero la
progressione settimana-su-settimana del volume nel piano/adattamento, non solo nel
prompt. Se "rimuovi": togli il parametro max_ramp_factor da adapt_plan e la sua
chiamata, lasciando il consumo ramp solo nel prompt di generazione piano.

Prima del codice: git pull; verifica app/processing/adaptive.py (_MAX_FACTOR,
adapt_plan) e app/services/adaptive_plan.py (dove si applica il factor al target
volume). Accettazione con test coerente alla scelta. Gate verdi, commit + push.
```

### C5 · [P1] Schermata Android per il Digital Twin (`GET /api/athlete-model`)

```text
Aggiungi una piccola superficie Android che mostra il Digital Twin (A5): ramp
tolerance, recovery half-life, heat sensitivity, ciascuno con confidence e stato
"learning".

Prima del codice: git pull; l'endpoint GET /api/athlete-model e lo schema
AthleteModel esistono già lato backend. Verifica data/remote/ApiService.kt,
data/repository/CoachRepository.kt, data/model/Models.kt e un pattern di schermata
esistente (es. StatsScreen.kt) da imitare.

Obiettivo: modello dati AthleteModel/AthleteModelEstimate, metodo repository,
e una sezione (in Stats o una schermata dedicata raggiungibile da Opzioni) che
rende i tre valori con etichetta "in apprendimento" quando learning=True.

Perimetro: solo Android. Nessun SDK: verifica sintassi/import/icone/coerenza coi
pattern e dichiara nel report che la build non è stata eseguita. Commit + push.
```

### C6 · [P2] Rimozione/rinomina del modulo morto `athlete_model.py` (fisiologia)

```text
Risolvi la collisione di nome tra il Digital Twin (A5, in
app/processing/digital_twin.py) e il vecchio estimatore di fisiologia
app/processing/athlete_model.py (LT1/LT2/durability/speed reserve).

Prima del codice: git pull; conferma con grep che le funzioni di
app/processing/athlete_model.py (update_athlete_model, estimate_lt2_pace, ecc.)
NON siano importate da nessuna parte (app/ e tests/). Se davvero morto: rimuovi il
file (o, se preferisci conservarlo, rinominalo in physiology_model.py e aggiorna
eventuali riferimenti). Aggiorna il commento in digital_twin.py che cita la
collisione.

Perimetro: nessun cambiamento di comportamento. Gate verdi (la coverage totale
può salire togliendo codice morto). Commit + push sul branch.
```

### C7 · [P2] Refresh del twin anche fuori dal pipeline API

```text
Assicura che il Digital Twin (A5) venga ricalcolato anche quando la sync non passa
dal pipeline HTTP post-sync (es. uso via CLI): oggi maybe_refresh_athlete_model è
invocato solo in app/api/routes.py._adapt_after_change.

Prima del codice: git pull; verifica il punto d'ingresso della CLI/analyze
(python -m app.cli analyze / app/services/ingest.py) e il throttle 1×/giorno già
esistente in athlete_model_service.maybe_refresh_athlete_model.

Obiettivo: chiama maybe_refresh_athlete_model anche nel percorso CLI, best-effort,
senza rompere l'esecuzione senza credenziali. Il throttle evita ricalcoli
ridondanti.

Accettazione (test): dopo un analyze CLI con storia sufficiente, la tabella
athlete_model risulta popolata. Gate verdi, commit + push sul branch.
```

### C8 · [P2] `injury_level high` nella derivazione bad-outcome del ramp (A5)

```text
Completa la derivazione dell'esito negativo per la ramp tolerance (A5): oggi
usa solo readiness-red + execution-collapse; aggiungi injury_level high.

Prima del codice: git pull; verifica app/services/athlete_model_service.py
(_week_observations) e come compute_metrics espone injury_level. Valuta il costo:
ricomputare le metriche per-settimana è pesante — se troppo costoso, documenta un
proxy leggero (es. ACWR alto nella finestra) invece di injury_level pieno.

Accettazione (test): una settimana seguita da injury_level high (o dal proxy)
viene marcata bad_after e quindi esclusa dagli incrementi "assorbiti". Gate verdi,
commit + push sul branch.
```

### Nota C (facoltativa) · workflow CI notturno per gli `eval_llm`

Se vuoi il job notturno di U3 come codice, iniettami:

```text
Crea .github/workflows/eval-nightly.yml che, su schedule notturno e
workflow_dispatch, esegue `pytest -m eval_llm` con
ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}. Deve fallire se un golden
regredisce e non deve girare sui push normali. Verifica lo stile degli altri
workflow in .github/workflows/. Commit + push sul branch.
```

---

## Fuori scope qui (appartengono a passi futuri della roadmap)

- **`debrief_pain` → conversazione infortuni (G6):** l'evento è già emesso; il
  consumo è parte del futuro passo G6, non un'integrazione mancante di A4.
- **"Domanda prima della decisione" nei giorni a confidenza `low`** (retro §5):
  è una nuova feature di prodotto, non una cucitura tra passi esistenti.
- **Health Connect (A2, Passo 14)** e **recap condivisibili (A6, Passo 15):**
  già in coda nella FINAL_ROADMAP.
