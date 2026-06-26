# Feature Gap Analysis — AI Running Coach
**Obiettivo:** 500M download nel settore running/fitness  
**Benchmark:** Strava (120M utenti), Garmin Connect (40M), Nike Run Club (50M+), Runna (top paid app)  
**Data analisi:** 2026-06-26

---

## Cosa ha già l'app (sintesi)

✅ Sync Garmin + demo mode  
✅ Fitness/Fatigue model (CTL/ATL/TSB + ACWR)  
✅ AI coaching con Claude (analisi + piano settimanale)  
✅ Rischio infortunio composite (0–100)  
✅ Zone FC, splits, training effect, VO2max  
✅ Periodizzazione (Base→Build→Taper→Race)  
✅ Previsione gara con probabilità  
✅ Daily check-in readiness  
✅ Trail metrics (VAM, equivalent flat km)  
✅ Dashboard web + app Android nativa  

---

## TIER 1 — Immediati (ore / 1–2 giorni)
*Quick wins con alto impatto utente. Zero dipendenze esterne.*

### 1. Personal Records (PR) automatici
**Perché:** Prima cosa che un runner vuole vedere. Nike Run Club ha costruito metà della retention su questo.  
**Cosa manca:** L'app calcola best efforts in snapshot (5K/10K/half/full) ma non li mostra in modo prominente, non li evidenzia quando vengono battuti durante la sync, e non tiene track del trend storico PR.  
**Implementazione:**
- Backend: `GET /api/personal-records` → estrai PR da DB per distanze canoniche (1K, 5K, 10K, 21K, 42K) + custom
- Notifica nel CoachingResult quando un PR viene battuto durante ingest
- Android: schermata PRScreen + badge visuale "NEW PR" sulla ActivityRow quando applicabile
- **Effort:** 1–2 giorni

---

### 2. Streak e Badge/Milestones
**Perché:** Gamification = retention. Strava ha rivelato che gli utenti con streak attive churnan il 60% meno.  
**Cosa manca:** Nessun sistema di streak o achievement.  
**Implementazione:**
- Backend: calcolo streak corrente (giorni/settimane consecutive con almeno 1 run), lista badge sbloccati (primo run, 100km totali, 500km, 1000km, prima gara, prima corsa trail, 30-day streak, ecc.)
- `GET /api/gamification` → streak, total_badges, recent_unlocks
- Android: sezione nella HomeScreen con streak pill + badge gallery
- **Effort:** 1 giorno

---

### 3. Effort-based color coding nelle liste
**Perché:** UX immediata. Un runner capisce in 1 secondo la settimana guardando i colori.  
**Cosa manca:** Le ActivityRow mostrano solo testo; nessuna distinzione visiva per intensità.  
**Implementazione:**
- Android: colora la pill del tipo attività per zona intensità (verde=easy, giallo=medio, arancio=tempo, rosso=intervalli/gara)
- Usa `activity_type` già presente nel modello
- **Effort:** 2 ore

---

### 4. Dark mode
**Perché:** Top-1 feature request di qualsiasi app mobile. Critico per chi corre di mattina presto o di sera.  
**Cosa manca:** L'app usa il tema Material 3 di base, non ha dark mode esplicita.  
**Implementazione:**
- Android: `MaterialTheme` con `darkColorScheme` + follow system setting
- **Effort:** 4 ore

---

### 5. Widget home screen Android
**Perché:** La forma del giorno visibile senza aprire l'app = DAU elevatissimo. Garmin Connect ha widget TSB.  
**Cosa manca:** Nessun widget.  
**Implementazione:**
- Android: `GlanceAppWidget` (Jetpack Glance) con TSB, forma (form state), km settimana
- Aggiorna ogni sync o ogni ora
- **Effort:** 1 giorno

---

### 6. Schermata Statistiche annuali / "Year in Review"
**Perché:** Strava's "Year in Review" genera milioni di condivisioni organiche ogni dicembre — marketing gratis.  
**Cosa manca:** Nessun summary annuale/mensile.  
**Implementazione:**
- Backend: `GET /api/stats?period=year|month|all-time` → totali distanza, dislivello, ore, numero corse, PR del periodo
- Android: StatsScreen con cards grafiche shareable
- **Effort:** 1 giorno

---

### 7. Export dati (CSV/JSON)
**Perché:** Trust builder. Gli utenti che sanno di poter esportare i propri dati sono più disposti a inserirne di nuovi.  
**Cosa manca:** Nessun export.  
**Implementazione:**
- Backend: `GET /api/export?format=csv|json` → download activities
- Android: share sheet con file CSV
- **Effort:** 4 ore

