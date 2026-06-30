# Feature Gap Analysis — AI Running Coach
**Obiettivo:** 500M download nel settore running/fitness  
**Benchmark:** Strava (120M utenti), Garmin Connect (40M), Nike Run Club (50M+), Runna (top paid app)  
**Ultimo aggiornamento:** 2026-06-28

---

## Stato implementazione rapido

| Simbolo | Significato |
|---------|-------------|
| ✅ | Implementata e in produzione |
| 🔄 | In corso (branch attivo) |
| 📋 | Da fare |

---

## Cosa ha già l'app (base + feature implementate)

✅ Sync Garmin automatico + demo mode (offline, zero credenziali)  
✅ Fitness/Fatigue model (CTL/ATL/TSB + ACWR + monotonia carico)  
✅ AI coaching con Claude (analisi singola corsa + piano settimanale)  
✅ Rischio infortunio composite (0–100, multi-fattore)  
✅ Zone FC, splits al km, training effect numerico, VO2max  
✅ Periodizzazione automatica (Base → Build → Specifico → Peak → Taper → Race)  
✅ Previsione gara con probabilità e intervallo di confidenza  
✅ Daily check-in readiness (sonno, fatica, dolori, motivazione)  
✅ Trail metrics (VAM, equivalent flat km, D+/D−)  
✅ Dashboard web (HTMX/Jinja) + app Android nativa (Jetpack Compose)  
✅ **Strava sync event-driven** (OAuth 2.0 + webhook push, nessun polling)  
✅ **Mappa OSM per ogni attività** (osmdroid, tile Mapnik, start/finish dots, fullscreen interattivo)  
✅ **Profilo altitudine + passo overlay** (Garmin/Strava-style, Canvas Compose)  
✅ **RPE editabile + note editabili** per ogni attività  
✅ **Personal Records automatici** (1K/5K/10K/21K/42K, badge NEW PR)  
✅ **Streak + Badge/Milestones** (streak corrente, achievement sbloccati)  
✅ **Color coding intensità** nelle liste attività (verde→rosso per zona)  
✅ **Dark mode** (segue sistema, selezionabile manualmente)  
✅ **Widget home screen** (Jetpack Glance, TSB + forma + km settimana)  
✅ **Statistiche annuali/mensili** (distanza, dislivello, ore, numero corse)  
✅ **Export dati CSV/JSON** (share sheet nativa Android)  
✅ **Piani multi-settimana strutturati** (Runna-grade: 8–20 settimane, fasi periodizzate, check-off sessioni, countdown gara)  
✅ **Workout builder visuale** (tab Builder + Libreria, AI suggest, segment espandibili, stima distanza/durata)  

---

## TIER 1 — Immediati (ore / 1–2 giorni)
*Quick wins con alto impatto utente. Zero dipendenze esterne.*

### ✅ 1. Personal Records (PR) automatici
**Perché:** Prima cosa che un runner vuole vedere. Nike Run Club ha costruito metà della retention su questo.  
**Implementato:** `GET /api/personal-records` per distanze canoniche (1K, 5K, 10K, 21K, 42K). Badge "NEW PR" sulle ActivityRow. Visibile in HomeScreen e ActivityDetailScreen.

---

### ✅ 2. Streak e Badge/Milestones
**Perché:** Gamification = retention. Strava ha rivelato che gli utenti con streak attive churnan il 60% meno.  
**Implementato:** `GET /api/gamification` → streak corrente, total badges, recent unlocks. Badge gallery in HomeScreen con pill colorata streak.

---

### ✅ 3. Effort-based color coding nelle liste
**Perché:** UX immediata. Un runner capisce in 1 secondo la settimana guardando i colori.  
**Implementato:** Pill tipo attività colorata per zona intensità (verde=easy, giallo=medio, arancio=tempo, rosso=intervalli/gara) in tutte le ActivityRow.

---

### ✅ 4. Dark mode
**Perché:** Top-1 feature request di qualsiasi app mobile. Critico per chi corre di mattina presto o di sera.  
**Implementato:** `MaterialTheme` con `darkColorScheme`, segue sistema di default, selezionabile manualmente in Impostazioni (light/dark/system).

---

### ✅ 5. Widget home screen Android
**Perché:** La forma del giorno visibile senza aprire l'app = DAU elevatissimo. Garmin Connect ha widget TSB.  
**Implementato:** `GlanceAppWidget` con TSB, forma (fresh/balanced/fatigued/detraining), km settimana. Si aggiorna ad ogni sync.

