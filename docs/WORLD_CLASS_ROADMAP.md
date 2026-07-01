# Roadmap strategica per un AI Running Coach world-class

## Obiettivo

Trasformare il progetto da piattaforma tecnica avanzata per analisi e pianificazione running a prodotto consumer capace di competere con Garmin, Strava, Runna, TrainingPeaks, Nike Run Club e Coros.

Il prodotto non deve essere un cruscotto di metriche. Deve diventare un coach che decide con l'atleta cosa fare oggi, lo guida durante la corsa, adatta il piano alla vita reale e spiega ogni scelta con trasparenza.

## Verdetto iniziale

Il progetto ha una base forte: backend FastAPI, Android nativo, integrazione Garmin/Strava, coach AI/offline, piani multi-settimana, chat, metriche di carico, gamification, heatmap e workout builder.

Il limite principale è strategico: oggi l'app è ancora troppo orientata a report, metriche e azioni manuali. Un prodotto world-class deve essere orientato a decisioni, momenti quotidiani, adattamento automatico e guida in tempo reale.

## Posizionamento target

### Posizionamento attuale implicito

Dashboard tecnica e mobile app per analizzare le corse e generare consigli AI.

### Posizionamento desiderato

Il coach che decide con te cosa fare oggi, ti guida durante la corsa e adatta il piano alla tua vita reale.

## North Star Metric

Weekly completed prescribed sessions.

La metrica centrale non deve essere il numero di chat, il numero di chilometri o le aperture dell'app, ma quante sedute prescritte vengono completate in modo sano, coerente e sostenibile.

## Principi guida

1. Ogni schermata deve rispondere alla domanda: cosa devo fare adesso?
2. Le metriche avanzate devono supportare la decisione, non sostituirla.
3. Ogni decisione AI deve avere motivazione, confidenza e segnali usati.
4. Il piano deve adattarsi automaticamente dopo attività, check-in e variazioni di contesto.
5. L'app deve creare momenti emozionali, non solo statistiche.
6. Il mobile è il prodotto principale; dashboard web e CLI sono strumenti secondari.
7. La sicurezza e la privacy devono diventare parte del valore del prodotto.

## Gap principali

### Product

- Mancanza di una raccomandazione giornaliera dominante.
- Piano non ancora percepito come autopilota adattivo.
- Troppe metriche esposte come elementi primari.
- Mancanza di live tracking e audio coach.
- Mancanza di Health Connect, Apple Health e iOS.

### UX

- Decision fatigue: sync, analyze, plan, chat e workout sono azioni separate.
- Onboarding non abbastanza guidato verso la prima raccomandazione utile.
- La home deve diventare il centro decisionale del coach.
- Le metriche devono essere progressive: semplice per principianti, dettagliata per esperti.

### AI

- L'AI produce ancora soprattutto testo e report.
- Serve un Coach Decision Engine con output strutturato.
- Mancano confidence, missing data, alternative e decision trace.
- L'AI deve prendere iniziativa dopo sync, check-in, corsa saltata o rischio infortunio.

### Running coaching

- Piani ancora troppo generici rispetto a un coach umano elite.
- Manca un execution score per misurare quanto la seduta è stata rispettata.
- Manca una gestione seria di dolore, infortuni, scarpe, meteo e fueling.
- Serve modellare atleta, durability, threshold, speed reserve, aderenza e rischio.

### Motivazione

- PR, streak e badge sono utili ma insufficienti.
- Mancano momenti emozionali personalizzati.
- Serve una narrativa di stagione: progresso, difficoltà, comeback, race journey.
- Il coach deve far sentire l'utente capito, non solo misurato.

### Architettura

- Architettura attuale ottima per single-user/self-host.
- Per scala consumer servono multi-user, account, job async, notifiche, cache offline, event-driven coach brain.
- Il mobile deve diventare offline-first.
- Serve observability prodotto: activation, retention, funnel, feature usage.

### Business

