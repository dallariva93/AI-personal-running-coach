# Redesign UI Android — piano di implementazione

Fonte: `handoff/` (13 schermate, dark mode, generate con Claude Design il
2026-07-09). Riferimento completo: `handoff/README.md` (mappatura file →
schermata), `handoff/RunningCoach.dc.html` (markup di riferimento, sezioni
`id="1a"`…`id="1m"`), `handoff/DESIGN_TOKENS.md`, `handoff/COMPONENT_NOTES.md`.

## Scoperta chiave (prima di procedere)

I design token del redesign (`DESIGN_TOKENS.md`) **sono già** quelli
dell'app — `ui/theme/Color.kt` e `Shape.kt` corrispondono esattamente
(`BrandGreen #00C16E`, radii `8/12/18/24/32`, ecc.), perché sono stati
estratti dal codebase corrente. **Il redesign non è un rifacimento da zero**:
è un **refinement mirato** di composizione, copy e micro-dettagli su
componenti già molto vicini al target. Questo abbassa il rischio per schermo
ma non riduce il conteggio (13 schermate + 1 nuova + tema chiaro).

## Principio di esecuzione

Un milestone per sessione (come Passo 18 in `FINAL_ROADMAP.md`), CI Android
verificata verde prima di passare al successivo. Nessuna verifica visuale
diretta è possibile in questo ambiente (niente SDK/emulatore) — l'unico gate
automatico è la build (`assembleDebug` in CI). Ogni modifica va quindi accompagnata
da un confronto letterale col markup HTML del riquadro corrispondente (colori
hex, spaziature, copy) per limitare il rischio di scostamento.

## Milestone

- **M1 — Home / Oggi (1a)** ✅ FATTO — 2026-07-09
  - Header: eyebrow uppercase mono-style "data · settimana N" (settimana da
    `Overview.activePlan.currentWeekNumber`, quando presente) sopra il titolo.
  - CTA "Corri adesso col telefono": gradiente BrandGreen→BrandGreenBright
    (prima: bottone Material pieno), testo/icona `#00210F` fisso.
  - `TodayWorkoutCard`: barra accento 4dp in cima alla card (gradiente sul
    colore della decisione); griglia azioni 2×2 con "Fatto" enfatizzato
    (bordo/testo/tint primary) e gli altri tre neutri — prima tutti e 4
    uniformi.
  - Non toccato in M1 (verificato già conforme al target): `IntensityBar`
    (copy "Distribuzione intensità" / "obiettivo 80/20" già presente),
    `WeeklyChart` (label date già `MM-DD` via `weekStart.drop(5)`), radii
    (`SurfaceCard`/tema già 18dp, nel range 16–22 del target).
  - Rimandato a un polish successivo: font Manrope/DM Mono (opzionale per il
    doc handoff), `MetricRing` 96dp vs 116dp attuale (cosmetico, basso rischio
    ma basso valore), copy `home_subtitle`.

- **M2 — Dettaglio corsa (1b)** ✅ FATTO — 2026-07-09
  - Zone FC: barre individuali per zona (larghezza ∝ quota di tempo, label
    "m:ss" in stile Garmin) al posto di StackedBar + lista a pallini.
  - Nuova `RpeSliderSection`: track a gradiente verde→arancio→rosso con
    thumb posizionato sul valore corrente, tap per aprire lo stesso
    `RpeEditDialog` già usato dall'icona nell'hero.
  - `PaceComparisonSection` restilizzata come card a gradiente compatta
    (passo reale a sinistra, delta con segno + target a destra), come il
    blocco "PASSO vs OBIETTIVO GARA" del mockup.
  - Non toccato (già conforme, o fuori scope UI): hero mappa/hero header a
    gradiente (struttura diversa dal mockup ma pattern di brand consolidato,
    rifarlo è un cambio strutturale più ampio, rimandato); `MetricAreaChart`
    (Passo 18) per altitudine/passo, splits Strava-style, Performance/
    Environment/Recovery grid — già coerenti. Trail metrics (VAM, km piani
    equivalenti) **non implementate**: richiedono dati non presenti nel
    modello `Activity` (lavoro backend, fuori scope redesign UI).

