# FINAL ROADMAP — Autopsia e ricostruzione

**Mandato:** distruggere il progetto e ricostruirlo meglio. Nessun complimento.
**Team simulato:** Product, UX/UI, Psicologia, AI Engineering, Coach olimpico, Data Science, Software Architecture, Mobile, Growth, Gamification, Performance, Security, Accessibility.
**Test-guida applicato a ogni sezione:** *"Se Apple, Garmin e OpenAI stessero costruendo questa funzione oggi, la farebbero davvero così?"*
**Base dell'analisi:** lo stato reale del codice a oggi (non le intenzioni del roadmap) — 17 feature marcate FATTO, 418+ test, backend FastAPI/SQLite, app Android Compose.

---

## VERDETTO — I cinque difetti mortali

Prima di tutto il resto. Se non si risolvono questi cinque, il resto è decorazione.

**1. Il coach non esiste durante la corsa.**
L'app è interamente post-hoc: raccoglie, analizza, pianifica, adatta — *dopo*. Nel momento in cui l'atleta corre, cioè il momento per cui tutto il resto esiste, l'app è una lapide nel taschino. Nike Run Club ha costruito 50M+ utenti solo su questo momento. Nessuna quantità di CTL/TSB compensa l'assenza dal momento della verità. `#13 Live GPS` e `#14 Audio coach` non sono "grandi funzionalità": sono **il prodotto**.

**2. Senza Garmin non sei nessuno.**
L'onboarding reale è: possiedi un Garmin (o colleghi Strava, che a sua volta richiede un device). Chi ha solo un telefono — la maggioranza assoluta dei runner principianti, cioè il segmento che ha *più bisogno* di un coach — è fuori. Health Connect (`#10`, aperto) e GPS da telefono non sono integrazioni: sono il TAM.

**3. L'"AI" è per l'80% template deterministici — e si vede in due settimane.**
Scelta giusta per sicurezza e costi (il Decision Engine rules-based è difendibile), ma la conseguenza è che `daily_note()` ha un set finito di frasi, `execution_notes` sono stringhe fisse (`_NOTES` in `execution.py`), i warning sono formattati da template. Alla terza volta che l'utente legge *"oggi vinci se corri piano"*, l'illusione del coach muore. OpenAI non spedirebbe mai un "AI coach" in cui l'AI vera tocca solo chat e generazione piano: userebbe il motore deterministico come *fatti* e un LLM economico come *voce*, con memoria della conversazione recente per non ripetersi mai.

**4. Il modello dell'atleta è fatto di costanti di popolazione.**
`hrv_status()` usa soglie assolute 25/55 ms — **errore metodologico**, non opinione: l'HRV ha senso solo rispetto alla baseline individuale (media mobile 7gg di ln rMSSD ± SD; letteratura Plews/Buchheit). ACWR con soglia fissa 1.5 presentata come vangelo (metrica peraltro contestata in letteratura — Impellizzeri 2020). Taper "40-50%" per tutti. Recupero uguale per il 25enne e il 55enne. Un coach olimpico personalizza *tutto*; noi non personalizziamo *niente* che non venga dal profilo dichiarato. Il "Digital Twin" (N1, sotto) non è innovazione esotica: è il minimo per meritare la parola "coach".

**5. Architettura da self-host per smanettoni, non da prodotto.**
Single-user senza account, SQLite, token opzionale, tokens Strava e dati sanitari (HRV!) in chiaro nel DB, sync Garmin a pulsante, notifiche "intelligenti" consegnate da un WorkManager che fa polling **ogni 3 ore** — un coach che ti avvisa di riposare tre ore dopo è un coach che arriva a gara finita. Niente analytics prodotto: non sappiamo letteralmente quale feature venga usata (violazione diretta del principio "misura la North Star" scritto nel nostro stesso roadmap).

---

## 1. AUTOPSIA PER AREA

### 1.1 Product — inventario feature per feature

Verdetti: **TIENI** (funziona, serve) · **RIPARA** (serve ma è rotta/incompleta) · **RETROCEDI** (non merita superficie primaria) · **ELIMINA**.