---

## TIER 2 — Breve termine (1–2 settimane)
*Feature con impatto medio-alto. Richiedono più lavoro ma nessuna infrastruttura nuova.*

### 8. Trend VO2max nel tempo
**Perché:** Il numero che i runner ossessionano più di qualsiasi altro. Garmin lo mostra, ma male. Farlo meglio = differenziazione.  
**Cosa manca:** VO2max è già nel DB ma non c'è nessun grafico trend.  
**Implementazione:**
- Backend: `GET /api/vo2max/history` → lista (date, vo2max) da activities
- Android: grafico lineare nella HomeScreen/StatsScreen con trend e annotation "In miglioramento"
- **Effort:** 1 giorno

---

### 9. Vista calendario mensile
**Perché:** Strava ha rimosso il calendario e ne hanno sentito la mancanza. I runner visualizzano il training in modo lineare nel tempo.  
**Cosa manca:** Solo lista, nessuna vista temporale.  
**Implementazione:**
- Android: CalendarScreen con `LazyVerticalGrid` 7 colonne, dot colorato per ogni giorno con run, tap → lista runs del giorno
- Backend: già ha dati sufficienti
- **Effort:** 2–3 giorni

---

### 10. Tracking scarpe da corsa
**Perché:** Feature cult tra runner seri. Hoka/Asics consigliano di cambiare ogni 700–800km. Genera conversioni affiliate.  
**Cosa manca:** Nessun tracking scarpe.  
**Implementazione:**
- Backend: tabella `shoes` (brand, model, buy_date, retirement_km), FK activity→shoe, `GET /api/shoes`, `POST /api/shoes`, upsert attività con shoe_id
- Android: ShoesScreen con mileage bar + alert "scarpa vicina al limite"
- **Effort:** 3–4 giorni

---

### 11. Notifiche push intelligenti
**Perché:** Ogni app top-tier usa le notifiche per retention. Un coach che ti avvisa è 10x più sticky di uno che aspetti tu ad aprire.  
**Cosa manca:** Nessuna notifica push.  
**Implementazione:**
- Android: FCM / WorkManager per notifiche locali: "Analisi pronta", "Ricorda il check-in", "Oggi è giorno di recupero (TSB basso)", "PR battuto!"
- Backend: no modifiche necessarie (notifiche locali su Android sufficienti)
- **Effort:** 2–3 giorni

---

### 12. Piani di allenamento strutturati multi-settimana
**Perché:** Runna (solo piani strutturati) vale decine di milioni. È LA killer feature per convertire da free a paid.  
**Cosa manca:** L'app genera piani settimanali on-demand ma non piani multi-settimana persistenti e tracciabili (tipo "Piano 16 settimane per la maratona").  
**Implementazione:**
- Backend: tabella `training_plans` con settimane/sessioni pianificate; `POST /api/plan/generate` con obiettivo+data gara → Claude genera piano completo 8–20 settimane; `GET /api/plan/current` → sessioni della settimana corrente
- Android: PlanScreen con view settimanale, check-off sessioni completate, progress bar verso gara
- **Effort:** 1–2 settimane

---

### 13. Analisi post-gara dedicata
**Perché:** La gara è il momento di picco emotivo di un runner. Un'analisi dettagliata in quel momento = virality.  
**Cosa manca:** L'analisi è generica per tutti i tipi di attività; la gara non ha un flusso dedicato.  
**Implementazione:**
- Backend: in `analyze_run`, se `activity_type == "gara"` → prompt speciale con: splits negativi/positivi, confronto con prediction pre-gara, cosa migliorare per la prossima
- Android: RaceResultScreen con storytelling visuale (andatura per km, confronto predetto vs reale)
- **Effort:** 3–4 giorni

---

### 14. Confronto corse sullo stesso percorso (Segment-style)
**Perché:** "Quanto sono andato più veloce rispetto all'ultima volta su questa salita?" — questo è il motore di Strava.  
**Cosa manca:** Nessun sistema di segmenti o confronto percorso.  
**Implementazione:**
- Backend: clustering semplice per distanza+dislivello simile come proxy percorso (senza GPS), `GET /api/activities/similar?activity_id=X` → corse simili ordinate per pace
- Android: nel ActivityDetail, sezione "Corse simili" con confronto passo
- **Effort:** 3–4 giorni (senza GPS parsing, solo heuristic)

---

