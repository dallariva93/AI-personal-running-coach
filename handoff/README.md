# Handoff: AI Running Coach — Redesign UI (Android / Jetpack Compose)

## Overview
Questo pacchetto contiene il **redesign completo dell'interfaccia** dell'app AI Running Coach: 13 schermate ridisegnate in dark mode, pensate per l'app Android nativa (Kotlin + Jetpack Compose, Material 3). Il redesign mantiene l'identità di brand esistente (verde "volt" + coral, superfici near-black) ma rinnova layout, gerarchia, densità e copy.

L'obiettivo dell'handoff è **reimplementare queste schermate nel codebase Compose esistente**, modificando i file in `running-coach-platform/android/app/src/main/java/com/runningcoach/app/ui/`.

## About the Design Files
I file in questo bundle sono **riferimenti di design creati in HTML** — prototipi che mostrano look e comportamento desiderati, **non codice di produzione da copiare direttamente**. Il compito è **ricreare queste schermate HTML nell'ambiente esistente del codebase** (Jetpack Compose / Material 3), usando i pattern, i `@Composable` e i token già presenti (`ui/theme/`). Il file `RunningCoach.dc.html` usa una sintassi custom (Design Components) con un frame Android di anteprima: ignora il wrapper `<x-import AndroidDevice>` e il markup del bezel — conta solo il contenuto delle schermate al suo interno.

## Fidelity
**High-fidelity (hifi).** Colori, tipografia, spaziature e stati sono definitivi. Il developer dovrebbe ricreare la UI in modo fedele usando i Composable e i token esistenti. Le spaziature HTML (px) mappano ~1:1 su `dp` in Compose.

## Mappatura file sorgente
Ogni schermata del redesign corrisponde a un file Compose esistente da aggiornare:

| Schermata redesign | File Compose da modificare |
|---|---|
| 1a — Oggi / Dashboard | `ui/screens/HomeScreen.kt` + `ui/components/TodayWorkoutCard.kt`, `Components.kt` |
| 1b — Dettaglio corsa | `ui/screens/ActivityDetailScreen.kt` + `ui/components/RouteMap.kt`, `Charts.kt` |
| 1c — Piano | `ui/screens/PlanScreen.kt` + `Components.kt` (PhaseCard, PredictionCard) |
| 1d — Coach AI | `ui/screens/ChatScreen.kt` |
| 1e — Statistiche | `ui/screens/StatsScreen.kt` |
| 1f — Check-in giornaliero | (nuovo / readiness — cfr. HealthConnectSection, check-in) |
| 1g — Live run | `ui/screens/LiveRunScreen.kt` |
| 1h — Workout builder | `ui/screens/WorkoutScreen.kt` |
| 1i — Calendario piano | `ui/screens/PlanCalendarScreen.kt` / `CalendarScreen.kt` |
| 1j — Impostazioni | `ui/screens/SettingsScreen.kt` |
| 1k — Traguardi / Gamification | `ui/components/Components.kt` (StreakCard, PersonalRecordsCard) + nuova gallery |
| 1l — Recap settimanale | `ui/screens/RecapScreen.kt` + `ui/components/RecapCard.kt` |
| 1m — Scarpe | `ui/screens/ShoesScreen.kt` |

Shell / navigazione: `ui/navigation/AppScaffold.kt` — bottom nav 4 tab (Oggi · Corse · Piano · Coach), Impostazioni = gear in header Oggi, Statistiche dentro Corse (tab Lista/Statistiche).

## Design Tokens
Tutti i valori sono già in `ui/theme/` (Color.kt, Type.kt, Shape.kt). Vedi anche `DESIGN_TOKENS.md` nel bundle.