- Le feature ad alto ROI sono: daily adaptive workout, notifiche intelligenti, audio coach, race day mode, compliance score, recap condivisibili, piani premium.
- Per conversione servono piani gara premium, live coach, esportazione workout e AI race strategy.
- Per passaparola servono momenti condivisibili e storytelling.

## Competitor gap

### Garmin

Garmin domina su dati fisiologici, device, readiness e affidabilità sensori. È debole su conversazione, spiegazione umana e adattamento percepito.

Strategia: copiare readiness, load focus e glance veloci; superare Garmin con AI spiegabile, coach conversazionale e piano che considera vita reale.

### Strava

Strava domina su social graph, segmenti, feed, kudos e condivisione. È debole come coach.

Strategia: copiare heatmap, segmenti, social proof e shareability; superare Strava con social coaching positivo e anti-overtraining.

### Runna

Runna domina su piani consumer, UX premium e obiettivo gara. È meno forte su analytics profondi e AI contestuale.

Strategia: copiare onboarding e centralità del piano; superare Runna con adattamento giornaliero, spiegabilità e dati wearable.

### TrainingPeaks

TrainingPeaks domina su calendar, coach workflow, compliance e metriche avanzate. È meno accessibile e meno emozionale.

Strategia: copiare calendar, compliance e structured workouts; superare TrainingPeaks con AI assistant mobile-first e linguaggio semplice.

### Nike Run Club

Nike domina su guided runs, motivazione, tono di voce e beginner friendliness. È meno forte su analytics e personalizzazione profonda.

Strategia: copiare audio guided runs e momenti emozionali; superare Nike con audio coach adattivo e dati personali reali.

### Coros

Coros è forte su device, running fitness, training hub e strumenti performance. È meno forte su social, AI e storytelling.

Strategia: copiare training hub e race tools; superare Coros con coach AI narrativo e proattivo.

## Roadmap per orizzonte temporale

## Quick Wins: 1 settimana

### 1. Today Workout Card ✅ FATTO

Una card primaria nella home che dica cosa fare oggi: corsa, riposo, modifica o attenzione.

**Implementato:** `TodayWorkoutCard` in cima alla home mostra decisione dominante (icona + headline), prescrizione concreta, motivazione, chip di confidenza, safety flags sempre visibili ed espansione "Perché questa scelta?" con segnali usati, alternative e dati mancanti. Alimentata da `today_decision` nell'overview e da `GET /api/coach/today`.

- Impatto utente: 10
- Complessità tecnica: 3
- Costo: basso
- Rischio: basso
- ROI: altissimo
- Tempo stimato: 2-3 giorni

### 2. Semplificazione della home ✅ FATTO

Metriche avanzate dietro sezione Dettagli. In primo piano solo stato, decisione e motivazione.

**Implementato:** la home ora guida con la Today Workout Card (decisione + motivazione) e le azioni primarie; tutte le metriche avanzate (forma/CTL/ATL/TSB, previsione gara, HRV, streak, PR, carico settimanale) sono raccolte dietro un unico toggle "Mostra dettagli" (progressive disclosure).

- Impatto utente: 8
- Complessità tecnica: 2
- Costo: basso
- Rischio: basso
- ROI: alto
- Tempo stimato: 1-2 giorni

### 3. Coach Daily Note

Messaggio quotidiano personalizzato basato su carico, readiness, piano e ultima attività.

- Impatto utente: 8
- Complessità tecnica: 3
- Costo: basso
- Rischio: basso
- ROI: alto
- Tempo stimato: 2-3 giorni

### 4. Onboarding checklist

Percorso guidato: collega dati, imposta obiettivo, check-in, genera piano, prima raccomandazione.

- Impatto utente: 9
- Complessità tecnica: 3
- Costo: basso
- Rischio: basso
- ROI: altissimo
- Tempo stimato: 3-5 giorni

### 5. Confidence e missing data nei report AI

Ogni analisi deve indicare livello di confidenza e dati mancanti.

- Impatto utente: 8
- Complessità tecnica: 3
- Costo: basso
- Rischio: medio
- ROI: alto
- Tempo stimato: 2-4 giorni