### 15. Integrazione salute (Google Health Connect)
**Perché:** Molti runner non hanno Garmin. Allargare la base utenti a chi usa watch diversi è +10x TAM.  
**Cosa manca:** Solo Garmin o input manuale.  
**Implementazione:**
- Android: Health Connect API (unica API unificata Android per tutti i wearable) → importa corse, FC, sonno
- Backend: nuovo `HealthConnectSource` che implementa `ActivitySource`
- **Effort:** 1–2 settimane

---

## TIER 3 — Medio termine (1–2 mesi)
*Feature strategiche. Richiedono infrastruttura nuova o integrazione complessa.*

### 16. HRV + readiness oggettiva
**Perché:** WHOOP ha costruito un'azienda da 3.6B$ solo su HRV + readiness. Garmin la misura, ma non la spiega bene.  
**Cosa manca:** Nessun HRV. La readiness usa solo check-in soggettivo.  
**Implementazione:**
- Garmin già espone HRV summary: `get_hrv_data(date)` → HRV LF/HF
- Backend: estendi `DailyCheckin` con `hrv_rmssd`, rivedi `readiness` per includere HRV come segnale obiettivo
- Android: HRV trend card in HomeScreen
- **Effort:** 1–2 settimane

---

### 17. Interval/Workout builder visuale
**Perché:** Running coach paid (Runna, TrainingPeaks) vendono per la struttura. Un workout builder libero + AI generation = differenziazione.  
**Cosa manca:** Si possono solo inserire attività passate, non pianificare sessioni strutturate future.  
**Implementazione:**
- Android: drag-and-drop workout builder (warmup → n×(work+rest) → cooldown)
- Backend: `POST /api/workouts` → salva workout template; AI può suggerire "Ti propongo questo: 3×2km @ 4:30/km"
- **Effort:** 2–3 settimane

---

### 18. Mappa delle corse (Heatmap)
**Perché:** La heatmap Strava è uno dei contenuti più condivisi su Instagram dai runner. Virality gratuita.  
**Cosa manca:** Nessuna visualizzazione geografica.  
**Implementazione:**
- Garmin espone coordinate GPX via `download_activity(id, ActivityDownloadFormat.GPX)`
- Backend: parse GPX → polilinee JSON; `GET /api/activities/{id}/route` → GeoJSON
- Android: MapScreen con MapBox/Google Maps + overlay heatmap
- **Effort:** 3–4 settimane

---

### 19. Live GPS tracking durante la corsa
**Perché:** La maggior parte degli utenti non ha Garmin. Usare il telefono come tracker = acquisire utenti senza wearable.  
**Cosa manca:** L'app è post-hoc (sync dopo la corsa). Nessun tracking live.  
**Implementazione:**
- Android: foreground service GPS, `LocationManager` con sampling ogni 5s, salvataggio traccia GPX locale, upload al termine
- Backend: endpoint per ricevere tracce GPX e sintetizzare splits/km
- **Effort:** 3–4 settimane

---

### 20. Audio coaching durante la corsa (voice feedback + interval timer)
**Perché:** Nike Run Club ha costruito la sua fanbase su guided runs. Running con audio > running in silenzio per retention.  
**Cosa manca:** Nessuna interazione real-time.  
**Implementazione:**
- Android: `TextToSpeech` per annunci ai km (passo, FC, tempo trascorso) + supporto sessioni interval (beep tra rest/work)
- Workout builder: UI per creare sessioni tipo "6x1km @ soglia con 90s recupero"
- Backend: `POST /api/workouts/interval` → genera struttura sessione
- **Effort:** 3–4 settimane

---

### 21. Feature sociali (condivisione + amici)
**Perché:** Strava ha vinto sul social. Il network effect è il moat più forte nel fitness.  
**Cosa manca:** Nessuna funzionalità social.  
**Implementazione:**
- Backend: tabella `users`, `follows`, `kudos`; `POST /api/share/activity` → genera immagine PNG shareable con stats
- Android: share sheet con immagine auto-generata; feed amici
- **Effort:** 3–6 settimane (con infrastruttura multi-user)

---

### 22. iOS app
**Perché:** In Europa e USA il mercato iOS pesa il 50–60% dei download di app fitness premium. Assenza = perdita di metà TAM.  
**Cosa manca:** Solo Android.  
**Implementazione:**
- Swift/SwiftUI nativa oppure Flutter condividendo logica
- Backend già pronto (API REST completa)
- **Effort:** 4–8 settimane (nativa) / 2–3 settimane (Flutter)

---

## TIER 4 — Grandi feature (3+ mesi)
*Feature trasformative che cambiano la categoria. Alta complessità, altissimo impatto.*