---

### ✅ 6. Schermata Statistiche annuali / "Year in Review"
**Perché:** Strava's "Year in Review" genera milioni di condivisioni organiche ogni dicembre — marketing gratis.  
**Implementato:** `GET /api/stats?period=year|month|all-time`. StatsScreen con cards distanza/dislivello/ore/corse. Esportabile.

---

### ✅ 7. Export dati (CSV/JSON)
**Perché:** Trust builder. Gli utenti che sanno di poter esportare i propri dati sono più disposti a inserirne di nuovi.  
**Implementato:** Export CSV e JSON via share sheet Android. Accessibile da StatsScreen e SettingsScreen.

---

## TIER 2 — Breve termine (1–2 settimane)
*Feature con impatto medio-alto. Richiedono più lavoro ma nessuna infrastruttura nuova.*

### 📋 8. Trend VO2max nel tempo
**Perché:** Il numero che i runner ossessionano più di qualsiasi altro. Garmin lo mostra, ma male. Farlo meglio = differenziazione.  
**Cosa manca:** VO2max è già nel DB per ogni attività ma non c'è nessun grafico trend.  
**Implementazione:**
- Backend: `GET /api/vo2max/history` → lista `(date, vo2max)` da activities ordinate per data
- Android: grafico lineare in StatsScreen/HomeScreen con trend annotation ("In miglioramento ↑")
- **Effort:** 1 giorno

---

### 📋 9. Vista calendario mensile
**Perché:** Strava ha rimosso il calendario e ne hanno sentito la mancanza. I runner visualizzano il training in modo lineare nel tempo.  
**Cosa manca:** Solo lista, nessuna vista temporale.  
**Implementazione:**
- Android: CalendarScreen con `LazyVerticalGrid` 7 colonne, dot colorato per ogni giorno con run, tap → lista runs del giorno
- Backend: già ha dati sufficienti (activities con date)
- **Effort:** 2–3 giorni

---

### 📋 10. Tracking scarpe da corsa
**Perché:** Feature cult tra runner seri. Hoka/Asics consigliano di cambiare ogni 700–800km. Genera conversioni affiliate.  
**Cosa manca:** Nessun tracking scarpe.  
**Implementazione:**
- Backend: tabella `shoes` (brand, model, buy_date, retirement_km), FK activity→shoe, `GET /api/shoes`, `POST /api/shoes`
- Android: ShoesScreen con mileage bar + alert "scarpa vicina al limite (650/800 km)"
- **Effort:** 3–4 giorni

---

### 📋 11. Notifiche push intelligenti
**Perché:** Ogni app top-tier usa le notifiche per retention. Un coach che ti avvisa è 10x più sticky di uno che aspetti tu ad aprire.  
**Cosa manca:** Nessuna notifica push.  
**Implementazione:**
- Android: WorkManager per notifiche locali periodiche: "Analisi pronta", "Ricorda il check-in", "Oggi è giorno di recupero (TSB basso)", "PR battuto!"
- Backend: nessuna modifica necessaria (notifiche locali Android sufficienti)
- **Effort:** 2–3 giorni

---

### ✅ 12. Piani di allenamento strutturati multi-settimana
**Perché:** Runna (solo piani strutturati) vale decine di milioni. È LA killer feature per convertire da free a paid.  
**Implementato:** Tabelle `training_plans` / `training_plan_weeks` / `training_plan_sessions`. Claude genera piano completo 8–20 settimane con fasi periodizzate (Base→Build→Specifico→Taper→Race). Fallback offline deterministico (10% rule, cutback ogni 4a settimana, taper 40–50%). API REST: `POST /api/plan/generate`, `GET /api/plan/current`, `GET /api/plan/{id}`, `PATCH /api/plan/sessions/{id}/complete`, `DELETE /api/plan/{id}`. PlanScreen Android: RaceCountdownCard, sessioni settimanali con check-off, vista piano collassabile, GeneratePlanDialog.

---