**Brand:** BrandGreen `#00C16E`, BrandGreenBright `#2BE38C`, BrandGreenDeep `#037A45`, Coral `#FF5A1F`, CoralBright `#FF7E45`.
**Dark surfaces:** background `#0D1014`, surface `#161B22`, surfaceElevated `#1D232C`, surfaceVariant `#242C37`, outline `#323B47`, onSurface `#E7ECF2`, onSurfaceMuted `#9AA6B4`.
**Light surfaces:** background `#F5F7FA`, surface `#FFFFFF`, surfaceVariant `#EDF1F5`, outline `#D7DEE6`, onSurface `#11161C`, onSurfaceMuted `#5C6773`.
**Form state:** fresh `#22C55E`, balanced `#38BDF8`, fatigued `#F43F5E`, detraining `#FBBF24`, unknown `#64748B`.
**HR zone / intensità:** Z1 `#64748B`, Z2 `#38BDF8`, Z3 `#22C55E`, Z4 `#FB923C`, Z5 `#F43F5E`.
**Attività:** easy/recupero `#22C55E`, medio/lungo `#38BDF8`, tempo `#FB923C`, intervalli/gara `#F43F5E`, trail `#10B981`.
**Radii (dp):** xs 8, sm 12, md 18, lg 24, xl 32. Le card del redesign usano prevalentemente 16–22.
**Tipografia (system sans / Roboto):** displaySmall 40/44 Black -0.5 (numeri hero), headlineMedium 26/32 Bold, headlineSmall 22/28 Bold, titleLarge 19/24 Bold, titleMedium 16/22 SemiBold, bodyLarge 15/22, bodyMedium 14/20, bodySmall 13/18, labelMedium 12/16 SemiBold +0.4.
Il redesign HTML usa **Manrope** (display/body) + **DM Mono** (etichette dati/mono). In Compose puoi mantenere Roboto o introdurre Manrope come font asset; i pesi mappano 400/500/600/700/800.

---

## Schermate — dettaglio

### 1a — Oggi / Dashboard
**Scopo:** rispondere a "cosa faccio oggi?" e mostrare lo stato di forma.
**Layout:** scroll verticale, padding 16dp orizzontale.
- **Header:** riga con data mono (`Mar 8 lug · settimana 3`, colore verde) sopra titolo "Oggi" (34sp, 800). A destra: due pill impilate — "DEMO" (verde tint) e "COACH AI" (coral tint) — + icona gear 42×42 in card surface.
- **CTA primaria:** bottone full-width 52dp, gradiente `#00C16E→#2BE38C`, testo `#00210f` 800, icona corsa. "Corri adesso col telefono". Ombra verde soft.
- **Card hero "cosa fare oggi":** card surface radius 22, barra accento superiore 4dp (gradiente arancio per decisione "quality"). Riga icona 52×52 tint arancio + `QUALITÀ · ALTA CONFIDENZA` (12sp 800 arancio) + headline "Ripetute in soglia" (22sp 800). Nota motivazionale in corsivo colore accento. Prescrizione (15sp onSurface) + razionale (13sp muted). Griglia 2×2 di action button outline 42dp: **Fatto** (verde), **Riduci**, **Sposta**, **Problema**. Riga toggle "Perché questa scelta?" (verde) + chevron.
- **Sync row:** testo muted "Ultima sync 08:42 · 1 nuova corsa" + icona refresh.
- **Card Forma:** anello SVG 96×96 (traccia `#242C37`, progresso `#22C55E`, valore "+12" 26sp + caption "FORMA"). A fianco pill "FRESH" verde + spiegazione. Divider. Riga 4 StatItem: Fitness 48, Fatica 36, ACWR 1.1 (verde), 7gg 42km. Barra intensità stacked (Facile 82% `#38BDF8` / Medio 11% `#FB923C` / Intenso 7% `#F43F5E`) con legenda a pallini + "obiettivo 80/20".
- **Card Carico settimanale:** titolo + "312 km · 8 sett." + bar chart 8 barre (`#2b3a33`, ultima gradiente verde con label "oggi").
- **Corse recenti:** SectionTitle + link "Tutte". Lista righe corsa: box 44×44 tint per tipo + glyph emoji, tipo (colorato 800) + eventuale badge "PR" (rosso), data, + 4 stat (km/min/passo/FC).
- **Bottom nav** sticky: 4 tab, "Oggi" selezionato (indicator pill verde, icona `#00210f`), altri muted.