### 6. Shoe tracking MVP

Gestione scarpe, chilometri accumulati e avviso sostituzione.

- Impatto utente: 7
- Complessità tecnica: 3
- Costo: basso
- Rischio: basso
- ROI: alto
- Tempo stimato: 3-5 giorni

## Alto impatto: 1 mese

### 7. Coach Decision Engine v1 ✅ FATTO

Output strutturato per ogni decisione: decisione, prescrizione, evidenze, confidenza, dati mancanti, alternative e safety flags.

**Implementato:** `app/processing/decision.py` (`decide_today`, funzione pura e deterministica) produce un `CoachDecision` strutturato combinando piano del giorno, readiness, rischio infortuni, TSB e ACWR. Le decisioni sono persistite come entità queryable (tabella `coach_decisions`, una per data) via `decision_service`. API: `GET /api/coach/today`, `GET /api/coach/decisions`; incluso in `/api/mobile/overview`. Rule-based per essere offline, a costo zero, testabile e spiegabile.

- Impatto utente: 10
- Complessità tecnica: 6
- Costo: medio
- Rischio: medio
- ROI: altissimo
- Tempo stimato: 3-4 settimane

### 8. Adaptive plan after sync ✅ FATTO

Dopo ogni nuova attività o check-in, il sistema valuta compliance e modifica automaticamente i prossimi 3-7 giorni.

**Implementato:** `app/services/adaptive_plan.py` (`adapt_plan_after_sync`) viene richiamato automaticamente dopo `POST /api/ingest`, `/api/ingest/cross-training` e `/api/checkin`. Ripiega i segnali live (rischio infortuni, readiness, forma, carico acuto) sui prossimi 7 giorni del piano attivo: scala il volume e, quando l'atleta è compromesso, alleggerisce le sedute di qualità imminenti. Idempotente: la prescrizione originale è salvata in colonne `base_*` e ogni run ricalcola dalla base (nessun accumulo, ripristino automatico quando i segnali migliorano). Solo sedute future e non completate entro l'orizzonte vengono toccate.

- Impatto utente: 10
- Complessità tecnica: 7
- Costo: alto
- Rischio: alto
- ROI: altissimo
- Tempo stimato: 4 settimane

### 9. Workout Execution Score

Misura quanto la seduta eseguita rispetta quella prescritta: volume, intensità, distribuzione, passo, frequenza cardiaca e RPE.

- Impatto utente: 9
- Complessità tecnica: 6
- Costo: medio
- Rischio: medio
- ROI: altissimo
- Tempo stimato: 4-6 settimane

### 10. Health Connect MVP

Importazione di attività, sonno, frequenza cardiaca e HRV da Android Health Connect.

- Impatto utente: 10
- Complessità tecnica: 7
- Costo: alto
- Rischio: medio
- ROI: altissimo
- Tempo stimato: 4-8 settimane

### 11. Race recap condivisibile

Recap post-gara con risultato, storia, strategia, cosa ha funzionato, cosa migliorare e card condivisibile.

- Impatto utente: 9
- Complessità tecnica: 5
- Costo: medio
- Rischio: basso
- ROI: altissimo
- Tempo stimato: 3-4 settimane

### 12. Calendar plan editor

Calendario con sedute spostabili e ricalcolo AI del piano.

- Impatto utente: 9
- Complessità tecnica: 7
- Costo: alto
- Rischio: medio
- ROI: alto
- Tempo stimato: 4-6 settimane

## Grandi funzionalità: 3 mesi

### 13. Live GPS tracking

Tracciamento GPS nativo da app, con split, distanza, passo, durata e salvataggio attività.

- Impatto utente: 10
- Complessità tecnica: 8
- Costo: alto
- Rischio: alto
- ROI: altissimo
- Tempo stimato: 6-10 settimane

### 14. Audio coaching live

Coach vocale durante la corsa: intervalli, split, feedback su passo, frequenza cardiaca e motivazione.