### 📋 13. Analisi post-gara dedicata
**Perché:** La gara è il momento di picco emotivo di un runner. Un'analisi dettagliata in quel momento = virality.  
**Cosa manca:** L'analisi è generica per tutti i tipi di attività; la gara non ha un flusso dedicato.  
**Implementazione:**
- Backend: in `analyze_run`, se `activity_type == "gara"` → prompt speciale con splits negativi/positivi, confronto prediction pre-gara, cosa migliorare per la prossima
- Android: RaceResultScreen con storytelling visuale (andatura per km, confronto predetto vs reale)
- **Effort:** 3–4 giorni

---

### 📋 14. Confronto corse sullo stesso percorso (Segment-style)
**Perché:** "Quanto sono andato più veloce rispetto all'ultima volta su questa salita?" — questo è il motore di Strava.  
**Cosa manca:** Nessun sistema di segmenti o confronto percorso.  
**Implementazione:**
- Backend: clustering per distanza+dislivello simile come proxy percorso, `GET /api/activities/similar?activity_id=X` → corse simili ordinate per pace
- Android: nel ActivityDetail, sezione "Corse simili" con confronto passo
- **Effort:** 3–4 giorni (heuristic, senza GPS parsing)

---

### 📋 15. Integrazione salute (Google Health Connect)
**Perché:** Molti runner non hanno Garmin. Allargare la base utenti a chi usa watch diversi è +10x TAM.  
**Cosa manca:** Solo Garmin o Strava. Chi usa Apple Watch, Polar, Suunto, Fitbit non può usare l'app.  
**Implementazione:**
- Android: Health Connect API (unica API unificata Android per tutti i wearable) → importa corse, FC, sonno
- Backend: nuovo `HealthConnectSource` che implementa il protocollo `ActivitySource`
- **Effort:** 1–2 settimane

---

## TIER 3 — Medio termine (1–2 mesi)
*Feature strategiche. Richiedono infrastruttura nuova o integrazione complessa.*

### 📋 16. HRV + readiness oggettiva
**Perché:** WHOOP ha costruito un'azienda da 3.6B$ solo su HRV + readiness. Garmin la misura, ma non la spiega bene.  
**Cosa manca:** Nessun HRV. La readiness usa solo check-in soggettivo.  
**Implementazione:**
- Garmin già espone HRV summary: `get_hrv_data(date)` → HRV LF/HF
- Backend: estendi `DailyCheckin` con `hrv_rmssd`, rivedi formula readiness per includere HRV come segnale obiettivo
- Android: HRV trend card in HomeScreen con spiegazione plain-language
- **Effort:** 1–2 settimane

---

### ✅ 17. Interval/Workout builder visuale
**Perché:** Running coach paid (Runna, TrainingPeaks) vendono per la struttura. Un workout builder libero + AI generation = differenziazione.  
**Implementato:** Tabelle `workout_templates`/`workout_segments`. `Coach.suggest_workout()` genera template via Claude (JSON puro) con fallback offline deterministico (intervals/tempo/long/strides/easy, passo calibrato per livello). API REST: `POST /api/workouts`, `GET /api/workouts`, `GET /api/workouts/{id}`, `DELETE /api/workouts/{id}`, `POST /api/workouts/suggest`. Stima automatica distanza e durata per ogni template. Android: `WorkoutScreen` con tab Builder + Libreria, `SegmentCard` espandibile (ripetizioni, distanza/durata, passo, recupero), AI suggest integrato, navigazione da PlanScreen. 22 test di integrazione.

---

### 📋 18. Mappa heatmap di tutte le corse
**Perché:** La heatmap Strava è uno dei contenuti più condivisi su Instagram dai runner. Virality gratuita.  
**Nota:** La mappa OSM per singola attività è già implementata (Feature Tier-1 bonus). Manca la heatmap aggregata.  
**Cosa manca:** Aggregazione di tutte le tracce GPS in un'unica MapScreen con overlay termico.  
**Implementazione:**
- Backend: `GET /api/activities/heatmap` → GeoJSON con tutte le polilinee
- Android: MapScreen dedicata con osmdroid + polyline overlay (heatmap effect con opacity variabile per densità)
- **Effort:** 2–3 settimane (osmdroid già in progetto, nessuna nuova dipendenza)

---

### 📋 19. Live GPS tracking durante la corsa
**Perché:** La maggior parte degli utenti non ha Garmin. Usare il telefono come tracker = acquisire utenti senza wearable.  
**Cosa manca:** L'app è post-hoc (sync dopo la corsa). Nessun tracking live.  
**Implementazione:**
- Android: foreground service GPS, `LocationManager` con sampling ogni 5s, salvataggio traccia locale, upload al termine
- Backend: endpoint per ricevere tracce e sintetizzare splits/km via `upsert_activity`
- **Effort:** 3–4 settimane