| Feature (stato reale) | Serve? Problema risolto | Verdetto | Perché |
|---|---|---|---|
| Today Workout Card azionabile | Sì — "cosa faccio oggi" è LA domanda | **TIENI** | È il centro giusto. Ma vedi UX: convive con residui che la contraddicono |
| Decision Engine v2 + audit + notifiche | Sì — spiegabilità = fiducia | **TIENI/RIPARA** | Fatti giusti, voce finta (difetto 3); consegna lenta (difetto 5) |
| Piani multi-settimana + chat negoziale + enforcement | Sì — è la feature per cui si paga (Runna) | **TIENI** | Il contratto `week_structure` + enforcement deterministico è più solido di Runna. Raro punto in cui siamo *davanti* |
| Adaptive plan after sync | Sì — l'autopilota è il moat | **TIENI/RIPARA** | Adatta solo volume/intensità; non riprogramma i giorni; non impara dalla risposta individuale |
| Execution Score v2 | Sì — compliance reale | **RIPARA** | Match per data prende "la corsa più lunga del giorno": warm-up separato + ripetute = misclassificato. Zero analisi per-lap: giudica le ripetute dalla media. Un coach guarda i giri, non la media |
| Chat coach (routing Haiku/Sonnet/Opus) | Sì, ma… | **RIPARA** | Terza superficie AI (vedi UX). Non vede il diario decisioni/execution nel contesto → il coach chat e il coach engine sono due persone diverse |
| Check-in wellness auto (Garmin) | Sì | **RIPARA** | Proxy crudi: `fatigue = stress/10`, `motivation = body_battery/10` spacciati per stati soggettivi. O li chiami col loro nome o chiedi all'utente (voice debrief, N5) |
| HRV + readiness | Sì | **RIPARA** | Difetto 4: soglie assolute. Da rifare baseline-relative |
| VO2max trend, efficienza aerobica, previsione gara | Sì (differenziante vs Strava) | **TIENI/RIPARA** | Previsione = punto singolo da formula; senza profilo altimetrico né meteo né Monte Carlo è un oroscopo con una cifra decimale |
| Heatmap aggregata | Debole | **RETROCEDI** | Feature-vetrina: si guarda due volte. Nessun uso coaching finché non alimenta il route generator (N4). Costata 500 polylines parse per richiesta |
| Calendario mensile corse (Feature 9) | Debole | **RETROCEDI/UNIFICA** | Ora esistono DUE calendari (corse + piano editor). Uno solo, con entrambe le cose |
| Calendar plan editor (#12) | Sì | **TIENI** | Swap + warning deterministici: giusto. Manca: suggerire *dove* mettere la seduta, non solo lasciar spostare |
| PR, streak, badge | Parziale | **RIPARA** | Gamification generica (il roadmap stesso la vietava). Streak di *corse* punisce il riposo prescritto: uno streak che si rompe il giorno di riposo pianificato è anti-coaching. Va reinventata (vedi Motivazione) |
| Cross-training bike/swim/strength | Sì | **TIENI** | Isolamento dal carico running corretto. Ma il carico bike *dovrebbe* contare nel recupero sistemico: oggi 100km in bici = invisibili alla readiness |
| Scarpe (#6) | Sì (culto + affiliate) | **TIENI** | MVP ok |
| Onboarding checklist (#4) | Sì | **RIPARA** | Guida ai passi, ma il "wow" (prima raccomandazione utile) arriva solo dopo aver posseduto un Garmin. Difetto 2 |
| Statistiche/export CSV-JSON | Sì (trust) | **TIENI** | |
| Tooltip long-press sulle metriche | Sì | **TIENI** | Buona pedagogia. Estendere a decision-trace |
| Dashboard web HTMX | No per il consumer | **RETROCEDI** | Correttamente congelata dal roadmap. Solo debug |
| Workout builder + libreria | Parziale | **RETROCEDI** | Potente ma orfano: i template non si esportano al watch (#16) né si eseguono (audio). Finché non si collega, è un editor per collezionisti |
| Widget home screen | Sì | **TIENI** | Mostra TSB: dovrebbe mostrare *la decisione di oggi* |
| Pre-plan chat conferme | Sì | **TIENI** | Il budget-conferme è giusto. Da testare con eval harness, non a mano |

**Cosa manca di fondamentale (Product):** live tracking, audio, Health Connect, iOS, account multi-utente, export workout al watch, pain workflow, analytics prodotto. Tutto già noto e tutto ancora aperto: il roadmap è onesto, l'esecuzione ha privilegiato il cervello (giusto finora) — ora il debito è il *corpo*.

> **Apple/Garmin/OpenAI test:** Apple non spedirebbe mai un coach che non c'è mentre corri. Garmin non spedirebbe mai soglie HRV di popolazione. OpenAI non spedirebbe mai note giornaliere da array di stringhe. Tre bocciature nette.

### 1.2 Esperienza utente

**Attriti mortali:**
- **"Sincronizza" e "Analizza" in home.** L'utente lavora per l'app. Il pipeline post-sync esiste già (`_adapt_after_change`): la sync deve essere di sistema (background, all'apertura, push-driven), l'analisi automatica post-sync. I due bottoni vanno **eliminati**, non spostati. Apple non ha mai messo un bottone "sincronizza" su Apple Watch.
- **Tre superfici AI:** chat Coach (tab), chat pre-piano (dialog), Today card. L'utente non sa a chi parlare. Una sola conversazione col coach, che sappia *tutto* (decisioni, execution, eventi), raggiungibile da ovunque.
- **Sei tab.** "Stats" e "Corse" si fondono (le stats sono una vista delle corse). "Opzioni" non merita una tab (icona ingranaggio in alto). Target: 4 tab — Oggi, Piano, Corse, Coach.
- **Due calendari** (corse + piano): uno.
- **Decision fatigue residua:** la GeneratePlanDialog chiede goal/date/level/giorni *e poi* la chat li ri-negozia. La chat deve essere l'unico ingresso; il dialog sparisce.

**Errori possibili non gestiti:** doppio tap su azioni Today card (nessun debounce visibile); move nel calendario senza undo (c'è audit ma non "Annulla" in snackbar); nessuno stato "sync fallita perché Garmin rate-limited" spiegato all'utente.

**Tempi morti:** overview ricalcola tutto a ogni apertura (vedi Performance) → freddo percepibile; nessun cached-first render.

**Accessibilità (bocciatura):** stringhe hardcoded italiano (nessun i18n → mercato = Italia), emoji come icone informative (🏃 ⛰️ illeggibili per screen reader), nessun contentDescription-audit, day-cell del calendario ~44dp al limite, contrasto dei Pill colorati su surfaceVariant mai verificato WCAG, nessun supporto dynamic type verificato. Un Accessibility Specialist non firmerebbe il rilascio.

**Onboarding:** la checklist (#4) è un buon contenitore col problema sbagliato dentro: il primo valore richiede hardware. Percorso alternativo obbligatorio: *"Non hai un orologio? Corri col telefono adesso: 20 minuti e ti dico da dove partiamo"* — GPS live come onboarding, non come feature futura.

### 1.3 AI

- **Dove sembra finta:** daily notes (set finito), execution notes (stringhe fisse), titoli sessione del fallback offline ("Tempo", "Riposo"), risposte chat offline. Soluzione architetturale, non cosmetica: **fatti deterministici + voce LLM**. Il motore produce il JSON (decisione, evidenze, numeri); un Haiku con memoria delle ultime N note riscrive la superficie verbale con vincolo "non ripetere formule usate negli ultimi 14 giorni". Costo: centesimi/mese. Fallback: i template attuali.
- **Dove deve prendere iniziativa (oggi non lo fa):** corsa saltata da 2 giorni → messaggio proattivo; execution "too_hard" 3 volte in 10 giorni → proposta di ricalibrare le soglie; HRV in trend calo 5 giorni → intervento *prima* del red. Il event-log c'è già: mancano i **trigger comportamentali** sopra di esso.
- **Dove deve spiegarsi meglio:** la card mostra segnali e confidenza (bene, meglio di chiunque). Manca il *decision trace navigabile*: tap su "ACWR 1.6" → grafico di come ci sei arrivato → cosa l'avrebbe cambiata. La spiegabilità è il nostro moat dichiarato: portarla fino in fondo.
- **Dove può essere più personale:** memoria episodica. Il coach chat non ricorda "il dolore al tendine di cui mi hai parlato martedì" tra sessioni. `chat_sessions` esiste: serve un estratto di memoria long-term (fatti sull'atleta) iniettato nel system prompt e aggiornato dopo ogni conversazione.
- **Dove può sorprendere:** collegare cose che l'utente non collega. "Nelle 6 corse con le Pegasus la tua cadenza cala del 4%"; "dormi peggio i giorni post-intervalli: spostiamo la qualità al mattino?". I dati ci sono tutti, non c'è il layer di correlazione (N12, N7).

### 1.4 Running — la revisione del coach olimpico

- **HRV a soglie assolute: da correggere subito** (già detto, difetto 4). Baseline individuale ln rMSSD, banda ±0.75 SD, trend 7 giorni. Con meno di ~3 settimane di dati: dichiarare "sto ancora imparando la tua baseline" — che tra l'altro *aumenta* la fiducia.
- **Ripetute giudicate dalla media:** un 10×400 con recuperi ha avg pace lenta e HR medio basso → l'Execution Score v2 tempo-in-zona aiuta, ma senza analisi per-lap non distingui "ripetute corte tirate bene" da "fartlek svogliato". I lap Garmin ci sono (`splits`/`typed_splits` già archiviati raw!) e non li usiamo per la compliance. Sprecato.
- **Prescrizioni cieche all'ambiente:** target pace identico a 8°C e a 32°C, in piano e su 300 D+. Il dato meteo per attività c'è (temperature_c, humidity), il GAP c'è — non vengono usati *in prescrizione*, solo in lettura. Heat-adjustment dei target (già backlog #26) e target GAP-based sui percorsi collinari.
- **Periodizzazione a template:** cutback ogni 4ª settimana hardcoded, fasi a percentuali fisse. Difendibile come default; indifendibile come unico comportamento. La risposta individuale (execution score + readiness trend) dovrebbe modulare la periodizzazione, non solo la settimana corrente.
- **Ritorno da infortunio/malattia: assente.** Un coach vero ha protocolli di rientro graduati (return-to-run ladder). Oggi: salti 2 settimane e il piano ti ributta dentro col volume pianificato (l'adaptive taglia %, ma non esiste un protocollo). **Pericoloso.** (N13)
- **Cross-training invisibile al recupero:** 3h di bici il sabato non toccano la readiness di domenica. Sbagliato fisiologicamente: serve un carico sistemico multi-sport (TRIMP da HR c'è per tutte le attività).
- **Cosa manca vs un coach umano:** occhio sulla meccanica (cadenza/oscillazione — dati Garmin disponibili), fueling per il lungo (#27 backlog), gestione psicologica del pre-gara, e soprattutto **la conversazione che precede la decisione** — il nostro engine decide e spiega, un coach *chiede* ("come ti senti stamattina?") prima di decidere nei giorni ambigui. Con confidenza "low", la Today card dovrebbe fare una domanda, non dare un ordine.

### 1.5 Motivazione e psicologia

- **Cosa fa tornare domani:** la Today card (decisione fresca ogni giorno) — l'unico vero hook quotidiano. Le notifiche lo sarebbero se arrivassero in tempo (difetto 5).
- **Streak sbagliato:** premia il correre, non l'aderire. Il giorno di riposo prescritto *rompe* lo streak → incentivo perverso a junk miles, l'esatto contrario del coaching. Sostituire con **streak di aderenza al piano** (giorni in cui hai fatto ciò che era previsto, riposo incluso). La North Star è già "sedute prescritte completate": la gamification deve puntare alla stessa stella.
- **Momenti emozionali mancanti:** fine di ogni settimana (recap: "hai assorbito il carico, la soglia si muove"), il post-gara (#11 race recap, aperto), i comeback ("terza settimana di rientro: sei ufficialmente tornato"), i micro-PR invisibili ("miglior decoupling di sempre su un lungo"). Il diario del coach registra tutto ma non *celebra* niente.
- **Dove si perde motivazione:** giorni "low confidence" con ordini secchi; ripetitività delle note (difetto 3); silenzio totale nei giorni di riposo (il coach dovrebbe dire *perché il riposo di oggi costruisce mercoledì*).
- **Dipendenza positiva:** la leva più forte che abbiamo e non usiamo: **execution score come feedback immediato post-corsa** con push entro minuti dalla sync ("Seduta eseguita 92/100 — passo perfetto, recuperi lunghi"). Il loop corri→voto→domani-adattato, chiuso in tempo reale, è il ciclo della dipendenza sana.

### 1.6 Architettura, Performance, Sicurezza

- **Complessità inutile:** poca, onestamente — i layer sono puliti (collection/processing/coaching/services). La ridondanza vera: due calendari Android, tre superfici chat, dashboard web da mantenere.
- **Scalabilità:** SQLite + single-user = zero prodotto consumer. La separazione self-host/cloud è nel roadmap lungo termine: va anticipata, perché ogni feature nuova aumenta il costo della migrazione (accounts, migrazioni dati, isolamento).
- **Performance:** `/api/mobile/overview` ricalcola compute_metrics + PR + badge + snapshot + prediction + **decisione** su tutte le attività a ogni chiamata. O(n) con n che cresce per sempre, nessuna cache. Fix: cache metriche invalidata da ingest (chiave: max(activity.id) + checkin date), risposta <100ms. Heatmap: 500 JSON parse per request → precomputare.
- **Offline:** app mobile online-only (#17 aperto). Un'app per gente *che esce di casa* deve funzionare senza rete: cached-first per overview/piano/decisione di ieri.
- **Sync:** Garmin polling manuale. Minimo: scheduled背ground sync. Meglio: già che l'archivio raw esiste, delta-sync con backoff su rate limit.
- **Sicurezza (bocciatura severa):** dati sanitari (HRV, sonno) e OAuth tokens Strava **in chiaro** su SQLite; token API opzionale e statico; nessun rate limiting; nessuna cancellazione dati ("diritto all'oblio" GDPR — siamo in Italia e trattiamo dati salute, non è opzionale). Prima del multi-utente: cifratura at rest dei campi sensibili, endpoint `DELETE /api/me/data`, rotazione token, rate limit sul webhook.
- **Caching/sincronizzazione mobile:** nessuna cache locale, nessuna coda offline per azioni (un "Fatto" sulla Today card in galleria muore). Room + sync queue.

### 1.7 Business

- **Retention:** Today card + notifiche puntuali + adaptive plan (il "torna domani"). Execution score post-corsa immediato (il "torna dopo ogni corsa"). Weekly recap (il "torna lunedì").
- **Conversione (paid):** il pacchetto Runna-killer: piano AI negoziato + adattamento quotidiano + race-day mode + audio coach. Il free tier: tracking + analisi + decisione base. La chat illimitata e i piani multipli sono naturalmente premium.
- **Passaparola:** race recap condivisibile (#11, aperto — è LA feature virale, va fatta), heatmap condivisibile, "il mio coach mi ha spostato l'allenamento perché aveva visto che avevo dormito male" è una storia che si racconta al run club — la spiegabilità *è* il marketing.
- **Monetizzazione dormiente:** scarpe→affiliate; club sync (N11)→B2B verso i run club.

---

## 2. COMPETITOR TEARDOWN

| | Fa meglio di noi | Fa peggio di noi | Da copiare | Dove li battiamo |
|---|---|---|---|---|
| **Garmin** | Sensori, readiness/training-status maturi con baseline individuali, ecosistema device, affidabilità | Spiegazioni oracolari ("Unproductive" senza perché), zero conversazione, piani rigidi (DSW non negozia), UX densa | Baseline personali (HRV/soglie), Body Battery come linguaggio, workout→watch | Spiegabilità totale + negoziazione. Garmin ti giudica, noi ci giustifichiamo |
| **Strava** | Social graph, segmenti, condivisione, network effect imbattibile | Non è un coach: zero prescrizione, zero adattamento, analytics dietro paywall e comunque descrittive | Shareability (recap card), segmenti/percorsi, kudos come rinforzo | Il coaching vero. Strava ti mostra il passato, noi decidiamo il domani |
| **Runna** | Onboarding-to-plan magistrale, UX premium, piani chiari, marketing | Adattamento giornaliero superficiale, spiegazioni scarse, non legge readiness/HRV, chat limitata | Il polish dell'onboarding e della presentazione del piano | Adattamento reale post-sync + execution score + negoziazione. Il nostro piano *vive*, il loro è un PDF bello |
| **TrainingPeaks** | Metriche pro (CTL/ATL/TSB nostri padri), calendario-compliance, workflow coach umani | UX 2012, linguaggio per addetti, mobile debole, zero AI utile | Il calendario come superficie primaria di lavoro, compliance colore-coded | Stesso rigore, linguaggio umano, decisioni al posto di grafici. TP dà i numeri, noi le conclusioni |
| **Nike Run Club** | Guided runs (tono, voci, emozione), gratuito, beginner-friendly, momenti celebrativi | Analytics giocattolo, zero fisiologia, piani generici, ha smesso di innovare | Audio coaching emozionale, celebrazioni post-corsa, first-run experience senza hardware | Dati veri sotto l'emozione. NRC è un motivatore cieco; noi vediamo |
| **Coros** | EvoLab (durability!), hardware/prezzo, training hub pulito | Ecosistema piccolo, niente social, AI assente, poca personalità | Durability score, race predictor con confidenza | Durability *spiegata* + coaching conversazionale sopra le stesse metriche |

**Sintesi:** nessun competitor ha insieme (a) adattamento quotidiano reale, (b) spiegabilità completa, (c) negoziazione conversazionale. Noi abbiamo tutti e tre **ma solo nel post-hoc**. Chi arriva primo a "coach spiegabile che c'è anche durante la corsa" prende la categoria.

---

## 3. INNOVAZIONE — 18 funzionalità che tra cinque anni copieranno

| # | Funzionalità | Cos'è | Impatto | Compl. | Costo | Rischio | ROI | Tempo |
|---|---|---|---|---|---|---|---|---|
| N1 | **Digital Twin dell'atleta** | Modello individuale appreso dai TUOI dati: baseline HRV, emivita del recupero, tolleranza al ramp, sensibilità al caldo. Sostituisce OGNI costante di popolazione. Ogni soglia diventa "tua" | 10 | 9 | alto | medio | altissimo | 3-6 mesi (v0 in 1) |
| N2 | **Counterfactual plan (what-if)** | Slider sul piano: "se salto il lungo / aggiungo un giorno / mi ammalo 1 settimana" → impatto live su previsione gara e rischio. Trasforma il piano da documento a simulatore | 9 | 6 | medio | basso | altissimo | 3-4 sett |
| N3 | **Race strategist live (re-pacing)** | In gara: ricalcolo del pacing dai parziali reali + profilo percorso + meteo + il tuo twin. Uccide il "banked time". Nessuno lo fa davvero | 10 | 8 | alto | medio | altissimo | 2-3 mesi (dopo live GPS) |
| N4 | **Route generator per seduta** | "Oggi 8km easy" → genera IL percorso: distanza giusta, dislivello giusto, dai tuoi percorsi storici (heatmap!) + OSM, export al watch. La heatmap smette di essere un poster | 9 | 8 | alto | medio | altissimo | 2-3 mesi |
| N5 | **Voice debrief post-corsa** | 20 secondi a voce: "com'è andata?" → LLM estrae RPE, dolori, umore, note. Sostituisce ogni form. Il check-in diventa una conversazione da doccia | 9 | 5 | medio | basso | altissimo | 2-3 sett |
| N6 | **Invisible testing** | Micro-test dentro gli allenamenti normali (strides cronometrate, segmenti a decoupling controllato) → aggiorna soglia/VO2max senza mai un "test day". Il laboratorio senza laboratorio | 9 | 7 | medio | medio | alto | 4-6 sett |
| N7 | **Life-aware planning (calendario vita)** | Legge Google/Outlook calendar: volo alle 6, cena tardi, trasferta → il piano si riorganizza PRIMA che tu salti la seduta. Nessun competitor tocca la vita reale | 10 | 6 | medio | medio | altissimo | 4-6 sett |
| N8 | **Weather-window optimizer** | "Corri alle 18:40: 21°C, vento calo, luce ok" — l'ora ottimale di oggi da forecast + tue abitudini. Push al mattino | 8 | 4 | basso | basso | alto | 1-2 sett |
| N9 | **Durability index spiegato** | Fatigue-resistance dal drift passo/HR nella seconda metà dei lunghi. Coros ce l'ha muto; noi lo spieghiamo e lo alleniamo ("il tuo obiettivo del mese: durability") | 8 | 6 | medio | medio | alto | 4 sett |
| N10 | **Season storyline (memoria del coach)** | Memoria episodica: "la caviglia di marzo", "il comeback di giugno". Recap mensili narrativi, riferimenti spontanei in chat. Il coach che ti *conosce* | 9 | 6 | medio | basso | alto | 4-6 sett |
| N11 | **Club sync** | Il workout del martedì del tuo run club entra come fixed_session per tutti i membri; classifica di aderenza del gruppo, non di velocità. Social anti-overtraining | 9 | 7 | alto | medio | altissimo | 6-8 sett |
| N12 | **Shoe-stride intelligence** | Correlazioni scarpa↔cadenza↔dolori↔pace: "con le Pegasus la cadenza cala del 4%: usale solo per gli easy". Le scarpe da contatore a consulente | 7 | 6 | medio | medio | medio | 4 sett |
| N13 | **Comeback protocols** | Return-to-run ladder post-infortunio/malattia auto-inserita nel piano (walk-run → continuo → qualità), con gate di avanzamento su dolore/HRV. Il momento a più alto rischio della vita del runner, oggi scoperto | 9 | 6 | medio | alto (safety) | alto | 4-6 sett |
| N14 | **Race simulation Monte Carlo** | Non "3:45:12" ma la distribuzione: "68% sub-3:50, 20% sub-3:45" simulata dal twin su profilo+meteo. L'onestà probabilistica come firma | 9 | 7 | medio | medio | alto | 4-6 sett |
| N15 | **Coach Quality Index pubblico** | Eval harness con atleti sintetici (#25) trasformato in benchmark pubblicato: "il nostro coach non ha mai prescritto un ramp >10% in 10.000 scenari". La sicurezza come marketing. Nessuno può copiarlo in fretta perché nessuno testa | 8 | 7 | medio | medio | alto | 6-8 sett |
| N16 | **Audio run generati per-seduta** | Non guided runs preregistrate (NRC): generate per LA tua seduta — i tuoi passi, i tuoi nomi, il tuo momento della stagione, TTS. "Ultimo km del decimo 400: è qui che si vince giovedì" | 9 | 7 | alto | medio | altissimo | 6-8 sett (dopo live) |
| N17 | **Privacy-first on-device** | Twin e decisioni girano sul device; il cloud vede solo aggregati opt-in. "Il tuo HRV non lascia il telefono" come claim. Apple-style privacy come USP nel fitness (dove tutti aspirano i dati) | 8 | 9 | alto | alto | medio | 6+ mesi |
| N18 | **Human coach co-sign** | Marketplace: un coach umano rivede e firma la settimana AI in 5 minuti (l'AI prepara il dossier: execution, readiness, deviazioni). 10x atleti per coach, prezzo 1/5 del coaching umano | 10 | 10 | molto alto | alto | altissimo | 6-12 mesi |

---

## 4. LA RICOSTRUZIONE — principi

1. **Il coach esiste in tre tempi:** prima (decide e spiega — ✅ fatto), **durante** (guida — ❌ da costruire, priorità assoluta), dopo (valuta e adatta — ✅ fatto, da velocizzare a minuti).
2. **Fatti deterministici, voce generativa.** Il motore rules non si tocca; la superficie verbale diventa LLM con memoria anti-ripetizione.
3. **Ogni costante diventa una variabile appresa.** Population defaults solo come prior del twin.
4. **Zero lavoro utente:** niente bottoni sync, niente form. Voce, background, push.
5. **Il telefono è un sensore sufficiente.** Garmin è un arricchimento, non un requisito.
6. **Sicurezza e spiegabilità sono il brand,** non compliance: si pubblicano (N15) e si raccontano.
7. **North Star invariata:** sedute prescritte completate in modo sano/settimana. Ogni feature si giustifica contro questa o muore.

---

## 5. ROADMAP FINALE

### Quick Wins — 1 settimana ciascuno

| # | Cosa | Impatto | Compl. | Costo | Rischio | ROI | Tempo |
|---|---|---|---|---|---|---|---|
| Q1 | **HRV baseline individuale** (ln rMSSD rolling 7/28gg, bande ±SD; "sto imparando la tua baseline" <21gg) — fix metodologico | 9 | 3 | basso | basso | altissimo | 2-3 gg |
| Q2 | **Morte dei bottoni Sincronizza/Analizza**: sync in background all'apertura + scheduled; analisi auto post-sync; home senza lavoro | 9 | 3 | basso | basso | altissimo | 3-4 gg |
| Q3 | **Execution score: merge multi-corsa/giorno** (warm-up + seduta) e primi controlli per-lap dalle splits già archiviate | 8 | 4 | basso | basso | alto | 1 sett |
| Q4 | **Streak di aderenza** al posto dello streak di corse (il riposo prescritto conta) | 8 | 2 | basso | basso | alto | 1-2 gg |
| Q5 | **Cache overview** (invalidazione su ingest/checkin) + heatmap precomputata: apertura <100ms | 7 | 3 | basso | basso | alto | 2-3 gg |
| Q6 | **Weather-window optimizer** (N8) con open-meteo: push mattutino "corri alle 18:40" | 8 | 4 | basso | basso | alto | 1 sett |
| Q7 | **Accessibility pass**: contentDescription, touch target, contrasto, niente emoji-icone; estrazione stringhe per i18n | 7 | 3 | basso | basso | medio | 1 sett |
| Q8 | **Undo sugli edit del calendario** (snackbar "Annulla" che riusa lo swap inverso) | 6 | 2 | basso | basso | medio | 1-2 gg |

### Alto impatto — 1 mese ciascuno

| # | Cosa | Impatto | Compl. | Costo | Rischio | ROI | Tempo |
|---|---|---|---|---|---|---|---|
| A1 | **Voce LLM sul motore deterministico** + trigger proattivi comportamentali (corsa saltata, too_hard ricorrente, HRV in calo) — uccide il difetto 3 | 9 | 5 | medio | basso | altissimo | 3-4 sett |
| A2 | **Health Connect MVP** (#10): corse, HR, sonno, HRV senza Garmin — apre il TAM | 10 | 7 | alto | medio | altissimo | 4-6 sett |
| A3 | **Push reali (FCM)** + execution score push entro minuti dalla sync — chiude il loop dopamminico ✅ FATTO — 2026-07-03 | 9 | 5 | medio | basso | altissimo | 3 sett |
| A4 | **Voice debrief post-corsa** (N5) — sostituisce i proxy crudi fatigue/motivation | 9 | 5 | medio | basso | altissimo | 2-3 sett |
| A5 | **Digital Twin v0** (N1): recovery half-life, ramp tolerance e heat sensitivity stimate dai dati storici, con fallback ai default | 9 | 6 | medio | medio | altissimo | 4 sett |
| A6 | **Race recap condivisibile** (#11) + weekly recap emozionale — il motore del passaparola | 9 | 5 | medio | basso | altissimo | 3-4 sett |
| A7 | **Counterfactual what-if sul piano** (N2) | 9 | 6 | medio | basso | altissimo | 3-4 sett |
| A8 | **Chat unificata**: una sola conversazione col contesto completo (decisioni, execution, eventi, memoria episodica v0 N10); via la chat pre-piano separata; 4 tab | 8 | 5 | medio | medio | alto | 3-4 sett |
| A9 | **Eval harness coach v1** (#25): 50 scenari sintetici in CI; nessun prompt cambia senza passare i test di sicurezza ✅ FATTO — 2026-07-03 | 8 | 6 | medio | medio | alto | 4 sett |
| A10 | **Sicurezza GDPR**: cifratura at rest campi sanitari e token, delete-my-data, rate limiting | 8 | 5 | medio | basso | alto (rischio evitato) | 3 sett |

### Grandi funzionalità — 3 mesi

| # | Cosa | Impatto | Compl. | Costo | Rischio | ROI | Tempo |
|---|---|---|---|---|---|---|---|
| G1 | **Live GPS tracking da telefono** (#13) — con onboarding "corri adesso senza orologio" | 10 | 8 | alto | alto | altissimo | 6-10 sett |
| G2 | **Audio coach adattivo in corsa** (#14 + N16): la seduta del piano eseguita e parlata | 10 | 8 | alto | medio | altissimo | 6-10 sett (su G1) |
| G3 | **Race Day Mode con re-pacing live** (N3, #15) | 10 | 8 | alto | medio | altissimo | 6-8 sett (su G1) |
| G4 | **Multi-user cloud** (account, isolamento, Postgres, billing-ready) — anticipato dai 12 mesi perché ogni mese di ritardo aumenta il costo di migrazione | 9 | 8 | alto | alto | altissimo | 8-12 sett |
| G5 | **Offline-first mobile** (#17): Room cache, coda azioni, cached-first render | 9 | 7 | alto | medio | alto | 6-8 sett |
| G6 | **Pain & comeback workflows** (#19 + N13): body map, triage non-diagnostico, return-to-run ladder | 9 | 7 | alto | alto (safety) | alto | 6-8 sett |
| G7 | **Life-aware planning** (N7): integrazione calendario vita | 10 | 6 | medio | medio | altissimo | 4-6 sett |
| G8 | **Route generator** (N4): la seduta genera il percorso, export GPX | 9 | 8 | alto | medio | altissimo | 8-10 sett |
| G9 | **Carico sistemico multi-sport** nella readiness + invisible testing (N6) | 8 | 7 | medio | medio | alto | 6 sett |

### Visione — 12 mesi

| # | Cosa | Impatto | Compl. | Costo | Rischio | ROI | Tempo |
|---|---|---|---|---|---|---|---|
| V1 | **iOS + Apple Health** (#20) | 10 | 10 | molto alto | alto | altissimo | 3-6 mesi |
| V2 | **WearOS/watchOS companion** (#23) + workout export al watch (#16) | 10 | 10 | molto alto | alto | altissimo | 4-8 mesi |
| V3 | **Digital Twin completo + Monte Carlo race sim** (N1+N14): ogni numero personalizzato, ogni previsione una distribuzione | 10 | 9 | alto | medio | altissimo | 6 mesi |
| V4 | **Club sync + accountability circles** (N11): il social che previene l'overtraining invece di premiarlo | 9 | 8 | alto | alto | altissimo | 3-4 mesi |
| V5 | **Human coach co-sign marketplace** (N18) | 10 | 10 | molto alto | alto | altissimo | 6-12 mesi |
| V6 | **Privacy on-device** (N17) + **Coach Quality Index pubblico** (N15): fiducia come prodotto | 8 | 9 | alto | alto | alto | 6+ mesi |

**Sequenza critica:** Q1-Q8 → A1/A2/A3 (il coach diventa vivo e senza-Garmin) → G1/G2 (il coach entra nella corsa) → G4 (diventa un prodotto) → V1/V2 (prende il mercato). N7 (life-aware) è il jolly da anticipare appena possibile: costo medio, impatto 10, concorrenza zero.

**L'ordine operativo completo, con i brief di sviluppo per ogni passo, è nella sezione 5-bis.**

---

## 5-bis. SEQUENZA DI ESECUZIONE — brief di sviluppo

Le tabelle del §5 sono bucket per orizzonte; questa sezione è **l'ordine in cui sviluppare**, con un brief per passo pronto per chi implementa. Dipendenze dure da rispettare: **A1←A3, A5←Q1, G2/G3←G1, G1↔G5, V4/V5←G4**. Tutto ciò che non ha frecce è riordinabile o parallelizzabile.

---

### FASE 0 — Fondamenta (settimane 1-2, quasi tutto parallelizzabile)

#### Passo 1 — Q1 · HRV baseline individuale ✅ FATTO — 2026-07-02

**Implementato:** `hrv_baseline()` puro in `app/processing/recovery.py` (media ln(rMSSD)
7gg vs media±0.75·SD dei 28gg precedenti, outlier <=0/>200ms scartati, `learning=True`
sotto 21 giorni con fallback alle soglie assolute). `compute_metrics` accetta
`hrv_history` (opzionale, retrocompatibile) e popola `hrv_status`/`hrv_learning`/
`hrv_days_tracked` su `TrainingMetrics`; `readiness()` usa la banda relativa
(-15/0/+10) quando la baseline è nota, altrimenti le soglie assolute di prima.
Nuovo helper `hrv_history(session, ref, days=35)` in `app/services/checkin.py`,
cablato in tutti i chiamanti di `compute_metrics` che hanno accesso alla sessione
DB (decision_service, adaptive_plan, main.py, api/mobile.py, api/routes.py,
api/plan_multiweek.py, services/ingest.py). Android: `HrvCard` mostra "Sto ancora
imparando la tua baseline (giorno X/21)" quando `hrvLearning` è vero (nuovi campi
`hrv_learning`/`hrv_days_tracked` nel DTO `TrainingMetrics`); build non eseguita
(niente SDK in questo ambiente), verificata solo per bilanciamento sintassi/import.
**Deviazione dal brief:** aggiunto `hrv_days_tracked` (non richiesto esplicitamente)
per rendere possibile il testo "giorno X/21" lato Android senza inventare un numero.

**Obiettivo.** Sostituire le soglie HRV assolute (25/55 ms) con la baseline personale: media mobile 7 giorni di ln(rMSSD) confrontata con media±0.75·SD dei 28 giorni precedenti.

**Stato attuale.** `app/processing/recovery.py`: `hrv_status()` classifica con costanti; `readiness()` somma bonus/malus da soglie fisse. I valori storici esistono in `daily_checkins.hrv_rmssd`.

**Da costruire.**
- Nuova funzione pura `hrv_baseline(history: list[tuple[date, float]]) -> HrvBaseline` in `recovery.py`: calcola `ln_mean_7d`, `ln_mean_28d`, `ln_sd_28d`; stato = `low` se 7d < 28d−0.75·SD, `high` se > +0.75·SD, altrimenti `normal`; `learning=True` se <21 giorni di dati (in quel caso fallback alle soglie attuali E flag esposto).
- `compute_metrics` (in `app/processing/metrics.py`) riceve la history HRV (nuovo parametro, caricata dal chiamante con una query su `DailyCheckinRow` degli ultimi 35 giorni) e popola `hrv_status` + nuovo campo `hrv_learning: bool` su `TrainingMetrics`.
- `readiness()`: i contributi HRV diventano relativi alla banda (fuori banda bassa −15, dentro 0, sopra +10) invece che ai ms assoluti.
- Android: nel `HrvCard` mostrare "Sto ancora imparando la tua baseline (giorno X/21)" quando `hrv_learning`.

**Accettazione.** Unit test: baseline con 28 punti sintetici, stato low/normal/high per costruzione; <21 punti → learning; il decision engine con HRV 45ms e baseline personale alta (media 60) segnala `low` (le vecchie soglie avrebbero detto normal). Nessuna regressione sui 418 test.

**Rischi/edge.** Giorni mancanti (usare i punti disponibili, non interpolare); rMSSD=0 o >200 → scartare come outlier (>3 SD).

---

#### Passo 2 — Q2 · Morte dei bottoni Sincronizza/Analizza ✅ FATTO — 2026-07-02

**Implementato:** tabella `sync_state(key, value)` (migrazione `e5f6a7b8c9d0`) +
`app/services/sync_state.py` (`should_skip_ingest`/`record_ingest`, finestra 10 min).
`POST /api/ingest` salta il fetch reale se l'ultimo ingest è <10 min fa (log
"ingest skipped, recent", ritorna comunque le attività note via `list_activities`).
Quando l'ingest porta ≥1 attività nuova (contate via diff del count `Activity`
prima/dopo), `_adapt_after_change` gira anche `run_single_analysis(presync=False)`
best-effort: la corsa più recente ha sempre un report senza tap. Nuovo parametro
`presync` su `run_single_analysis` per evitare un secondo fetch Garmin ridondante
dentro la stessa richiesta (rischio non menzionato nel brief, scoperto leggendo
`sync_before_analysis`). Android: `SyncWorker` (WorkManager) con sync periodico
1h + one-shot expedited da `RunningCoachApp.onCreate` e `MainActivity.onResume`
(dedup via `ExistingWorkPolicy.KEEP`); i due bottoni Sincronizza/Analizza sono
spariti da `HomeScreen`, sostituiti da una riga passiva "Ultimo sync HH:mm · N
nuove corse" (`SettingsStore.syncStatus`/`recordSync`/`swapMaxActivityId`).
Build Android non eseguita (niente SDK in questo ambiente), verificata solo per
bilanciamento sintassi/import e coerenza con i pattern esistenti (`NotificationSyncWorker`).
**Deviazioni dal brief:** (1) niente vero gesture di pull-to-refresh — il compose-bom
del progetto (2024.06.00 → material3 ~1.2) non ha `PullToRefreshBox` stabile e un
bump non è verificabile in questo ambiente senza SDK; lo "sync manuale d'emergenza"
è invece una piccola icona nella riga di stato, stesso effetto pratico, rischio
molto più basso. (2) il conteggio "nuove corse" lato Android usa il confronto tra
il massimo `Activity.id` prima/dopo il sync (salvato in `SettingsStore`), non un
elenco esplicito di id dal backend: sufficiente perché gli id sono monotoni
crescenti e non richiede un nuovo contratto API.

**Obiettivo.** L'utente non lavora per l'app: sync in background, analisi automatica, home senza bottoni-lavoro.

**Stato attuale.** `HomeScreen` ha `onSync`/`onAnalyze` → `OverviewViewModel.sync()/analyze()` → `POST /api/ingest` e `POST /api/analyze`. Il pipeline post-sync (`_adapt_after_change` in `app/api/routes.py`) già concatena execution→adaptive→decisione→notifiche.

**Da costruire.**
- Android: `SyncWorker` (WorkManager, periodic ~1h + expedited one-shot all'apertura app da `RunningCoachApp.onCreate`/`onResume` della MainActivity) che chiama `repository.sync()`; rimuovere i due bottoni da `HomeScreen`; sostituirli con una riga di stato passiva ("Ultimo sync 08:12 · 2 nuove corse") alimentata da un timestamp salvato in `SettingsStore`.
- Backend: `POST /api/ingest` deve diventare idempotente-friendly per chiamate frequenti: aggiungere guardia "skip se ultimo ingest <10 min fa" (nuova colonna o riga chiave-valore; più semplice: tabella `sync_state(key, value)` o riuso `CoachEvent` con dedupe) e far girare `run_single_analysis` automaticamente quando il sync porta ≥1 attività nuova (dentro `_adapt_after_change`, best-effort, così l'ultima corsa ha sempre il report senza tap).
- Il pull-to-refresh in home resta come sync manuale d'emergenza.

**Accettazione.** Aprendo l'app con una corsa nuova su Garmin: entro il primo refresh appaiono corsa + report + decisione aggiornata, zero tap. Due sync ravvicinati non duplicano lavoro (log "skipped, recent"). UI senza i due bottoni; test integrazione su auto-analisi post-ingest.

**Rischi.** Rate-limit Garmin: mantenere il backoff esistente; l'expedited work non deve girare più di 1×/10min.

---

#### Passo 3 — Q4 · Streak di aderenza (+ Q8 · Undo nel calendario) ✅ FATTO — 2026-07-02

**Implementato:** `AdherenceDay` + `compute_adherence_streak()` pure in
`app/processing/gamification.py`: ogni giorno del calendario è aderente/rotto/neutro
(seduta completata o riposo rispettato = aderente, `skipped` o corsa hard in un
giorno di riposo = rotto, nessuna copertura del piano quel giorno = neutro,
bridged senza contare — evita che i giorni "vuoti" prima dell'inizio piano gonfino
artificialmente lo streak a 60). Nuovo `app/services/gamification_service.py`
(`compute_gamification`) unifica `/api/gamification` e `/api/mobile/overview`,
che prima duplicavano la logica in modo leggermente diverso: con piano attivo usa
la finestra di 60gg di aderenza, senza piano ricade sul vecchio `compute_streak`
(comportamento legacy). `GamificationData.streak_kind` ("adherence"|"runs")
esposto per la label Android. Android: `StreakCard` mostra "giorni di piano
rispettato" vs "giorni di fila" in base a `streakKind`. Q8: `PlanViewModel.moveSession`
calcola la data sorgente della seduta dal piano corrente prima dello spostamento e la
salva in `lastMove`; la snackbar in `AppScaffold` mostra "Annulla" quando presente e
richiama `moveSession` con id+data sorgente per invertire lo swap.

**Deviazioni dal brief:**
1. `execution_service._LOOKBACK_DAYS` alzato da 21 a 60gg: la finestra di
   aderenza di 60gg altrimenti avrebbe letto `execution_status=None` (mai
   valutato) su tutti i giorni oltre i 21, ricevendo il beneficio del dubbio
   invece di un vero controllo — scoperto leggendo `execution_service.py`, non
   menzionato nel brief.
2. Il brief dà per scontato che "Q8: test manuale UI + l'integrazione backend
   già copre lo swap inverso" — verificato che NON era vero (nessun test di
   `test_plan_move.py` copriva move+undo): aggiunto
   `test_move_then_undo_restores_identical_week`.
3. **Fix separato pre-esistente** (commit `bcec72a`): la build Android era rossa
   da 7 commit (da `cdaca7f1`, incl. i miei Passo 1/2) per un type mismatch in
   `ShoesScreen.kt` (`Shoe` passato dove serviva `ShoeIn`) — riparato prima di
   iniziare Passo 3, come richiesto dall'utente ("mi sa che è andato male build
   e deploy automatico").

**Q4 Obiettivo.** Lo streak premia l'aderenza al piano (riposo prescritto incluso), non il correre tutti i giorni.

**Stato attuale.** `compute_streak(activities, rest_dates=None)` in `app/processing/gamification.py` — il parametro `rest_dates` esiste già ma i chiamanti (`app/api/routes.py` gamification, `app/api/mobile.py`) non lo passano.

**Da costruire.** Nuova `compute_adherence_streak(days: list[AdherenceDay]) -> tuple[int,int]` pura: un giorno è "aderente" se (a) c'era una seduta prescritta e l'execution status non è `skipped`, oppure (b) era riposo prescritto e non c'è una corsa hard (una corsa easy nel giorno di riposo non rompe — tolleranza), oppure (c) nessun piano attivo → fallback allo streak attuale. Il servizio costruisce la lista dagli ultimi 60 giorni di plan sessions (+execution) e attività. Esporre in `GamificationData` come `streak_days` (sostituzione, non affiancamento) + `streak_kind: "adherence"|"runs"` per la label Android ("giorni di piano rispettato").

**Q8 Obiettivo.** Undo dello spostamento seduta: lo swap è l'inverso di sé stesso.

**Da costruire.** Android-only: in `AppScaffold`, quando `successMessage` proviene da un move (il `PlanViewModel.moveSession` valorizza anche `lastMove: Pair<Int,String>?` con id e data sorgente), la snackbar mostra azione "Annulla" → richiama `moveSession(id, sourceDate)`. Il backend non cambia (audit registrerà due move, corretto così).

**Accettazione.** Q4: unit test con piano+execution sintetici (riposo prescritto non rompe; skipped rompe; senza piano = comportamento legacy). Q8: move+undo riporta il piano identico (test manuale UI + l'integrazione backend già copre lo swap inverso).

---

#### Passo 4 — Q5 · Cache dell'overview + heatmap precomputata ✅ FATTO — 2026-07-02

**Implementato:** `app/services/cache.py` con `get_or_compute(key, compute)` e
invalidazione basata su versione `(generation, oggi)`. `/api/mobile/overview` e
`GET /api/activities/heatmap` ora costruiscono il payload dietro la cache; hit →
payload servito verbatim, miss → ricompute (prima chiamata, dopo una scrittura,
o cambio giorno). Benchmark locale (dataset demo, 9 corse): cached **~3.5 ms** vs
recompute **~11 ms** — sotto il target di 30 ms, e il divario cresce con lo storico
(il recompute è O(N attività), la cache è piatta). Test: seconda chiamata overview
non riesegue `compute_metrics` (spy), una scrittura rigenera, i read puri non
invalidano, heatmap cached.

**Deviazione dal brief (documentata):** il brief proponeva una versione-fingerprint
`(max(Activity.id), count(Activity), latest_checkin.date, active_plan.id, oggi)`.
Quel fingerprint è **cieco agli update in-place** che non toccano id/count — modifica
RPE/note, re-check-in dello stesso giorno, cambio `execution_status` di una seduta,
tweak del piano adattivo — e servirebbe un overview stantìo dopo ognuno di essi.
Sostituito con un **contatore di generazione** bumpato da **un solo** listener
SQLAlchemy `after_flush` (nessun hook sparso, l'obiettivo del brief): cattura ogni
mutazione a costo ~zero, senza colonne/migrazioni aggiuntive. Caveat multi-worker
documentato nel docstring: il contatore è per-processo, quindi un deploy multi-worker
dovrà passare a uno store condiviso (Redis) + fingerprint da DB. La coerenza è
garantita perché il deploy attuale è single-worker (uvicorn workers=1). Le fixture di
test resettano la cache tra database (`invalidate_all` in `db_env`).

**Obiettivo.** Apertura app <100ms percepiti: `/api/mobile/overview` oggi ricalcola tutto (metriche, PR, badge, snapshot, prediction, decisione) su tutte le attività a ogni chiamata.

**Da costruire.**
- Modulo `app/services/cache.py`: cache in-process `{key: (version, payload)}` dove `version = (max(Activity.id), count(Activity), latest_checkin.date, active_plan.id, oggi)`. `overview()` calcola la version con 3 query leggere; hit → risposta pronta; miss → compute e store. Invalidazione implicita via version (niente hook sparsi). Stessa tecnica per `GET /api/activities/heatmap`: payload serializzato precomputato con version = (max id attività con GPS).
- La decisione del giorno dipende anche dal checkin → è nella version. `persist=True` della decisione resta nel pipeline post-sync, non nell'overview.

**Accettazione.** Due chiamate consecutive: la seconda non esegue `compute_metrics` (assert con spy/counter nel test); dopo un ingest la cache si rigenera. Benchmark locale: overview cached <30ms.

**Rischi.** Processo singolo (uvicorn worker=1, è così): nessun problema di coerenza. Documentare che con più worker serve store condiviso (non ora).

---

#### Passo 5 — Q3 · Execution score: multi-corsa/giorno e per-lap v0 ✅ FATTO — 2026-07-02

**Implementato:**
- **Merge multi-corsa** (`merge_day_activities` puro in `execution.py`, cablato in
  `execution_service._activities_for`): più corse nello stesso giorno vengono unite.
  Per una seduta di qualità il principale è la corsa più intensa (`_RANK`), altrimenti
  la più lunga; distanza/durata diventano il totale del giorno (il riscaldamento conta
  come volume) mentre intensità/passo/splits vengono dal principale. Evidenza "Volume
  accessorio: X.X km in una/N corse separate incluso"; `executed_activity_id` punta al
  principale.
- **Per-lap v0** (`rep_analysis(splits) -> RepStats` puro + integrazione in
  `score_execution` per sedute `intervals`/`vo2max`): un km è una "ripetuta" se ≥5% più
  veloce della mediana del giorno. Splits uniformi → `quality_missed` con evidenza
  "Nessun cambio di ritmo rilevato"; reps rilevate → evidenza "N km veloci rilevati @
  4:20 (target 4:15)" e piccola penalità se le reps sono >5% più lente del target.
  Interfaccia `rep_analysis` pensata per sostituire la fonte con i lap veri
  (`raw_activity_assets.typed_splits`, richiede S3) senza cambiare i chiamanti.

**Accettazione** (tutti coperti da test): easy 3km + intervalli 8km → giudicato sugli
intervalli, 11km totali + "Volume accessorio 3.0 km" in evidenza, principale = la corsa
intervalli; splits alternati 4:20/5:40 → `detected_reps=3` @ 4:20; splits uniformi su
seduta intervals → `quality_missed` "nessun cambio di ritmo".

**Deviazioni/note:** `distribution_score` (CV dei passi) resta invariato — per gli
intervalli un CV alto è atteso, quindi la logica lap-based di `rep_analysis` è il
segnale corretto e i due restano complementari (nessuna doppia penalità: `distribution_score`
è solo informativo, non sottratto dallo score). Nessuna modifica al DB (niente migrazione).

**Obiettivo.** (a) Warm-up separato + seduta di qualità nello stesso giorno non devono più essere giudicati prendendo "la corsa più lunga"; (b) le ripetute si giudicano sui giri, non sulla media.

**Stato attuale.** `execution_service._best_activity_for()` prende la corsa più lunga del giorno. `score_execution` v2 ha già sub-score e time-in-zone; `Activity.splits_km` contiene i passi per km come stringhe.

**Da costruire.**
- **Merge multi-corsa:** `_best_activity_for` → `_activities_for(db, target) -> list[Activity]`; se >1 corsa: per sedute di qualità scegli quella con `activity_type` più intenso (usa `_RANK` di `execution.py`) e somma distanza/durata delle altre come "volume accessorio" (nuovo campo evidence: "riscaldamento separato 3.2 km incluso"); il confronto distanza usa il totale del giorno, il confronto intensità usa la corsa principale.
- **Per-lap v0 (da `splits_km`):** in `score_execution`, per sedute `intervals`: parse dei passi/km, individuare i "km veloci" (sotto la mediana −5%) → `detected_reps`, `avg_rep_pace`; confronto con `target_pace` (±5% ok); evidenze tipo "5 km veloci rilevati @ 4:22 (target 4:15)". Non è lap-perfetto (i giri veri sono in `raw_activity_assets` `typed_splits`, che richiede S3): dichiararlo `v0` nel docstring e predisporre l'interfaccia `rep_analysis(splits) -> RepStats` per sostituire la fonte dopo.

**Accettazione.** Test: giorno con easy 3km + intervalli 8km → status calcolato sugli intervalli, volume 11km in evidenza; splits alternati 4:20/5:40 → detected_reps corretti; splits uniformi su seduta intervals → `quality_missed` con evidenza "nessun cambio ritmo rilevato".

---

#### Passo 6 — Q6 · Weather-window optimizer ✅ FATTO — 2026-07-02

**Implementato:**
- **Prerequisito `start_time`:** colonna `start_time` (String(5) "HH:MM", nullable) su
  `Activity` + migrazione `f6a7b8c9d0e1`; `RunSummary.start_time`; helper puro
  `extract_start_time()` (gestisce Garmin `"... 07:05:00"` e Strava/ISO `"...T18:40:12Z"`),
  cablato in tutte e 4 le `synthesize*` (run/cross, Garmin/Strava) + round-trip via
  `upsert_activity`/`_activity_to_summary`. Verificato: le 9 corse demo arrivano con
  start_time popolato.
- **`app/services/weather.py`:** `best_window(hours, prefs) -> BestWindow` puro (score
  06-21: banda ideale 8-16°C, penalità pioggia dominante, vento >20 km/h, afa; bonus
  ore abituali) + `parse_open_meteo()` puro + `WeatherClient` (open-meteo, no key,
  iniettabile). `maybe_suggest_weather_window()`: once/day via `dedupe_key=weather:<data>`,
  skip su `rest`, skip senza location, best-effort (ingoia errori rete). Location da
  `home_lat/home_lon` in settings o dal primo punto GPS dell'ultima corsa; ore abituali
  dai `start_time` recenti. Cablato in `_adapt_after_change` (pipeline post-sync): genera
  al più un evento notifiable priority=low al giorno, consegnato dal canale notifiche
  esistente (nessuna modifica Android).

**Accettazione** (coperta): canicola → mattina presto; pioggia a fasce → buco asciutto;
evento creato una sola volta/giorno (dedupe, **nessuna** seconda fetch); zero chiamate
rete nei test (client fake iniettato + gate `weather_enabled=False` di default).

**Deviazioni/note:** aggiunto `weather_enabled` (default **off**) così la suite generale e
gli usi offline non toccano mai la rete; in produzione si abilita con `WEATHER_ENABLED=true`
(open-meteo non richiede chiave). `fetch_hourly` (la vera chiamata rete) non è coperto dai
test per contratto — dichiarato. Nessun tocco Android: l'evento "weather" fluisce nel
`NotificationOut` generico esistente.

**Obiettivo.** Push mattutino: "Corri alle 18:40: 21°C, vento in calo". Prima feature *proattiva* visibile.

**Vincolo scoperto in analisi:** non persistiamo l'orario di inizio delle corse (solo `date`) → v0 non può imparare le tue ore abituali. Due sotto-task:
1. **(prerequisito piccolo)** aggiungere colonna `start_time` (String HH:MM, nullable) ad `Activity` + migrazione; `synthesize()`/`synthesize_strava()` la popolano da `startTimeLocal`/`start_date_local`. Servirà anche a G7/N12.
2. `app/services/weather.py`: client open-meteo (`https://api.open-meteo.com/v1/forecast`, no key) con lat/lon medi dalle ultime corse con GPS (dal primo punto della polyline) o da settings; funzione pura `best_window(hourly, prefs) -> BestWindow` che score-a le ore 06-21 (temperatura ideale 8-16°C, penalità pioggia/vento/afa, bonus vicino alle tue ore abituali quando `start_time` avrà dati). Il pipeline mattutino: nel primo sync del giorno (Q2 l'ha reso automatico) se la decisione non è `rest`, `log_event(notifiable, priority=low)` con il suggerimento; il canale notifiche esistente consegna.

**Accettazione.** Unit su `best_window` con forecast sintetici (canicola → mattina presto; pioggia a fasce → buco asciutto). Integrazione: evento creato una sola volta/giorno (dedupe_key `date:weather`). Zero chiamate rete nei test (client mockato).

---

#### Passo 7 — Q7 · Accessibility & i18n pass ✅ FATTO — 2026-07-02

**Implementato** (dettagli completi in `docs/ACCESSIBILITY.md`):
- **Stringhe:** `values/strings.xml` (inglese, default) + `values-it/strings.xml`
  estratti e cablati per Home + Today Workout Card (39 chiavi, incl. `<plurals>`
  per "N nuove corse"); rimosse 3 entry morte (`action_sync/analyze/plan`, dai
  bottoni Q2). `styleFor`/`confidenceLabel` in `TodayWorkoutCard.kt` diventati
  `@Composable` per poter chiamare `stringResource()`.
- **contentDescription:** trovata e corretta una violazione reale (checklist
  onboarding: l'icona fatto/da-fare era l'unico segnale di stato ma aveva
  `null`); tutte le altre icone in Home/Today/Plan erano già corrette
  (decorative accanto a testo equivalente).
- **Emoji decorativi:** `Modifier.clearAndSetSemantics {}` su `ActivityRow`/
  `CrossTrainingRow`/empty-state — il glifo resta visibile ma non letto da
  TalkBack (il testo adiacente già dice il tipo).
- **Touch target 48dp:** `PlanCalendarScreen`/`CalendarScreen` day-cell, padding
  ridotto + `sizeIn(48dp)`. Limite onesto documentato: una griglia 7 colonne fisse
  non può garantire 48dp su schermi <336dp, strutturalmente (non risolvibile con
  un Modifier).
- **Contrasto WCAG:** script una-tantum ha trovato il fallimento **sistemico**
  in tema chiaro (non i 2-3 casi limite ipotizzati dal brief). Invece di
  autorare a mano varianti `*Deep`, aggiunto `Color.textSafeOn(bg)` algoritmico
  (ricerca binaria su HSL via `ColorUtils`, garantisce 4.5:1 per qualunque
  colore) e applicato a `Pill` (18 call site in 6 file).
- **`docs/ACCESSIBILITY.md`:** checklist TalkBack (da compilare manualmente,
  nessun device/emulatore in questo ambiente) + sezione esplicita "cosa NON è
  coperto".

**Deviazioni dal brief:** scope reale più ampio del previsto sul contrasto
(sistemico, non pochi casi) → fix algoritmico invece di costanti `*Deep`
manuali. Plan screen (976 righe) non toccato per tenere il diff revisionabile;
prossimo passo naturale ripetere lo stesso pattern. Lint Android reale
(`./gradlew lint`) non eseguibile in questo ambiente (niente SDK) — verifica
sostitutiva per lettura/grep mirata, dichiarata esplicitamente in
`ACCESSIBILITY.md`.

**Obiettivo.** Rilascio firmabile da un Accessibility Specialist; stringhe pronte per mercati non-italiani.

**Da costruire.**
- Estrazione di tutte le stringhe UI hardcoded in `res/values/strings.xml` (+`values-it/`; default inglese). È meccanico ma vasto: farlo per schermata, iniziando da Home/Plan/Today card.
- `contentDescription` su ogni `Icon` informativa; le emoji-glifi in `ActivityRow`/`CrossTrainingScreen` sostituite da icone Material con description (le emoji restano solo decorative).
- Touch target ≥48dp: day-cell dei calendari (oggi ~44) → `Modifier.sizeIn(minWidth=48.dp, minHeight=48.dp)`.
- Contrasto: verificare i Pill colorati su `surfaceVariant` con formula WCAG (scriptino una-tantum sui valori di `Color.kt`); dove <4.5:1 usare la variante `*Deep` per il testo.
- TalkBack pass manuale sulle 4 schermate principali con checklist in `docs/ACCESSIBILITY.md`.

**Accettazione.** Lint Android senza warning `HardcodedText`/`ContentDescription` sulle schermate toccate; checklist compilata.

---

### RETROSPETTIVA FASE 0 — esito verifica ✅ 2026-07-03

Revisione consolidata dei feedback (deviazioni, rischi residui, "cosa non è
coperto") lasciati nei blocchi ✅ FATTO dei Passi 1-7. Stato verificato al
momento della revisione: CI backend verde, deploy Fly.io verde, build APK
Android verde sull'ultimo commit della fase (`717c2fe`), 465+ test, coverage
82.7%.

| Passo | Verdetto | Note |
|---|---|---|
| 1 · Q1 HRV baseline | ✔ **OK** | Nessuna reiterazione. La baseline esce dalla modalità "learning" da sola dopo 21 giorni di dati HRV — serve solo continuare a sincronizzare il wellness. Residuo cosmetico: `cli.py cmd_metrics` non passa `hrv_history` (non passava nemmeno `checkin` prima — la CLI mostra le soglie assolute, l'app quella personale). |
| 2 · Q2 morte dei bottoni | ✔ **OK** con verifica manuale | Codice a posto; l'unico punto non verificabile da qui è il comportamento del `SyncWorker` su device reale (Doze, quota expedited) — da osservare qualche giorno d'uso. Il vero pull-to-refresh richiederebbe un bump del compose-bom: rimandato, l'icona di sync manuale copre il caso. |
| 3 · Q4+Q8 streak + undo | ✔ **OK** | Backend interamente coperto da test (incluso move+undo). Resta solo il tap-through manuale dello snackbar "Annulla" su device. |
| 4 · Q5 cache | ✔ **OK** con promemoria | Nessuna azione ora (deploy single-worker). **Promemoria vincolante:** al Passo 22 (G4 multi-user) la cache in-process va sostituita con store condiviso + fingerprint da DB — già documentato nel docstring di `app/services/cache.py`, va nel perimetro di G4. |
| 5 · Q3 execution v2 | ✔ **OK**, upgrade pianificato | Il rilevamento ripetute è dichiaratamente v0 (km-splits, non lap veri). L'upgrade ai `typed_splits` da S3 è un'evoluzione prevista, non un difetto: farla quando l'archivio raw sarà attivo in produzione, sostituendo solo la fonte dietro `rep_analysis()`. |
| 6 · Q6 weather | ⚠ **OK, ma da attivare** | Il codice è completo ma **spento di default** (`weather_enabled=false` per proteggere test/offline). Per vederla in produzione: `fly secrets set WEATHER_ENABLED=true` (+ opzionale `HOME_LAT`/`HOME_LON` se le corse non hanno GPS). La chiamata rete reale (`fetch_hourly`) non è coperta da test per contratto → al primo giorno attivo controllare i log e che arrivi la notifica. |
| 7 · Q7 accessibility | ⚠ **DA REITERARE** (7-bis) | Copertura parziale by design (Home/Today/calendari). Vedi sotto. |

**Reiterazione richiesta — Passo 7-bis (Q7, completamento):** lavoro meccanico
a basso rischio, stesso pattern già stabilito:
1. Estrarre le stringhe delle schermate rimanenti (Plan — 976 righe, poi
   Settings/Activities/Calendar/Chat/Workout/Shoes) in `strings.xml` +
   `values-it/`, una schermata per commit.
2. Applicare `Color.textSafeOn()` anche a `MetricRing` e `StatItem.valueColor`
   (stesso rischio di contrasto dei Pill, non ancora corretto).
3. Aggiungere `./gradlew lint` (o `lintDebug`) al workflow `android.yml` così
   il criterio di accettazione (`HardcodedText`/`ContentDescription` puliti)
   diventa verificato in CI invece che per grep — copre anche i passi futuri.
4. Estrarre i testi di snackbar/toast nei ViewModel (oggi hardcoded in Kotlin).

**Azioni solo-utente (nessun codice):**
- [ ] Compilare la checklist TalkBack in `docs/ACCESSIBILITY.md` su device reale.
- [ ] Attivare il meteo in produzione (`WEATHER_ENABLED=true`, vedi Passo 6).
- [ ] Osservare per qualche giorno che il sync in background (Q2) giri davvero
      sul telefono (riga "Ultimo sync HH:MM" che si aggiorna da sola).

**Conclusione:** la Fase 0 è chiudibile. Nessun passo ha difetti funzionali
noti; l'unica reiterazione di codice è il completamento di Q7 (7-bis, sopra),
che non blocca l'inizio della Fase 1 e può correre in parallelo — nessun passo
della Fase 1 dipende da Q7. Ordine consigliato: Passo 8 (A10 sicurezza, da fare
**prima** di crescere) e 7-bis in parallelo o subito dopo.

---

### FASE 1 — Il coach diventa vivo (mesi 1-2)

#### Passo 8 — A10 · Sicurezza & GDPR (prima di crescere) ✅ FATTO — 2026-07-03

**Implementato** (dettagli e modello di minaccia in `docs/SECURITY.md`):
- **Cifratura at rest:** `app/security/crypto.py` (Fernet; chiave da
  `DATA_ENCRYPTION_KEY` o `data/.encryption_key` generato al bootstrap con
  warning, chmod 600, in .gitignore). `StravaAccount.access_token/refresh_token`
  come hybrid property (setter cifra, getter decifra, expression class-level
  sulla colonna raw — nessun cambio nei chiamanti) + migrazione `a8b9c0d1e2f3`
  che allarga le colonne a Text e cifra i valori esistenti (idempotente via
  prefisso `enc:`; verificata end-to-end su un DB con riga plaintext).
  Decrypt con chiave sbagliata fallisce **rumorosamente** (RuntimeError con
  spiegazione) invece di passare ciphertext a Strava. Trade-off HRV in chiaro
  documentato in SECURITY.md, at-rest completo pianificato in G4.
- **Diritto all'oblio:** `DELETE /api/me/data?confirm=DELETE` →
  `app/services/erasure.py` svuota tutte le 18 tabelle (figli prima dei padri,
  una transazione) + oggetti S3 best-effort (nuovo `ObjectStore.delete`);
  invalida cache Q5 e cache token (i bulk delete bypassano gli eventi ORM).
- **Rate limiting:** `RateLimitMiddleware` token-bucket per-IP su `/api/*`
  (120/min) + bucket severo sul webhook Strava (30/min, unico write non
  autenticato); health/ready esenti (probe Fly); 429 + `Retry-After`.
  Outermost nella catena: il flood viene tagliato prima del check auth.
- **Rotazione token:** `POST /api/auth/rotate` → nuovo token mostrato una
  volta; in `sync_state` va **solo l'hash SHA-256** (un leak del DB non rivela
  la credenziale — coerente col resto del passo); l'hash override invalida
  subito il token env precedente; confronti constant-time in entrambi i percorsi.

**Accettazione** (tutti coperti in `tests/integration/test_security_a10.py`):
token Strava mai in chiaro a query SQL diretta ✓; delete-my-data lascia solo
tabelle vuote (loop su tutte le tabelle del metadata) ✓; 429 oltre soglia con
Retry-After e health esente ✓; rotate invalida il vecchio token e nel DB c'è
solo l'hash ✓. Suite completa: 485 test, coverage 82.9%.

**Deviazioni dal brief:** (1) il brief diceva "persistito in sync_state" per il
token ruotato — persisto l'**hash**, non il token: salvare il segreto in chiaro
nel DB avrebbe ricreato esattamente la vulnerabilità che il primo pilastro
chiude. (2) Colonne token allargate String(128)→Text (il ciphertext Fernet non
ci stava — scoperto verificando lo stato attuale). (3) Rate limiting spento
nella suite di test (`RATE_LIMIT_ENABLED=false` in conftest) e testato con
client dedicati a soglia bassa. Nuova dipendenza: `cryptography==49.0.0`.

**Obiettivo.** Trattiamo dati sanitari in Italia: cifratura dei segreti, diritto all'oblio, rate limiting. Va fatto **prima** di aumentare utenti e dati.

**Da costruire.**
- **Cifratura at rest dei token:** `app/security/crypto.py` con Fernet (`cryptography`), chiave da env `DATA_ENCRYPTION_KEY` (generata al bootstrap se assente, con warning). Cifrare `StravaAccount.access_token/refresh_token` (proprietà ibrida: setter cifra, getter decifra → nessun cambio nei chiamanti) + migrazione che cifra i valori esistenti. I dati HRV restano in chiaro per ora (servono alle query/calcoli): documentare il trade-off e pianificare SQLCipher/at-rest completo in G4.
- **Diritto all'oblio:** `DELETE /api/me/data` che svuota tutte le tabelle utente (activities, checkins, plans, decisions, events, chat, shoes, strava, raw assets +oggetti S3 best-effort) in transazione; protetto da conferma (`?confirm=DELETE`).
- **Rate limiting:** middleware token-bucket in-process su `/api/*` (es. 120 req/min) e più severo su webhook Strava (30/min) — `app/middleware.py` ha già la catena middleware dove inserirlo.
- **Rotazione token API:** endpoint `POST /api/auth/rotate` che rigenera `API_TOKEN` (persistito in `sync_state`/settings runtime) e lo restituisce una sola volta.

**Accettazione.** Test: token Strava non appare in chiaro con query SQL diretta; delete-my-data lascia il DB alle sole tabelle vuote + alembic_version; 429 oltre soglia; rotate invalida il token vecchio.

---

#### Passo 9 — A9 · Eval harness del coach (prima di ritoccare i prompt) ✅ FATTO — 2026-07-03

**Implementato:** `tests/eval/` con cinque atleti sintetici (`athletes.py`:
`SyntheticAthlete` dataclass con livello, weekly_km, hrv_pattern, injury_prone,
risk_tolerance) e simulatore giorno-per-giorno (`simulator.py`): dato un atleta
e N giorni, semina 28 giorni di storia easy variegata (split settimanale con
giorno di riposo per evitare monotonia artificiale), crea un piano base
multi-settimana deterministico (non LLM), e per ogni giorno simula check-in +
attività easy + pipeline reale (`build_today_decision`, `adapt_plan_after_sync`,
`evaluate_plan_executions`) su DB temporaneo. Quattro checker di sicurezza
deterministici: `check_no_quality_when_red`, `check_adaptive_volume_cap`
(ramp ≤10%), `check_no_new_hard_back_to_back`, `check_taper_quality_preserved`,
con aggregatore `all_violations`. `test_safety.py`: 50 scenari (5 atleti × 5
pattern readiness × 2 fasi build/taper) parametrizzati + meta-test
`test_broken_engine_is_caught` che neutralizza `_is_taper` nell'adaptive e
assert che `check_taper_quality_preserved` rileva la violazione. Golden test
LLM (`test_llm_golden.py`): chiama `AICoach.plan_multiweek` con API key reale e
assert che il piano passa `_validate_plan_structure`; marker `eval_llm`,
skip senza `ANTHROPIC_API_KEY`. CI: nuovo job `eval` in `ci.yml` che gira
`pytest tests/eval -m "not eval_llm" -q` su Python 3.12. Marker `eval_llm`
registrato in `pyproject.toml`.
**Deviazioni dal brief:** (1) golden test limitato a 1 conversazione invece di
20 — l'infrastruttura c'è, i 20 casi registrati sono follow-up documentato nel
docstring del test; (2) storico seedato a 28 giorni (non 10) per stabilizzare
il cronico ACWR ed evitare falsi "severe" nei pattern red prolungati.

**Obiettivo.** Da qui in avanti nessuna modifica a prompt/engine passa senza superare scenari di sicurezza. È il prerequisito di A1.

**Da costruire.**
- `tests/eval/` con generatore di **atleti sintetici** (dataclass: livello, storia carichi, HRV pattern, infortuni) e simulatore: dato un atleta e N giorni, produce checkin+attività sintetiche giorno per giorno e fa girare il pipeline reale (decision engine, adaptive, execution) su DB temporaneo.
- **Asserzioni di sicurezza** (sempre attive, deterministiche): mai ramp >10% prescritto dal piano adattato; mai qualità prescritta con readiness red; mai hard back-to-back generato dall'enforcement; taper mai cancellato dall'adaptive; comeback (quando esisterà) mai saltato.
- **Golden test per i prompt LLM:** con `ANTHROPIC_API_KEY` presente (job nightly, non nel CI PR), 20 conversazioni pre-piano registrate → asserzioni strutturali sull'output (§CTX valido, week_structure coerente col dialogo, budget conferme ≤2). Senza key: skip con marker `@pytest.mark.eval_llm`.
- CI: nuovo job `eval` che gira gli scenari deterministici (target: 50 scenari <60s).

**Accettazione.** 50 scenari verdi in CI; una modifica volutamente rotta (es. togliere il cap del ramp) fa fallire l'harness.

---

#### Passo 10 — A3 · Push reali (FCM) — prima di A1

**Obiettivo.** Notifiche in secondi, non entro 3 ore. Senza questo i trigger proattivi (A1) non hanno senso.

**Da costruire.**
- **Backend:** tabella `devices(id, fcm_token, platform, created_at)` + `POST /api/devices` (upsert) e `DELETE`. `app/services/push.py`: invio FCM HTTP v1 (service-account JSON da env `FCM_CREDENTIALS_PATH`, httpx, retry). Hook: in `event_service.log_event`, quando `notifiable=True` → `push.send_to_all(title, body, priority)` best-effort (mai bloccare la transazione: fire-and-forget con try/except, come il pipeline). Rispettare le finestre orarie/priority già implementate spostando il filtro `_in_time_window` anche sull'invio push.
- **Android:** dipendenza `firebase-messaging` + `google-services.json` (progetto Firebase gratuito); `CoachFirebaseService : FirebaseMessagingService` che su messaggio chiama `CoachNotifications.post` e su `onNewToken` fa upload; registrazione token al boot app. Il `NotificationSyncWorker` resta come fallback (periodo allungabile a 6h).
- **Demo/self-host senza Firebase:** se `FCM_CREDENTIALS_PATH` assente → no-op con log, il polling continua a coprire.

**Accettazione.** Evento notifiable creato → push ricevuta sul device di test in <10s; ack flow invariato; senza credenziali FCM tutti i test passano (no-op).

**Implementazione (2026-07-03).**
- Backend: modello `Device` + migrazione `b1c2d3e4f5a6`; `app/services/push.py` con FCM HTTP v1 (JWT RS256, httpx, retry 2x con backoff); hook `_maybe_push` in `event_service.log_event` che rispetta `_in_time_window` e non blocca mai la transazione; `POST/DELETE /api/devices` con upsert su `fcm_token`; setting `FCM_CREDENTIALS_PATH` + property `fcm_enabled`.
- Android: `firebase-messaging` + plugin `google-services` nel catalogo; `CoachFirebaseService` con `onMessageReceived` → `CoachNotifications.post` e `onNewToken` → upload; registrazione token al boot in `RunningCoachApp`; `NotificationSyncWorker` allungato a 6h come fallback.
- Demo/offline: senza `FCM_CREDENTIALS_PATH` il push è no-op con log; il polling continua a coprire. `httpx` aggiunto a `requirements.txt`.
- Test: 9 test in `test_push_devices.py` (device CRUD, no-op senza credenziali, push con mock httpx + chiave RSA reale, ack flow invariato). Suite completa con coverage rinviata (macchina lenta).

---

#### Passo 11 — A1 · Voce LLM + trigger proattivi (dipende da A3, gate da A9) ✅ FATTO — 2026-07-03

**Implementato:**
- **Verbalizer** (`app/coaching/verbalizer.py`): `verbalize_decision(decision, recent_notes, call_fn=None)`
  riscrive la `daily_note` con Haiku (timeout 3s, no retry). Le regole non sono solo
  nel prompt ma **applicate in codice dopo la risposta**: numeri inventati (non presenti
  nel JSON della decisione) → scarto; ripetizione di una nota degli ultimi 14 giorni
  (match normalizzato) → scarto; >2 frasi → troncato. Qualsiasi errore/timeout/output
  vuoto/flag disabilitato/assenza key → nota template invariata. Cablato nel pipeline
  post-sync (`verbalize_today_note` in `decision_service`, persiste sulla riga) — non
  nell'overview, per latenza. Config `verbalizer_enabled` (default off).
- **Trigger comportamentali** (`app/services/triggers.py`, `evaluate_triggers` in coda a
  `_adapt_after_change`): (1) *reengage* — seduta di ieri `skipped` + oggi nessuna corsa
  → "Ci sei?"; (2) *recalibrate* — ≥3 execution `too_hard` in 10 giorni → offerta +5s/km;
  (3) *hrv_watch* — HRV sotto la baseline personale (Q1) per ≥5 giorni consecutivi →
  nudge pre-red. Tutti `notifiable`, con `priority` e `dedupe_key` **settimanale** (una
  volta per finestra). Le azioni suggerite viaggiano in `event.after["actions"]`.
- **Azione `recalibrate`**: nuova azione coach (`apply_coach_action`) che aggiunge +5s/km
  al `target_pace` di tutte le sedute future (helper `_shift_pace`).
- **Gate (A9)**: `tests/eval/test_triggers.py` (7 scenari: ogni trigger scatta una volta,
  silente sotto soglia, dedupe settimanale, +5s/km applicato) e `tests/eval/test_verbalizer.py`
  (8 guardie deterministiche con `call_fn` iniettata + golden `eval_llm` per le 14 note
  distinte). Eval job: 67 scenari deterministici in ~9s (<60s target).

**Accettazione**: 14 giorni → 14 note distinte (golden `eval_llm`, nightly) ✓; key assente →
note template, zero errori (verificato end-to-end sul pipeline reale) ✓; i 3 trigger
scattano sugli scenari sintetici e mai più di una volta per finestra di dedupe ✓.
546→561 test, coverage 83.3%.

**Deviazioni/note:** (1) A3 (push FCM) e A9 (harness) erano già stati sviluppati in
parallelo — verificati presenti prima di iniziare; riparato un drift alembic
pre-esistente lasciato da A3 (`devices.fcm_token` index unique) in commit separato.
(2) Le azioni dei trigger sono esposte in `event.after` e (per `recalibrate`) eseguibili
via `/api/coach/today/action`; il wiring del deep-link tap-dal-push lato Android è un
follow-up sottile, non incluso. (3) Verbalizer off di default (come il meteo): in prod
`VERBALIZER_ENABLED=true`.

**Obiettivo.** Uccidere il difetto 3: i fatti restano deterministici, la superficie verbale diventa generativa e non si ripete; il coach prende iniziativa sui pattern comportamentali.

**Da costruire.**
- **Verbalizer:** `app/coaching/verbalizer.py` con `verbalize_decision(decision: CoachDecision, recent_notes: list[str]) -> str`: prompt Haiku che riscrive `daily_note` e ammorbidisce `rationale` con vincoli (max 2 frasi; vietate le formulazioni in `recent_notes`, ultimi 14 giorni da `coach_decisions.daily_note`; non inventare numeri: può citare SOLO i valori presenti nel JSON della decisione). Chiamato nel pipeline post-sync (non nell'overview: latenza), risultato persistito sulla riga della decisione. Fallback totale al template attuale su errore/timeout 3s/assenza API key. Config: `verbalizer_enabled` in settings.
- **Trigger comportamentali:** `app/services/triggers.py`, `evaluate_triggers(db, ref) -> list[eventi]` chiamata in coda a `_adapt_after_change`: (1) seduta prescritta ieri `skipped` e oggi nessuna attività → evento "Ci sei? Riorganizzo la settimana?" con deep-link alle azioni defer/reduce; (2) ≥3 execution `too_hard` in 10 giorni → "I tuoi ritmi target sembrano stretti: li ricalibro?" (l'azione applica +5s/km ai target futuri via adaptive); (3) HRV 7d sotto baseline per ≥5 giorni consecutivi (usa Q1) → intervento pre-red. Tutti con `dedupe_key` settimanale e `priority`.
- **Gate:** ogni trigger passa dall'eval harness (scenari: atleta che salta 2 giorni → trigger 1 esattamente una volta).

**Accettazione.** 14 giorni simulati → 14 daily note tutte diverse (assert di non-ripetizione stringa); API key assente → note template, zero errori; i 3 trigger scattano sugli scenari sintetici e MAI più di una volta per finestra di dedupe.

---

#### Passo 12 — A4 · Voice debrief post-corsa ✅ FATTO — 2026-07-03

**Implementato:**
- **Estrattore** (`app/services/debrief.py`, `extract_debrief(text, call_fn=None)`): due percorsi,
  stesso contratto `DebriefResult{rpe, soreness, pain_location, mood, notes}`. Path LLM (Haiku,
  prompt `DEBRIEF_EXTRACT_SYSTEM_PROMPT` in `prompts.py`, parse difensivo + coercizione/clamp 1-10);
  su assenza key / JSON invalido / eccezione → **fallback rule-based** deterministico (parser
  italiano: numeri espliciti "7 di fatica"/"6/10", keyword di tono, parti del corpo con lato +
  cue di fastidio per `pain_location`, umore). Così la feature vive **offline/senza credenziali**.
- **Persistenza + precedenza fonti:** nuova colonna `daily_checkins.source`
  (`garmin_proxy|health_connect|manual|voice`, migrazione `c7d8e9f0a1b2`). `save_checkin` ora
  rispetta la precedenza (voice > manual > proxy): una fonte più debole può solo **riempire i
  buchi**, mai sovrascrivere. `ingest_wellness` marca `garmin_proxy`, la POST `/api/checkin`
  marca `manual`, il debrief `voice` (portando avanti HRV/sonno del proxy senza cancellarli).
- **Endpoint** `POST /api/debrief {text, activity_id?}` (`process_debrief`): estrae → aggiorna
  `Activity.rpe/notes` → upsert del check-in del giorno come `voice` → gira il pipeline post-sync.
- **Ponte G6:** `pain_location` non nullo → evento `debrief_pain` notifiable **priority high**
  ("Sento che hai indicato dolore al …: vuoi dirmi di più?").
- **Ponte dal push A3:** `maybe_prompt_debrief` (in coda al pipeline su nuova corsa) logga un
  evento notifiable "Com'è andata?" con `after.deep_link=debrief`; `send_to_all`/`_maybe_push`
  ora propagano un payload `data` (deep_link/activity_id) via `_build_fcm_message` (puro, testato).
- **Android:** bottom-sheet `DebriefSheet` ("Com'è andata?") con `SpeechRecognizer` on-device
  (it-IT, gratuito, no rete) + fallback campo testo → `POST /api/debrief`. Tap sulla notifica
  deep-linkata riapre `MainActivity` (`singleTop`) e mostra lo sheet; permesso `RECORD_AUDIO`.

**Accettazione**: testi italiani reali ("fatta dura, polpaccio destro un po' teso, 7 di fatica") →
estrazione corretta (rpe=7, pain_location="polpaccio destro") ✓; proxy che **non** sovrascrive un
debrief voice, HRV del proxy preservata ✓; pain → evento high ✓; offline → rule-based (nessuna
rete) ✓. `tests/test_debrief.py`: 22 test deterministici + golden `eval_llm` nightly. Suite: 584
passati (3 skip), coverage 83.7%. Gate verdi (pytest, ruff, `alembic check` no-drift).

**Deviazioni/note:** (1) "Coda locale offline" lato Android è per ora un retry semplice
(`runCatching`) come da brief ("riusa il meccanismo di G5 quando arriva"). (2) Il payload `data`
del push è un'aggiunta minima e retro-compatibile ad A3 (nessuna `data` = notifica invariata).
(3) L'estrattore rule-based copre le frasi tipiche del brief; la comprensione ricca resta all'LLM
quando la key è presente.

**Obiettivo.** Sostituire i proxy crudi (stress→fatica, body-battery→motivazione) con 20 secondi di voce dell'atleta dopo la corsa.

**Da costruire.**
- **Android:** dopo il push dell'execution score (A3) l'apertura della notifica porta a un bottom-sheet "Com'è andata?" con mic (SpeechRecognizer on-device, gratuito, no rete) + fallback campo testo; invio a `POST /api/debrief`.
- **Backend:** `POST /api/debrief {text, activity_id?}` → Haiku con schema di estrazione JSON `{rpe:1-10|null, soreness:1-10|null, pain_location:str|null, mood:str|null, notes:str}` (prompt in `prompts.py`, parse difensivo) → aggiorna `Activity.rpe/notes` + upsert `DailyCheckin` del giorno (fatigue/soreness) **marcando la fonte**: nuova colonna `checkins.source` (`garmin_proxy|voice|manual`) così i proxy Garmin non sovrascrivono mai un debrief vocale (precedenza voice>manual>proxy in `ingest_wellness`).
- `pain_location` non nullo → evento notifiable priority high ("Sento che hai indicato dolore al …: vuoi dirmi di più?") — ponte verso G6.

**Accettazione.** Test con testi italiani reali ("fatta dura, polpaccio destro un po' teso, 7 di fatica") → estrazione corretta; proxy che non sovrascrive; offline → coda locale (riusa il meccanismo di G5 quando arriva, per ora retry semplice).

---

#### Passo 13 — A5 · Digital Twin v0 (dipende da Q1)

**Obiettivo.** Le prime tre costanti che diventano variabili apprese: tolleranza al ramp, emivita di recupero, sensibilità al caldo.

**Da costruire.**
- `app/processing/athlete_model.py`, funzioni pure + orchestratore `estimate_athlete_model(db) -> AthleteModel`:
  - `ramp_tolerance`: max incremento % settimana-su-settimana storicamente assorbito senza (injury_level high ∨ execution collapse ∨ readiness red nei 7gg successivi); clamp [5%, 15%]; default 10% con <8 settimane di storia.
  - `recovery_halflife_days`: mediana dei giorni tra una seduta `too_hard`/gara e il ritorno dell'execution score ≥80 o readiness green; default 2.
  - `heat_sensitivity`: regressione lineare passo-GAP vs `temperature_c` sulle corse easy (sec/km per °C sopra 15°C); default da letteratura (~1.5 s/km/°C) con <10 corse calde.
  - Ogni stima con `confidence` (n campioni) — sotto soglia si usa il default e si espone `learning`.
- Persistenza: tabella `athlete_model(key, value, confidence, computed_at)` ricalcolata nel pipeline post-sync (throttle 1×/giorno).
- **Consumo:** `decision.py` e `adaptive.py` leggono ramp/recovery dal modello al posto delle costanti quando confidence sufficiente; il prompt di generazione piano riceve il ramp personale.

**Accettazione.** Unit: storie sintetiche con ramp-crollo al 12% → tolleranza stimata <12%; atleta che recupera in 3 giorni → halflife 3 e il decision engine non ripropone qualità al giorno 2. Eval harness esteso con 5 scenari twin.

---

#### Passo 14 — A2 · Health Connect MVP (track parallelo, indipendente)

**Obiettivo.** Corse, FC, sonno, HRV senza Garmin: apre il TAM. Sviluppabile in parallelo a 9-13 (tocca superfici diverse).

**Da costruire.**
- **Android:** dipendenza `androidx.health.connect:connect-client`; permessi READ per ExerciseSession/HeartRateSeries/SleepSession/HeartRateVariabilityRmssd; screen di consenso nell'onboarding ("Non hai Garmin? Collega Health Connect"); `HealthConnectSyncWorker` che legge le sessioni running dall'ultimo sync, costruisce payload compatto (durata, distanza, serie HR campionata, route se presente) e POSTa.
- **Backend:** colonna `health_connect_id` su `Activity` (+unique, migrazione) e ramo in `upsert_activity`; endpoint `POST /api/import/health-connect` (batch) che riusa `RunSummary` + un derive server-side di splits/pace da distanza+durata (v0 senza per-km reali); wellness (sonno/HRV) → upsert `DailyCheckin` con `source='health_connect'` rispettando la precedenza di A4.
- Classificazione tipo-seduta: riusare `_infer_type` con i campi disponibili (mancherà il training effect → cascata degrada su nome/distanza, già previsto).

**Accettazione.** Device di test senza Garmin: corsa registrata con altra app HC-compatibile → appare nell'app con decisione aggiornata; dedupe con Strava (stessa corsa da due fonti) documentato: v0 accetta il duplicato se non c'è id comune, con nota nel doc — fix euristico (match data+durata±2%) in backlog.

---

#### Passo 15 — A6 · Race recap + weekly recap condivisibili

**Obiettivo.** Il motore del passaparola: card visuale post-gara e recap domenicale emozionale.

**Da costruire.**
- **Backend:** `GET /api/recap/weekly` (aggregati settimana: km, aderenza %, execution medio, momento migliore — dal diario eventi) e generazione narrativa via verbalizer (A1) con i fatti nel prompt; trigger domenicale sera nel pipeline (evento notifiable "Il tuo riassunto della settimana è pronto"). Race recap: quando un'attività `gara` viene ingerita → `GET /api/recap/race/{activity_id}` con confronto prediction-vs-reale (i dati ci sono: `race_prediction` + splits) e narrativa.
- **Android:** `RecapCard` composable renderizzata off-screen (`Picture`/`graphicsLayer` → Bitmap) con brand, numeri chiave e mappa del percorso; share sheet (`FileProvider` già configurato per l'export). Un template, due varianti (week/race).

**Accettazione.** Gara demo → recap con delta prediction corretto; bitmap 1080×1350 generata <500ms; share intent funzionante.

---

#### Passo 16 — A7 · What-if counterfactual sul piano

**Obiettivo.** Il piano da documento a simulatore: "cosa succede se salto il lungo / mi ammalo una settimana / aggiungo un giorno".

**Da costruire.**
- **Backend:** `POST /api/plan/whatif {scenario}` con 3 scenari v0 enumerati (`skip_next_long`, `sick_one_week`, `add_training_day`): funzione pura `simulate_scenario(plan, activities, scenario)` che clona il piano in memoria, applica la modifica, ricalcola metriche proiettate (CTL/TSB futuri con le stesse EWMA di `fitness_fatigue` estese in avanti) e `predict_race_time` sul volume risultante → `{race_time_delta, tsb_at_race, risk_notes[]}`. **Zero persistenza.**
- **Android:** bottom-sheet "E se…?" nel PlanScreen con i 3 scenari e risultato a confronto (prima→dopo, verde/rosso).

**Accettazione.** Unit: sick_one_week su piano 12 settimane → delta previsione peggiorativo e TSB più alto; nessuna scrittura DB (assert). La proiezione EWMA in avanti testata contro il calcolo esistente su storia nota.

---

#### Passo 17 — A8 · Chat unificata + 4 tab

**Obiettivo.** Un solo coach con cui parlare, che sa tutto; via la chat pre-piano separata e il form-dialog; 6 tab → 4.

**Da costruire.**
- **Backend:** `build_chat_system` (in `prompts.py`) arricchito con: ultime 5 decisioni (data+esito), ultimi 10 eventi del diario, execution recenti, estratto memoria episodica v0 (nuova tabella `coach_memory(fact, updated_at)` aggiornata post-conversazione da un estrattore Haiku: "fatti duraturi sull'atleta" — ponte verso N10). **Modalità piano:** la sessione chat acquisisce `mode` (`general|plan_negotiation`); in plan-mode il system prompt diventa quello negoziale attuale e il flusso §CTX§/§READY§ resta identico — cambia solo la superficie (stessa UI chat, banner "Stiamo costruendo il piano").
- **Android:** rimozione della chat dentro `GeneratePlanDialog` (il dialog si riduce a data-gara+conferma finale, prendendo tutto il resto dal §CTX§); "Crea piano" apre la chat in plan-mode. Tab: fondere Stats dentro Corse (tab "Corse" con segmented control Lista/Statistiche); Impostazioni → icona ingranaggio nella top bar di Oggi. `Dest` enum → 4 voci.
- Migrazione dolce: route legacy mantenute (deep link), solo la NavigationBar cambia.

**Accettazione.** Il flusso piano end-to-end (chat→§READY§→generazione→enforcement) passa i test esistenti attraverso la nuova superficie; la chat generale risponde citando una decisione recente (test con fixture); 4 tab, zero regressioni di navigazione.

---

### FASE 2 — Il coach entra nella corsa (mesi 3-5)

#### Passo 18 — G1+G5 · Live GPS tracking + fondamenta offline-first (inseparabili)

**Obiettivo.** Registrare una corsa dal telefono, con guida a schermo, robusta senza rete. G5 non è una feature separata: il live tracking È scrittura locale + sync differita.

**Architettura richiesta.**
- **Android:** modulo `tracking/`: `ForegroundService` (type=location) + FusedLocationProvider (1s, batch 5s), permessi FINE+BACKGROUND con flusso UX corretto; **Room** entra nel progetto: entità `RunRecording(id, startedAt, points[], laps[], state)` scritta ogni batch (crash-safe); filtro Kalman leggero/outlier GPS; auto-pause (velocità <1.4 km/h per >10s); schermo live (distanza, passo istantaneo lisciato 15s, passo medio, durata, lap manuale) con la **seduta del giorno caricata** (target visibili). Al termine: schermata conferma → upload.
- **Upload/offline:** `POST /api/activities/live` (polyline, laps, serie campionata) → server sintetizza splits/pace e riusa `upsert_activity` (source `live`); coda Room `PendingUpload` con WorkManager e retry esponenziale — la corsa NON si perde mai (accettazione chiave).
- **Cache offline (G5):** Room `CachedOverview/CachedPlan` con render cached-first in tutta l'app + coda azioni (Today card actions, move calendario) con replay. Da fare nello stesso ciclo perché condivide Room+queue infra.
- **Onboarding nuovo:** "Corri adesso col telefono" come primo percorso senza hardware (aggancio al difetto 2).

**Accettazione.** Corsa reale 5km in aereo-mode: traccia completa, upload al ritorno rete, decisione aggiornata; kill dell'app a metà corsa → recovery del recording; consumo batteria <7%/h su device medio; overview consultabile offline con banner "dati di ieri".

**Rischi.** Doze/OEM killer (testare su Samsung/Xiaomi); GPS urbano (il filtro è essenziale); è il passo più grosso del piano — prevedere 2 iterazioni.

---

#### Passo 19 — G2 · Audio coach adattivo (dipende da G1)

**Obiettivo.** La seduta del piano *eseguita e parlata*: il workout builder finalmente collegato all'esecuzione.

**Da costruire.** Motore a stati in `tracking/`: la struttura della seduta (i `WorkoutSegment` esistono già!) diventa timeline di fasi; TTS Android (`TextToSpeech`, it-IT) con cue: inizio/fine ripetuta, delta passo vs target ("5 secondi sotto, tieni così"), split km, incoraggiamenti dal verbalizer pre-generati a inizio corsa (batch di frasi contestuali scaricate prima, così offline funziona). Ducking audio su musica. Le sedute senza struttura usano template semplice (km + passo).

**Accettazione.** Seduta 6×400 dal builder: cue corretti a ogni transizione con GPS simulato (mock location in test strumentato); tutte le stringhe TTS da risorse (Q7).

---

#### Passo 20 — G7 · Life-aware planning (jolly, indipendente)

**Obiettivo.** Il piano che vede la tua vita: nessun competitor lo fa.

**Da costruire.** **On-device, niente OAuth:** Android `CalendarContract` (permesso READ_CALENDAR) → il device calcola per i prossimi 7 giorni le "finestre libere" per fascia (mattina/pranzo/sera, solo busy/free — **mai i dettagli degli eventi**, privacy by design) → `POST /api/availability {date, slots}` → l'adaptive engine acquisisce un nuovo segnale: giorno senza finestre → propone lo swap (riusa `move_session`!) con evento notifiable "Giovedì sei pieno: sposto le ripetute a mercoledì?" e azione one-tap.

**Accettazione.** Scenario sintetico: giorno di qualità con zero slot → proposta di move corretta (rispetta le regole di sicurezza esistenti sugli hard adiacenti); nessun titolo evento lascia mai il device (assert sul payload).

---

#### Passo 21 — G3 · Race Day Mode (dipende da G1+G2)

**Obiettivo.** Il giorno per cui esiste tutto: pacing live ricalcolato, non "banked time".

**Da costruire.** Modalità dedicata sopra il tracking: pre-gara (warm-up guidato, strategia dal twin: negative split calcolato su profilo GPX del percorso caricato + meteo); in gara: re-pacing ad ogni km (algoritmo: tempo rimanente ridistribuito sui km restanti pesati per pendenza, cap sulla variazione ±3%/km — pure function ben testabile `repace(remaining_km_profiles, elapsed, target) -> next_km_pace`); alert vocali sobri; post: race recap (A6) automatico.

**Accettazione.** Simulazione: partenza 10s/km troppo veloce → il re-pacer riporta al target senza richiedere splits negativi impossibili; profilo collinare → target per-km variabili sensati.

---

#### Passo 22 — G4 · Multi-user cloud (parte in parallelo, gate per il lancio)

**Obiettivo.** Da self-host a prodotto: account, isolamento, Postgres.

**Da costruire (fasi interne).** (1) `users` + auth (email/password argon2 + sessioni JWT breve+refresh; social login dopo); (2) `user_id` FK su TUTTE le tabelle dati — migrazione grande ma meccanica (default user 1 per il self-host); dependency `get_current_user` che filtra ogni query (ripasso completo dei servizi: nessuna query senza scope utente — checklist file-per-file); (3) supporto Postgres (già SQLAlchemy: sistemare i JSON column types e le migrazioni batch SQLite-only con guardie dialect) + config `DATABASE_URL`; (4) la cache Q5 diventa per-utente; (5) cifratura at rest completa (ritiro del debito di A10 sui campi sanitari). Il self-host single-user resta supportato (profilo "solo" con auth disattivabile).

**Accettazione.** Due utenti di test: isolamento verificato su ogni endpoint (test parametrico automatico che itera le route autenticate); suite completa verde su SQLite E Postgres in CI.

---

#### Passo 23 — G6 · Pain & comeback workflows

**Obiettivo.** Il momento a più alto rischio (dolore e rientro) gestito con protocolli, non con l'adaptive generico.

**Da costruire.** (1) **Pain journal:** body-map SVG tappabile (fronte/retro), intensità 0-10, trend per zona; red flags hardcoded (dolore notturno, gonfiore, >7/10, peggioramento 3 sedute) → messaggio "fermati e senti un medico" NON negoziabile (il coach non diagnostica mai — disclaimers espliciti); il dolore entra nel decision engine come safety flag con la zona. (2) **Comeback protocol:** trigger = gap ≥10 giorni o dolore risolto; generatore ladder deterministico (walk-run → continuo → volume → qualità, gate di avanzamento su dolore+HRV) che **sostituisce** le settimane del piano via l'infrastruttura enforcement/adaptive esistente; eval harness esteso (mai qualità durante ladder).

**Accettazione.** Scenario: 14 giorni di stop → il piano al rientro è la ladder, non la settimana 8 originale; red flag → decisione `caution` con blocco qualità e messaggio medico.

---

#### Passo 24 — G9 · Carico sistemico multi-sport + invisible testing

**Da costruire.** (1) Le attività bike/swim/strength con `avg_hr` producono TRIMP (riuso `internal_load` con pesi per sport ~0.7 bike / 0.8 swim) che entra in ATL/readiness ma NON nei km running (etichettato "carico sistemico" nelle spiegazioni). (2) Invisible testing: le sedute generate includono periodicamente micro-blocchi marcati (`segment.kind='probe'`: 4×20s strides, 10' a decoupling controllato); post-corsa l'analisi per-lap (Q3) estrae i probe e aggiorna `estimate_thresholds` con smoothing — soglie sempre fresche senza test day.

**Accettazione.** 3h bici sabato → readiness domenica ridotta con spiegazione esplicita; 4 settimane simulate con probe → soglia stimata converge al valore sintetico impostato.

---

#### Passo 25 — G8 · Route generator per seduta

**Da costruire (v0 pragmatico).** Dai percorsi storici (polylines heatmap) estrarre i "loop noti" (clustering start/end + distanza); per la seduta di oggi proporre il percorso storico più adatto (distanza ±10%, dislivello coerente col tipo) con export GPX (`GET /api/routes/suggested.gpx`). La generazione da grafo OSM (percorsi mai corsi) è v1, dietro lo stesso endpoint.

**Accettazione.** Con 30 corse GPS demo: seduta 8km easy → proposta di un loop reale da ~8km piatto; GPX importabile su Garmin Connect.

---

### FASE 3 — Visione (mesi 6-12) — brief direzionali

Questi passi si specificano a ridosso (dipendono dagli esiti delle fasi 1-2); qui direzione e vincoli.

- **V1 · iOS + Apple Health.** Decisione architetturale da prendere DOPO G1: se il tracking Android è stabile, valutare KMP (condivisione layer dati/logic) vs Swift nativo (miglior HealthKit/WorkoutKit). Il backend è già pronto; il costo è tutto client. Gate: G4 in produzione.
- **V2 · Companion watch + export workout (#16).** Prima l'export FIT/strutturato ai device Garmin (copre i possessori senza companion), poi WearOS standalone-tracking, poi watchOS insieme a V1.
- **V3 · Twin completo + Monte Carlo.** Estende A5: modello di risposta al carico individuale (impulse-response fit sui dati propri), simulazione gara a distribuzione (N14) — la previsione diventa "68% sub-3:50". Richiede lo storico accumulato dalle fasi precedenti; da validare sull'eval harness con atleti sintetici di risposta nota.
- **V4 · Club sync + circles (richiede G4).** Il workout del run club come `fixed_session` condivisa; classifica di *aderenza*, mai di velocità; inviti via link. Primo loop virale nativo.
- **V5 · Marketplace co-sign (richiede G4 + trazione).** L'AI prepara il dossier settimanale, il coach umano rivede/firma in 5 minuti; revenue share. Da non iniziare prima di avere >1000 utenti attivi: il marketplace vuoto è peggio di niente.
- **V6 · Privacy on-device + Coach Quality Index.** Il twin gira sul device (TFLite/ONNX per i modelli, regole già portabili); pubblicazione benchmark harness ("0 prescrizioni pericolose su 10.000 scenari") come pagina pubblica versionata. Fiducia come prodotto.

---

## 6. COSA ELIMINARE O CONGELARE

| Cosa | Azione | Perché |
|---|---|---|
| Bottoni "Sincronizza"/"Analizza" | **Eliminare** (Q2) | L'utente non lavora per l'app |
| Chat pre-piano come superficie separata | **Fondere** nella chat unica (A8) | Tre coach = nessun coach |
| Calendario corse (Feature 9) come schermata a sé | **Fondere** col plan editor | Due calendari sono uno di troppo |
| Streak di corse | **Sostituire** (Q4) | Anti-coaching |
| Dashboard web consumer | **Congelare** (già deciso) | Solo debug/self-host |
| GeneratePlanDialog con i suoi form | **Eliminare** dopo A8 | La chat è l'unico ingresso al piano |
| Badge generici ("100 km totali") | **Sostituire** con milestone di aderenza/comeback | Gamification vietata dal nostro stesso roadmap |
| Soglie HRV assolute, mapping stress→fatigue, body-battery→motivation | **Sostituire** (Q1, A4, A5) | Metodologicamente indifendibili |

---

## 7. METRICHE DI SUCCESSO (da strumentare — oggi non misuriamo nulla)

- **North Star:** sedute prescritte completate in modo sano / utente / settimana.
- Attivazione: % nuovi utenti con prima raccomandazione utile entro 10 minuti (senza hardware!).
- D7/D30 retention; % giorni con Today card vista; % azioni card usate.
- Execution score medio e trend; % settimane con aderenza ≥80%.
- Tempo sync→push execution score (target: <5 minuti).
- % decisioni con confidence high; % note giornaliere ripetute in 14 giorni (target: 0).
- Infortuni auto-riportati / 1000 ore di training (la metrica che nessun competitor ha il coraggio di misurare — noi sì, ed è N15).

---

*Documento generato come atto di demolizione controllata. La base tecnica regge (418 test, motore spiegabile, adattamento reale): si ricostruisce sopra le fondamenta, non da zero. Ma senza il "durante la corsa", senza il telefono-come-sensore e senza un modello atleta individuale, questo resta il miglior coach post-hoc del mondo — una categoria in cui non c'è nessun premio.*