- Impatto utente: 10
- Complessità tecnica: 8
- Costo: alto
- Rischio: medio
- ROI: altissimo
- Tempo stimato: 6-10 settimane

### 15. Race Day Mode

Modalità gara con pacing, warm-up, fueling, split target, adattamento meteo e recap finale.

- Impatto utente: 10
- Complessità tecnica: 7
- Costo: alto
- Rischio: medio
- ROI: altissimo
- Tempo stimato: 6-8 settimane

### 16. Workout export

Esportazione allenamenti strutturati verso piattaforme o dispositivi supportati.

- Impatto utente: 9
- Complessità tecnica: 8
- Costo: alto
- Rischio: alto
- ROI: altissimo
- Tempo stimato: 2-3 mesi

### 17. Offline-first mobile

Cache locale, sincronizzazione differita, retry, gestione conflitti e utilizzo affidabile senza rete.

- Impatto utente: 9
- Complessità tecnica: 7
- Costo: alto
- Rischio: medio
- ROI: alto
- Tempo stimato: 6-8 settimane

### 18. Route and segment intelligence

Analisi dei percorsi ricorrenti, confronto performance, suggerimento percorso ideale per la seduta del giorno.

- Impatto utente: 8
- Complessità tecnica: 7
- Costo: alto
- Rischio: medio
- ROI: alto
- Tempo stimato: 6-8 settimane

### 19. Pain and injury workflow

Workflow non diagnostico per dolore, rischio infortunio e adattamento allenamento: localizzazione, intensità, andamento e consigli di sicurezza.

- Impatto utente: 9
- Complessità tecnica: 7
- Costo: alto
- Rischio: alto
- ROI: alto
- Tempo stimato: 6-8 settimane

## Visione: 12 mesi

### 20. iOS app e Apple Health

App iOS nativa con integrazione Apple Health per raggiungere il mercato premium.

- Impatto utente: 10
- Complessità tecnica: 10
- Costo: molto alto
- Rischio: alto
- ROI: altissimo
- Tempo stimato: 3-6 mesi

### 21. Multi-user cloud platform

Account, autenticazione, billing, storage multi-utente, isolamento dati, rate limiting e privacy center.

- Impatto utente: 10
- Complessità tecnica: 10
- Costo: molto alto
- Rischio: alto
- ROI: altissimo
- Tempo stimato: 6-12 mesi

### 22. AI plus human coach marketplace

Marketplace dove coach umani possono supervisionare o personalizzare il lavoro dell'AI.

- Impatto utente: 10
- Complessità tecnica: 10
- Costo: molto alto
- Rischio: alto
- ROI: altissimo
- Tempo stimato: 6-12 mesi

### 23. WearOS and WatchOS companion

Coach al polso: workout, split, feedback live, notifiche, check-in e race mode.

- Impatto utente: 10
- Complessità tecnica: 10
- Costo: molto alto
- Rischio: alto
- ROI: altissimo
- Tempo stimato: 4-8 mesi

### 24. Personal AI Voice Coach

Voce AI personalizzata, stile configurabile e feedback adattivo durante la corsa.

- Impatto utente: 9
- Complessità tecnica: 8
- Costo: alto
- Rischio: medio
- ROI: altissimo
- Tempo stimato: 2-3 mesi

### 25. Coach quality evaluation platform

Sistema di test con atleti sintetici e scenari reali per validare sicurezza, qualità dei piani e coerenza metodologica del coach.

- Impatto utente: 9
- Complessità tecnica: 7
- Costo: medio
- Rischio: medio
- ROI: altissimo
- Tempo stimato: 4-8 settimane

## Backlog innovativo