### 1b — Dettaglio corsa
- **Hero mappa** 220dp: sfondo scuro, traccia GPS SVG verde con dot start (verde) / finish (rosso). Bottone back top-left e fullscreen bottom-right (card blur 40×40).
- **Titolo:** data mono + "Medio progressivo" (24sp 800) + pill tipo "TEMPO" (arancio tint).
- **Big stats:** riga 3 (12.4 km / 4:41 passo / 58:04 tempo, 30sp 800). Riga 4 secondaria (FC media 168, FC max 184, dislivello +186, kcal 712).
- **Card passo vs obiettivo:** gradiente verde, "4:41 reale" vs "−9″ sotto target 4:50".
- **Grafico altitudine & passo:** card, area quota (`#242C37`) + linea passo verde, legenda.
- **Splits al km:** lista 12 righe: numero km, barra relativa (larghezza ∝ velocità, colore per zona: verde→blu→arancio→rosso), passo mono, delta dislivello.
- **Zone FC:** 5 righe Z1–Z5 con barra colorata per zona e tempo in zona.
- **Training effect** (3.4 aerobico) + **VO₂max** (54.2, ▲) in due card affiancate.
- **RPE slider:** track gradiente verde→arancio→rosso, thumb bianco a 70%, valore "7" mono. Label "1 facile / 10 massimale".
- **Trail metrics:** 3 card — VAM 842 m/h, km piani eq. 14.3, D+/D− +186/−178.
- **Note:** card con testo editabile + link "Modifica".

### 1c — Piano
- **Header:** data mono "Maratona di Venezia · 118 gg" + "Piano" (34sp).
- **Card previsione gara:** gradiente verde, "PREVISIONE GARA · MARATONA" + tempo 40sp "3:24:18" + 3 hero stat (Obiettivo 3:20:00 / Probabilità 72% / Confidenza Media) + basi.
- **Periodizzazione:** timeline fasi con larghezza ∝ settimane: BASE 4w (idle) / **BUILD 6w · ora** (verde, evidenziata) / SPEC 4w / TAP 2w / gara 1w (rosso 🏁). Testo fase attuale + volume target.
- **Questa settimana:** SectionTitle + "3/5 fatti". Lista sessioni: giorno (LUN 7…) + barra colore tipo + nome + dettaglio + check (fatto = verde pieno, oggi = bordo verde + cerchio vuoto, futuro = cerchio muted).

### 1d — Coach AI
- **Header chat:** avatar gradiente verde con stella + "Coach" + stato "online · ricorda la tua storia" (verde) + pill modello "SONNET" (mono).
- **Messaggi:** separatore data mono. Bolla coach (sinistra, surface, radius 18/18/18/6). Bolla utente (destra, gradiente verde, testo scuro, radius 18/18/6/18). Bolla coach con **quick-reply button** ("Sì, aggiorna" verde / "Solo fondo facile" outline).
- **Suggestion chips** scrollabili (outline). **Input bar:** campo pill 44dp + bottone invio tondo gradiente verde.

### 1e — Statistiche
- **Header** "Statistiche". Toggle periodo (2026 attivo / Luglio / Sempre).
- **Grid 2×2 big stat:** 1.284 km (verde), 142 corse, 18.640 m dislivello, 108h.
- **Bar chart** distanza per mese (7 barre, ultima verde).
- **Record personali:** grid 2×2 tile tint rosso (1km 3:42, 5km 19:58, 10km 41:30, 21.1km 1:32:04).
- **Export:** due bottoni outline CSV / JSON con icona download.

### 1f — Check-in giornaliero
- **Header:** data mono "· 30 sec" + "Come stai stamattina?" (32sp) + sottotitolo.
- **Sonno:** card con slider (thumb bianco bordo verde) + valore "7h 20".
- **Energia:** 5 emoji selezionabili (🙂 selezionato = tint verde bordo verde).
- **Dolori:** chip multi-scelta ("Nessuno", "Polpaccio dx" selezionato arancio, "Ginocchio"…).
- **Motivazione:** slider "8/10".
- **CTA** full-width gradiente "Invia check-in".

### 1g — Live run
- **Mappa** flex-1 con traccia verde + dot start/posizione.
- **Overlay:** pill "REC" (rosso pulsante) + "GPS ●●●".
- **Pannello metriche** (bottom sheet radius 28 top): distanza gigante "5.42" (72sp mono) + "CHILOMETRI". Riga 3 (passo 4:48 / tempo 26:04 / FC 158 arancio). Controlli: pausa (64 tondo surface), stop grande (88 tondo gradiente verde), lock (64 tondo).