### 23. Coach AI conversazionale (chat con memoria)
**Perché:** Chatbot coaching 24/7 = differenziazione massima vs Strava/Garmin. Claude è perfetto per questo.  
**Cosa manca:** L'AI genera analisi one-shot; nessuna sessione conversazionale con contesto persistente.  
**Implementazione:**
- Backend: tabella `chat_sessions`; endpoint `POST /api/chat` → Claude API con history + tool use (accesso metriche in real-time)
- Android: ChatScreen con bubble UI
- **Effort:** 3–4 settimane (solo chat) / 2–3 mesi (con tool use + memory completa)

---

### 24. Multi-sport (ciclismo, nuoto, forza, yoga)
**Perché:** Garmin Connect copre 100+ sport. Il runner medio fa anche bike e palestra. App single-sport perdono utenti.  
**Cosa manca:** Solo running. Ciclismo/nuoto richiedono metriche diverse (potenza, SWOLF).  
**Effort:** 2–3 mesi

---

### 25. Companion app per smartwatch (WearOS / watchOS)
**Perché:** L'utente vuole il coaching sul polso, non solo sul telefono.  
**Cosa manca:** Nessuna app watch.  
**Effort:** 2–3 mesi (WearOS) + 2–3 mesi (watchOS)

---

### 26. Marketplace coach umani + AI ibrido
**Perché:** Modello business da $40–150/mese per atleta. Runna costa $18/mese, TrainingPeaks $19/mese. Con coach umano il valore percepito è 3–5x.  
**Cosa manca:** Tutto. Multi-tenancy, pagamenti, dashboard coach.  
**Effort:** 4–6 mesi

---

## Riepilogo priorità

| # | Feature | Impatto | Effort | Tier |
|---|---------|---------|--------|------|
| 1 | Personal Records prominenti | Alto | 1–2 gg | 1 |
| 2 | Streak + Badge | Alto | 1 gg | 1 |
| 3 | Dark mode | Medio | 4 ore | 1 |
| 4 | Widget home screen | Alto | 1 gg | 1 |
| 5 | Color coding intensità | Medio | 2 ore | 1 |
| 6 | Stats annuali / Year in Review | Alto | 1 gg | 1 |
| 7 | Export CSV/JSON | Medio | 4 ore | 1 |
| 8 | Trend VO2max | Alto | 1 gg | 2 |
| 9 | Vista calendario | Alto | 2–3 gg | 2 |
| 10 | Tracking scarpe | Medio | 3–4 gg | 2 |
| 11 | Notifiche push | Alto | 2–3 gg | 2 |
| 12 | Piani multi-settimana | Altissimo | 1–2 sett | 2 |
| 13 | Analisi gara dedicata | Alto | 3–4 gg | 2 |
| 14 | Confronto corse simili | Alto | 3–4 gg | 2 |
| 15 | Health Connect (Android) | Altissimo | 1–2 sett | 2 |
| 16 | HRV + readiness oggettiva | Alto | 1–2 sett | 3 |
| 17 | Interval/Workout builder | Alto | 2–3 sett | 3 |
| 18 | Mappa + Heatmap | Altissimo | 3–4 sett | 3 |
| 19 | Live GPS tracking | Altissimo | 3–4 sett | 3 |
| 20 | Audio coaching durante corsa | Altissimo | 3–4 sett | 3 |
| 21 | Feature sociali + condivisione | Altissimo | 4–6 sett | 3 |
| 22 | iOS app | Altissimo | 4–8 sett | 3 |
| 23 | Chat AI conversazionale | Altissimo | 3–4 sett | 4 |
| 24 | Multi-sport | Alto | 2–3 mesi | 4 |
| 25 | WearOS / watchOS app | Alto | 2–3 mesi | 4 |
| 26 | Marketplace coach umani | Altissimo | 4–6 mesi | 4 |

---

## I 5 "unlock" da 500M download

Se dovessi scegliere le 5 feature che fanno la differenza tra "app carina per smanettoni" e "app mainstream con virality":

1. **iOS app** — senza iOS perdi metà del mercato premium
2. **Health Connect** — svincolarsi da Garmin è il TAM più grande della lista
3. **Live GPS + audio coaching** — trasforma l'app da "archivio" a "compagno di corsa"
4. **Piani strutturati multi-settimana** — l'unica feature per cui i runner pagano davvero (vedi Runna)
5. **Feature social + condivisione immagini** — il flywheel di crescita organica (Strava insegna)