| # | Funzionalità | Impatto | Complessità | Costo | Rischio | ROI | Tempo stimato |
|---|---|---:|---:|---|---|---|---|
| 26 | Heat-adaptive pacing con meteo | 8 | 5 | medio | medio | alto | 3-4 settimane |
| 27 | Fueling coach per long run e maratona | 8 | 5 | medio | medio | alto | 3-4 settimane |
| 28 | Hydration and sodium planner | 8 | 6 | medio | medio | alto | 4-6 settimane |
| 29 | Psychological profile per motivazione e aderenza | 9 | 6 | medio | medio | alto | 4-6 settimane |
| 30 | Consistency contract con micro-impegni adattivi | 8 | 4 | basso | basso | alto | 2-3 settimane |
| 31 | AI season story | 8 | 5 | medio | basso | alto | 3-4 settimane |
| 32 | Social accountability circles | 9 | 8 | alto | alto | altissimo | 2-3 mesi |
| 33 | Segment intelligence avanzata | 8 | 7 | alto | medio | alto | 6-8 settimane |
| 34 | Running form insights da cadenza e dinamiche | 7 | 7 | medio | alto | medio | 6-8 settimane |
| 35 | Lactate threshold estimation engine | 9 | 7 | alto | medio | alto | 6-8 settimane |
| 36 | Durability score | 9 | 6 | medio | medio | alto | 4-6 settimane |
| 37 | Nutrition and recovery habit coach | 8 | 6 | medio | medio | alto | 4-6 settimane |
| 38 | Privacy vault and consent center | 8 | 7 | alto | medio | alto | 2-3 mesi |
| 39 | Synthetic athlete simulator | 8 | 8 | alto | medio | alto | 2-3 mesi |
| 40 | Route recommender per seduta specifica | 9 | 8 | alto | alto | altissimo | 2-3 mesi |

## Decisioni architetturali consigliate

### Breve termine

- Introdurre un modello dati per CoachDecision.
- Salvare decisioni AI come entità queryable, non solo report testuali.
- Aggiungere job asincroni per generazione piano e analisi pesanti.
- Preparare eventi interni: activity_imported, checkin_created, plan_changed, decision_created.

### Medio termine

- Mobile cache locale per overview, piani, attività e decisioni.
- Sync queue per modifiche offline.
- Notifiche push basate su eventi coach.
- Observability prodotto: activation, retention, usage delle feature.

### Lungo termine

- Separare single-user self-host da piattaforma cloud multi-user.
- Introdurre account, permessi, encryption at rest e data deletion.
- Costruire evaluation harness per coach AI.
- Preparare integrazioni wearable e workout export.

## Cosa non fare ora

- Non investire pesantemente nella dashboard web consumer.
- Non aggiungere nuove metriche in home senza trasformarle in decisioni.
- Non creare astrazioni cloud multi-user prima di validare il loop principale.
- Non aggiungere gamification generica se non produce motivazione reale.
- Non affidare sicurezza e qualità coach solo a prompt non testati.

## Ordine consigliato di implementazione

1. Today Workout Card. ✅ FATTO
2. CoachDecision schema e persistenza. ✅ FATTO
3. Decision Engine v1. ✅ FATTO
4. Coach Daily Note.
5. Adaptive plan after sync. ✅ FATTO
6. Workout Execution Score.
7. Health Connect MVP.
8. Notifiche intelligenti.
9. Race recap.
10. Audio/live coaching.

## Definizione di successo

Il progetto avrà fatto il salto quando un utente potrà dire:

- Apro l'app e so subito cosa fare oggi.
- Capisco perché il coach mi propone quella scelta.
- Se salto o sbaglio una seduta, il piano si adatta senza farmi sentire in colpa.
- Durante la corsa il coach mi guida davvero.
- Dopo la corsa ricevo un feedback utile, umano e motivante.
- Mi fido perché vedo i segnali usati e i limiti della raccomandazione.

## Conclusione

La base tecnica è già solida. La prossima fase non deve aggiungere semplicemente feature, ma cambiare il centro di gravità del prodotto: da analisi delle corse a coaching quotidiano adattivo.

Le tre iniziative con massimo ritorno strategico sono:

1. Today Workout Card.
2. Coach Decision Engine strutturato.
3. Adaptive plan after sync.

Queste trasformano l'app da archivio intelligente a coach operativo.