### 1h — Workout builder
- **Header:** "Nuovo allenamento" + riepilogo (12 km · 58 min · TSS 74) + pill "AI".
- **Nome** (card) + **tipo** chip (Tempo selezionato arancio).
- **Segmenti:** Riscaldamento (barra blu, chevron), **Ripeti ×6** espanso (bordo arancio, sub-step Corri 1000m 4:05 + Recupero 90s jog), Defaticamento. Bottone dashed "Aggiungi segmento".
- **CTA** "Salva allenamento".

### 1i — Calendario piano
- **Header** "Luglio" + frecce prev/next. Header giorni L-D. **Grid mese:** celle radius 10 con numero + barra colore tipo sessione; oggi (9) evidenziato verde, giorno con qualità (8) arancio. Legenda colori. **Dettaglio giorno selezionato** (card bordo verde): data mono + "Fondo facile" + dettaglio + hint drag.

### 1j — Impostazioni
- Sezioni con label uppercase muted. **Connessioni:** Garmin (connesso, verde) / Strava (non connesso + bottone "Collega"). **Aspetto:** Tema (Sistema/Scuro selezionato/Chiaro). **Obiettivo:** righe gara/data/tempo/livello. **Backend:** URL mono.

### 1k — Traguardi / Gamification
- **Streak hero** gradiente coral: 🔥 + "23 giorni di piano rispettato" + record 31.
- **3 counter:** 14 badge / 5 record km / 1.284 km 2026.
- **Gallery badge sbloccati** (grid 3-col, emoji + nome) + **da sbloccare** (grid dashed, grayscale, opacità 0.4).

### 1l — Recap settimanale
- **Header** range date mono + "La tua settimana" + icona condividi.
- **Summary verbale** (card gradiente verde, testo 16sp): riassunto discorsivo.
- **Grid 2×2 stat** (52.2 km ▲12%, 5 uscite, 4:38 passo, +486 m).
- **Momenti clou:** righe con emoji (🏆 nuovo lungo record, ⚡ passo soglia in calo).
- **CTA** "Condividi recap" (outline verde).

### 1m — Scarpe
- **Card scarpa attiva:** nome + uso + pill "ATTIVE" (verde) + progress usura (182/400 km, 45%, barra verde).
- **Card da cambiare:** pill "DA CAMBIARE" (arancio), 642/700 km 92%, barra arancio + warning.
- **Card ritirate** (opaca, 812 km). Bottone dashed "Aggiungi scarpe".

## Interactions & Behavior
- Tutte le liste scrollano verticalmente; chip/segment control orizzontali scrollano.
- Toggle "Perché?" / "Dettagli" espandono con `AnimatedVisibility` (già nel codice).
- Action button Oggi (Fatto/Riduci/Sposta/Problema) → `onCoachAction(action, param)` esistente.
- Slider RPE/readiness → salvano su cambio (debounce).
- Chat quick-reply → invio messaggio predefinito.
- Calendario: long-press + drag sposta sessione → `moveSession` esistente (con snackbar "Annulla").
- Temi: dark è il default e la firma; light usa i token light sopra.

## State Management
Riutilizza i ViewModel esistenti: `OverviewViewModel` (Home+Piano condiviso, `/api/mobile/overview`), `PlanViewModel`, `WorkoutViewModel`, `ChatViewModel`, `StatsViewModel`, `SettingsViewModel`. Nessun nuovo store necessario — è un refactor di presentazione. DTO in `data/model/Models.kt`.

## Assets
Nessun asset immagine: icone = Material Icons (già usate) o SVG inline equivalenti; glyph attività = emoji (come nel codice attuale, `activityGlyphs`). Mappa = OSM via `RouteMap.kt` esistente. Font opzionale Manrope da Google Fonts se si vuole adottare il type del redesign.

## Files
- `RunningCoach.dc.html` — tutte le 13 schermate del redesign (dark). Apri in browser per vederle affiancate.
- `android-frame.jsx` — solo il bezel di anteprima (NON da portare in Compose).
- `DESIGN_TOKENS.md` — token di design estratti dal codebase.
- `COMPONENT_NOTES.md` — note sulla struttura dei componenti originali.