---

### 📋 20. Audio coaching durante la corsa (voice feedback + interval timer)
**Perché:** Nike Run Club ha costruito la sua fanbase su guided runs. Running con audio > running in silenzio per retention.  
**Nota:** Il workout builder (Feature 17) genera la struttura dell'allenamento; questa feature la esegue in tempo reale.  
**Cosa manca:** Nessuna interazione real-time durante la corsa.  
**Implementazione:**
- Android: `TextToSpeech` per annunci ai km (passo, FC, tempo trascorso) + timer interval che usa template da Feature 17
- Dipende da: Feature 17 (workout builder) + Feature 19 (GPS tracking)
- **Effort:** 3–4 settimane

---

### 📋 21. Feature sociali (condivisione + amici)
**Perché:** Strava ha vinto sul social. Il network effect è il moat più forte nel fitness.  
**Cosa manca:** Nessuna funzionalità social, nessun multi-user.  
**Implementazione:**
- Backend: tabella `users`, `follows`, `kudos`; `POST /api/share/activity` → genera immagine PNG shareable
- Android: share sheet con immagine auto-generata; feed amici opzionale
- **Effort:** 3–6 settimane (con infrastruttura multi-user)

---

### 📋 22. iOS app
**Perché:** In Europa e USA il mercato iOS pesa il 50–60% dei download di app fitness premium. Assenza = perdita di metà TAM.  
**Cosa manca:** Solo Android.  
**Nota:** Il backend REST è già pronto e completo. Solo il frontend è da fare.  
**Implementazione:**
- Swift/SwiftUI nativa oppure Flutter condividendo la logica UI
- **Effort:** 4–8 settimane (nativa) / 2–3 settimane (Flutter)

---

## TIER 4 — Grandi feature (3+ mesi)
*Feature trasformative che cambiano la categoria. Alta complessità, altissimo impatto.*

### ✅ 23. Coach AI conversazionale (chat con memoria)
**Perché:** Chatbot coaching 24/7 = differenziazione massima vs Strava/Garmin. Claude è perfetto per questo.  
**Implementato:**
- Backend: `chat_sessions` + `chat_messages` (SQLite, migrazione `c5d6e7f8`); `POST /api/chat/send`, `GET /api/chat/sessions`, `GET /api/chat/{id}/messages`, `DELETE /api/chat/{id}`
- Routing intelligente: Haiku classifica la complessità → `simple` (Haiku) / `medium` (Sonnet) / `complex` (Opus); in dev tutti Haiku
- System prompt contestuale: metriche CTL/ATL/TSB, ultime 10 corse, piano attivo
- Sessioni persistenti con titolo auto-generato dal primo messaggio
- Android: `ChatScreen` (bubble UI, tier chip), `ChatViewModel`, tab "Coach" nella NavigationBar

---

### 📋 24. Multi-sport (ciclismo, nuoto, forza, yoga)
**Perché:** Garmin Connect copre 100+ sport. Il runner medio fa anche bike e palestra. App single-sport perdono utenti.  
**Cosa manca:** Solo running. Ciclismo/nuoto richiedono metriche diverse (potenza, SWOLF).  
**Effort:** 2–3 mesi

---

### 📋 25. Companion app per smartwatch (WearOS / watchOS)
**Perché:** L'utente vuole il coaching sul polso, non solo sul telefono.  
**Cosa manca:** Nessuna app watch.  
**Effort:** 2–3 mesi (WearOS) + 2–3 mesi (watchOS)

---

### 📋 26. Marketplace coach umani + AI ibrido
**Perché:** Modello business da $40–150/mese per atleta. Runna costa $18/mese, TrainingPeaks $19/mese. Con coach umano il valore percepito è 3–5x.  
**Cosa manca:** Tutto. Multi-tenancy, pagamenti, dashboard coach.  
**Effort:** 4–6 mesi

---

## Riepilogo priorità aggiornato

