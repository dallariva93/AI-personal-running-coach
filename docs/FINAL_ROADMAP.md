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
| A3 | **Push reali (FCM)** + execution score push entro minuti dalla sync — chiude il loop dopamminico | 9 | 5 | medio | basso | altissimo | 3 sett |
| A4 | **Voice debrief post-corsa** (N5) — sostituisce i proxy crudi fatigue/motivation | 9 | 5 | medio | basso | altissimo | 2-3 sett |
| A5 | **Digital Twin v0** (N1): recovery half-life, ramp tolerance e heat sensitivity stimate dai dati storici, con fallback ai default | 9 | 6 | medio | medio | altissimo | 4 sett |
| A6 | **Race recap condivisibile** (#11) + weekly recap emozionale — il motore del passaparola | 9 | 5 | medio | basso | altissimo | 3-4 sett |
| A7 | **Counterfactual what-if sul piano** (N2) | 9 | 6 | medio | basso | altissimo | 3-4 sett |
| A8 | **Chat unificata**: una sola conversazione col contesto completo (decisioni, execution, eventi, memoria episodica v0 N10); via la chat pre-piano separata; 4 tab | 8 | 5 | medio | medio | alto | 3-4 sett |
| A9 | **Eval harness coach v1** (#25): 50 scenari sintetici in CI; nessun prompt cambia senza passare i test di sicurezza | 8 | 6 | medio | medio | alto | 4 sett |
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
