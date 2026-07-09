# AI Running Coach — Component / Content Notes (for redesign)

Source repo: dallariva93/AI-personal-running-coach @ claude/running-analytics-platform-a017s4
Goal: REDESIGN all screens (skip recreation). Dark+light. Android phone frame. Mix of visual+UX+copy.
Tokens in DESIGN_TOKENS.md.

## App shell (AppScaffold.kt)
- Bottom nav, 4 tabs: Oggi (Today icon) · Corse (DirectionsRun) · Piano (CalendarMonth) · Coach (AutoAwesome/sparkle)
- NavigationBar containerColor = surface; selected: indicator=primary(green), selectedIcon=onPrimary, selectedText=primary
- Settings = gear icon in Oggi header (not a tab). Corse has internal Lista/Statistiche TabRow.

## HOME / "Oggi" (HomeScreen.kt) — vertical scroll, pad 16h/12v
1. Header row: ScreenTitle(title="Oggi"+subtitle) | right: two stacked Pills — mode (green, e.g. "DEMO") + coach (coral, e.g. "AI") | gear IconButton
2. Primary Button full-width: "Corri adesso col telefono" (DirectionsRun icon)
3. (optional) Onboarding card (primaryContainer bg) w/ checklist 5 steps + "x/5"
4. **TodayWorkoutCard** (dominant): icon box 52dp rounded16 tinted + [verb · confidence] small caps colored + headline titleLarge. Then italic colored dailyNote. Then prescription (bodyMedium). Then rationale (muted). Safety flags (red warning rows). 4 action OutlinedButtons 2x2: "Fatto"(check), "Riduci"(trendDown), "Sposta"(moveDown), "Problema"(sick). Then "Perché?" expand toggle -> signals/alternatives/missingData bullet lists.
   - decision styles: rest=Hotel/grey, quality=Bolt/tempo-orange, long=Route/greenDeep, modify=Tune/amber, caution=Warning/red, default=Run/green
5. SyncStatusRow: muted "Ultima sync HH:MM" + Sync icon button
6. "Dettagli" expand toggle (primary color) -> FormStateCard, PredictionCard, HrvCard, StreakCard, PersonalRecordsCard, WeeklyChart
7. Two link rows (primary text + chevron): "Diario del coach", "Recap settimanale"
8. SectionTitle "Corse recenti" + up to 5 ActivityRow

## Key cards
- **FormStateCard**: MetricRing (progress ring, big signed TSB value e.g. "+12", caption "FORMA", ring color by formState) + Pill(formState uppercase) + formExplanation. Divider. Row of StatItems: Fitness(CTL), Fatica(ATL), ACWR, "7 gg" km. IntensityBar (stacked 80/20: Facile/Medio/Intenso with %). Extra chips: injury, recovery, VO2max.
  - formState colors: fresh #22C55E, balanced #38BDF8, fatigued #F43F5E, detraining #FBBF24
  - ring math: (tsb+30)/55 clamped 0..1
- **PredictionCard**: GradientCard [BrandGreenDeep->BrandGreen], white text. "PREVISIONE GARA · {TYPE}" label + predictedTime displaySmall + 3 HeroStats: Obiettivo(targetTime), Probabilità(%), Confidenza. basis line.
- **HrvCard**: big value + "ms RMSSD" + Pill(HRV ALTO/BASSO/NORMALE) + explanation. high=green, low=coral, normal=sky.
- **StreakCard**: 3 columns divided: streakDays (coral if>=7 else green) "giorni di fila" | streakDaysBest "record streak" | totalBadgesEarned "badge". Earned badges chips 2-col grid.
- **PersonalRecordsCard**: "Record personali" + 2-col grid tiles (ActivityHard #F43F5E tint bg): distance label, pace titleMedium bold, date. Distances 1K/5K/10K/21K/42K.
- **WeeklyChart**: "Carico settimanale" + total km · 8 sett. BarChart green, latest week accented. labels = weekStart minus year.
- **ActivityRow** (SurfaceCard, vert pad 5): 44dp icon box tinted by activityColor + glyph emoji | type name (colored, bold) + PR badge (red) + date | stats row: km, min, passo, FC.
  - activity glyphs: easy🏃 recupero🚶 medio⚡ lungo🛣️ tempo🔥 intervalli💥 trail⛰️ gara🏁
  - activityColor: easy/recupero green, medio/lungo sky, tempo orange, intervalli/gara red, trail emerald

## Primitives (Primitives.kt — not yet read, infer): SurfaceCard = rounded (md/18dp) surface card w/ padding ~16; Pill = small rounded caps chip tinted; SectionTitle = titleLarge/Medium bold; ScreenTitle = big title + muted subtitle; StatItem = value (bold) over small muted label; MetricRing, StackedBar, ThinDivider, GradientCard, BarChart.

## Other screens to redesign (read source next as needed)
- ActivityDetailScreen.kt (34KB): map (RouteMap.kt, OSM), elevation+pace overlay chart (Charts.kt), Strava splits with relative bars, intensity pill, editable RPE slider 1-10, editable notes, HR zones, training effect, VO2max, trail metrics (VAM, equiv flat km, D+/D-), target pace compare card.
- ChatScreen.kt (12KB): conversational coach, message bubbles, model routing.
- PlanScreen.kt (36KB): weekly plan, multi-week periodization phases (Base->Build->Specifico->Taper->Race), PhaseCard timeline.
- StatsScreen.kt: annual/monthly distance, dislivello, hours, count + CSV/JSON export.
- WorkoutScreen.kt (36KB): visual workout builder, expandable segments, AI suggest.
- Also: CalendarScreen, HeatmapScreen, CrossTrainingScreen, ShoesScreen, LiveRunScreen, SettingsScreen, RecapScreen, CoachLogScreen.

## BUILD PLAN
1. copy_starter_component android_frame.jsx
2. Build RunningCoach.dc.html — redesigned Home (dark) inside Android frame first. Use canvas mode (meta design_doc_mode=canvas) since multiple options/screens.
3. Add screens + light variant + option directions per turn (sections newest-top, ids 1a/1b...).