| # | Feature | Stato | Impatto | Effort | Tier |
|---|---------|--------|---------|--------|------|
| 1 | Personal Records prominenti | ✅ | Alto | 1–2 gg | 1 |
| 2 | Streak + Badge | ✅ | Alto | 1 gg | 1 |
| 3 | Color coding intensità | ✅ | Medio | 2 ore | 1 |
| 4 | Dark mode | ✅ | Medio | 4 ore | 1 |
| 5 | Widget home screen | ✅ | Alto | 1 gg | 1 |
| 6 | Stats annuali / Year in Review | ✅ | Alto | 1 gg | 1 |
| 7 | Export CSV/JSON | ✅ | Medio | 4 ore | 1 |
| 8 | Trend VO2max | 📋 | Alto | 1 gg | 2 |
| 9 | Vista calendario | 📋 | Alto | 2–3 gg | 2 |
| 10 | Tracking scarpe | 📋 | Medio | 3–4 gg | 2 |
| 11 | Notifiche push | 📋 | Alto | 2–3 gg | 2 |
| 12 | Piani multi-settimana | ✅ | Altissimo | 1–2 sett | 2 |
| 13 | Analisi gara dedicata | 📋 | Alto | 3–4 gg | 2 |
| 14 | Confronto corse simili | 📋 | Alto | 3–4 gg | 2 |
| 15 | Health Connect (Android) | 📋 | Altissimo | 1–2 sett | 2 |
| 16 | HRV + readiness oggettiva | 📋 | Alto | 1–2 sett | 3 |
| 17 | Interval/Workout builder | ✅ | Alto | 2–3 sett | 3 |
| 18 | Mappa heatmap aggregata | 📋 | Altissimo | 2–3 sett | 3 |
| 19 | Live GPS tracking | 📋 | Altissimo | 3–4 sett | 3 |
| 20 | Audio coaching durante corsa | 📋 | Altissimo | 3–4 sett | 3 |
| 21 | Feature sociali + condivisione | 📋 | Altissimo | 4–6 sett | 3 |
| 22 | iOS app | 📋 | Altissimo | 4–8 sett | 3 |
| 23 | Chat AI conversazionale | ✅ | Altissimo | 3–4 sett | 4 |
| 24 | Multi-sport | 📋 | Alto | 2–3 mesi | 4 |
| 25 | WearOS / watchOS app | 📋 | Alto | 2–3 mesi | 4 |
| 26 | Marketplace coach umani | 📋 | Altissimo | 4–6 mesi | 4 |

**Implementate: 10/26 feature (tutte e 7 del Tier 1 + Feature 12 Tier 2 + Feature 17 Tier 3)**

---

## Feature bonus implementate (non nel roadmap originale)

Queste feature sono state aggiunte al di fuori del roadmap originale durante lo sviluppo:

| Feature | Dettaglio |
|---------|-----------|
| ✅ Strava sync event-driven | OAuth 2.0 + webhook push subscriptions. Nessun polling. Attività arrivano in tempo reale, come Garmin → Strava. |
| ✅ Mappa OSM per attività | Mappa OpenStreetMap (osmdroid) nella schermata attività con start/finish dots, fullscreen interattivo con pinch-to-zoom. |
| ✅ Profilo altitudine + passo | Grafico combinato elevation area + pace line overlay sullo stesso asse X, Garmin/Strava-style. |
| ✅ RPE editabile | Slider 1–10 per modificare lo sforzo percepito direttamente dalla schermata attività. |
| ✅ Note editabili | Campo note inline con save/annulla, persistito via `PATCH /api/activities/{id}`. |
| ✅ Confronto passo obiettivo | Card che confronta passo medio effettivo vs passo gara obiettivo (calcolato da goal_type + target_time). |
| ✅ Splits Strava-style | Tabella parziali con barre relative (verde = più veloce, rosso = più lento) + delta dislivello per km. |

---

## I 5 "unlock" da 500M download (invariati)

Se dovessi scegliere le 5 feature che fanno la differenza tra "app carina per smanettoni" e "app mainstream con virality":

1. **iOS app** — senza iOS perdi metà del mercato premium
2. **Health Connect** — svincolarsi da Garmin è il TAM più grande della lista
3. **Live GPS + audio coaching** — trasforma l'app da "archivio" a "compagno di corsa"
4. **Piani strutturati multi-settimana** — l'unica feature per cui i runner pagano davvero (vedi Runna) ✅ **FATTO**
5. **Feature social + condivisione immagini** — il flywheel di crescita organica (Strava insegna)