- **M3 — Piano (1c) + Calendario (1i)** ✅ FATTO — 2026-07-09
  - Nuova `PeriodizationTimeline` in `PlanScreen.kt`: raggruppa le settimane
    del piano per fase consecutiva (`PlanWeek.phase`), larghezza del segmento
    ∝ numero di settimane, fase corrente evidenziata (colore pieno + "Nw ·
    ora"), riga "Fase attuale: X — descrizione" + volume target sotto.
    Costruita direttamente da `TrainingPlan.weeks` — **non** da
    `PeriodizationPlan`/`PhaseCard` (`Components.kt`): quel componente esiste
    ma non è mai chiamato da nessuno screen, e richiederebbe di passare
    `Overview` dentro `PlanScreen` (wiring cross-schermo, rischio più alto
    per lo stesso risultato visivo). Segnalato qui come componente morto da
    valutare per rimozione in futuro.
  - `PlanCalendarScreen.kt`: la cella giorno ora mostra una barra colorata in
    fondo (larghezza 60%, altezza 4dp) invece di un pallino centrato — più
    leggibile a colpo d'occhio su un mese intero, come nel mockup.
  - Non toccato (già solido, rischio/beneficio sfavorevole a toccarlo):
    `RaceCountdownCard` (mostra countdown/completamento, concettualmente
    diverso dalla "previsione tempo gara" del mockup — quella vive in
    `PredictionCard`, oggi mostrata solo in Home; wiring cross-schermo
    rimandato), `SessionRow` (checkbox interattiva reale, più ricca del
    markup statico — non c'è motivo di impoverirla per somiglianza visiva).

- **M4 — Coach AI (1d) + Statistiche (1e)**
  - File: `ChatScreen.kt`, `StatsScreen.kt`.
  - Dal markup: bolle con radius asimmetrico (18/18/18/6 coach,
    18/18/6/18 utente), quick-reply button dentro la bolla coach, suggestion
    chips scrollabili.
  - Stats: grid 2×2 big stat, record personali tile tint rosso.

- **M5 — Check-in giornaliero (1f, NUOVA schermata) + Live run (1g)**
  - 1f non esiste ancora come schermo dedicato (readiness/check-in — verificare
    se i dati esistono già in `DailyCheckin` nel modello e sono solo da
    esporre in UI, o se serve anche lavoro backend: **verificare prima di
    stimare l'effort**).
  - `LiveRunScreen.kt`: pannello metriche bottom-sheet, già implementato in
    Passo 18 — verificare stile vs markup, non rifare la logica GPS.

- **M6 — Workout builder (1h) + Impostazioni (1j)**
  - File: `WorkoutScreen.kt`, `SettingsScreen.kt`.

- **M7 — Traguardi/Gamification (1k) + Recap (1l) + Scarpe (1m)**
  - File: `Components.kt` (`StreakCard`/`PersonalRecordsCard` — verificare
    se serve una gallery dedicata "sbloccati/da sbloccare" separata da Home),
    `RecapScreen.kt`, `ShoesScreen.kt`.

- **M8 — Tema chiaro + polish trasversale (facoltativo, a fine ciclo)**
  - Verifica di tutte le schermate in `RunningCoachTheme(darkTheme = false)`.
  - Eventuale introduzione font Manrope/DM Mono se si decide di adottarli
    (asset font + `Type.kt`) — solo se richiesto esplicitamente, il doc
    handoff la marca opzionale.

## Note per l'esecutore (ogni milestone)

1. `git pull` prima di iniziare; verificare lo stato reale del file Compose
   target (i componenti sono spesso già più vicini al design di quanto la
   sola lettura del doc handoff suggerisca — vedi M1).
2. Confrontare letteralmente col blocco HTML `id="1x"` in
   `handoff/RunningCoach.dc.html` (colori hex, spaziature, copy) prima di
   scrivere codice.
3. Modifiche scoped al/ai file della schermata; evitare di toccare
   `Primitives.kt`/tema globalmente a meno che il diff non lo richieda
   esplicitamente (rischio di ripercussioni sulle altre ~12 schermate).
4. Bilanciamento graffe/parentesi (niente SDK locale) + CI Android verde
   prima di considerare la milestone chiusa.
5. Aggiornare la riga della milestone qui sopra a ✅ FATTO con data.
