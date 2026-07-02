# Accessibility — stato e checklist

Passo 7 del piano di sviluppo (`FINAL_ROADMAP.md` §5-bis, Q7). Copre le schermate
Home + Today Workout Card + Plan (le più usate); il resto dell'app non è ancora
stato passato — vedi "Cosa NON è coperto" in fondo.

## 1. Stringhe i18n

`res/values/strings.xml` (default, inglese) + `res/values-it/strings.xml`
(italiano) per Home + Today Workout Card. `strings.xml` di default era già
presente ma **non collegato a nessun composable** (zero `stringResource()` in
tutto il modulo prima di questo passo, incluse 3 entry — `action_sync`,
`action_analyze`, `action_plan` — relative ai bottoni Sincronizza/Analizza
rimossi dal Q2: rimosse, morte insieme ai bottoni).

Convenzioni adottate:
- Placeholder posizionali (`%1$s`, `%1$d`) per i valori dinamici (orario
  sync, conteggio nuove corse, nome del prossimo step onboarding).
- `<plurals>` per "N nuove corse/corsa" invece di un if/else manuale sul
  singolare — l'inglese e l'italiano hanno regole di pluralizzazione diverse
  e il sistema `<plurals>` le gestisce entrambe dallo stesso resource id.
- Le funzioni non-composable che restituivano stringhe hardcoded
  (`styleFor`, `confidenceLabel` in `TodayWorkoutCard.kt`) sono diventate
  `@Composable` per poter chiamare `stringResource()` — unico modo pulito,
  l'alternativa (passare il `Context` a mano) è più invasiva.

**Non ancora estratto:** Plan screen (976 righe, non toccato in questo passo
per tenere il diff revisionabile), Settings/Activities/Calendar/Chat/Workout
screens, tutti i toast/snackbar nei ViewModel. Prossimo passo naturale:
ripetere lo stesso pattern schermata per schermata.

## 2. contentDescription sugli Icon

Regola applicata, coerente con le linee guida Android: un'icona **decorativa**
(il cui significato è già espresso da un testo adiacente nello stesso
componente cliccabile — es. il chevron accanto a "Mostra dettagli", l'icona
tipo-seduta accanto al titolo della seduta) resta `contentDescription = null`
e non deve annunciare nulla a TalkBack, altrimenti duplica o confonde
l'annuncio del testo. Un'icona che è **l'unica fonte dell'informazione** (nessun
testo adiacente equivalente) deve avere una descrizione vera.

Trovato e corretto un caso reale di violazione: il segnaposto
fatto/da-fare nella checklist di onboarding (`HomeScreen.kt`,
`OnboardingCard`) aveva `contentDescription = null` ma è l'**unico** segnale
visivo che distingue uno step completato da uno da fare — l'etichetta testuale
("Collega i dati") è identica in entrambi i casi. Ora annuncia "Fatto"/"Da
fare". Tutte le altre icone ispezionate in Home/Today/Plan erano già corrette
(incluse `IconButton` standalone come "Sincronizza ora" e "Invia" nella chat,
già con descrizioni proprie).

## 3. Emoji-glifo decorativi (`ActivityRow`, `CrossTrainingRow`)

Gli emoji di tipo-attività (🏃🚶⚡🛣️🔥💥⛰️🏁, 🚴🏊🏋️) restano visivamente
com'erano — non sostituiti da icone Material — perché in entrambi i casi
siedono accanto a un'etichetta testuale che dice già il tipo ("Intervalli",
"Ciclismo"...). Il problema reale non era la mancanza di un'icona Material,
era che TalkBack leggeva ad alta voce il glifo Unicode grezzo (spesso in modo
confuso o ridondante col testo adiacente). Fix: `Modifier.clearAndSetSemantics
{}` sul `Text` che porta il glifo, in `ActivityRow` (Components.kt),
`CrossTrainingRow` e l'illustrazione vuota "🚴 🏊 🏋️" (CrossTrainingScreen.kt).
Risultato: il glifo resta visibile ma invisibile a TalkBack, che annuncia solo
l'etichetta testuale — nessuna perdita di informazione, nessun doppio annuncio.

## 4. Touch target ≥48dp — calendari

`PlanCalendarScreen.kt` (`PlanDayCell`) e `CalendarScreen.kt` (`DayCell`):
padding orizzontale della griglia ridotto 8dp→4dp, padding interno della
cella 2dp→1dp, e `Modifier.sizeIn(minWidth = 48.dp, minHeight = 48.dp)`
aggiunto come previsto dal brief.

**Limite onesto, non risolvibile con un Modifier:** una griglia a 7 colonne
fisse (`GridCells.Fixed(7)`) alloca a ogni cella uno slot di larghezza
`(larghezza schermo − padding) / 7` con vincoli di larghezza *esatti* (min ==
max) imposti dal genitore — `sizeIn`/`minimumInteractiveComponentSize` non
possono forzare più spazio di quanto la griglia assegni. Su schermi ≥360dp
(la stragrande maggioranza dei dispositivi reali) i tagli sopra portano le
celle sopra i 48dp. Su schermi molto stretti (~320dp, ormai rari) resta
strutturalmente impossibile: 7×48dp = 336dp da soli, più del display intero.
Risolvibile solo cambiando il design (es. vista settimanale scrollabile
invece del mese a griglia) — fuori perimetro per un passo di accessibilità,
è un redesign.

## 5. Contrasto WCAG dei `Pill`

Script una-tantum (formula WCAG standard, luminanza relativa + rapporto
(L1+0.05)/(L2+0.05)) su ogni colore semantico di `Color.kt` contro
`background`/`surface`/`surfaceVariant` di entrambi i temi. **Risultato: il
fallimento è sistemico in tema chiaro**, non un paio di casi limite — quasi
tutti i colori del brand (tarati per il tema scuro quasi-nero) scendono sotto
4.5:1 su sfondo chiaro, e diversi falliscono anche in scuro una volta
applicato l'alpha 16% del pill.

Data la scala, invece di autorare a mano una variante `*Deep` per ogni
colore (facile dimenticarne una per i colori futuri, e fa divergere la
palette), ho aggiunto `Color.textSafeOn(background): Color` — schiarisce o
scurisce algoritmicamente (ricerca binaria sulla componente L di HSL,
`androidx.core.graphics.ColorUtils`) fino a raggiungere 4.5:1, garantito per
qualunque colore, non solo quelli auditati oggi. `Pill` lo applica al testo
(il pallino resta col colore vivido originale, è decorativo). Verificato in
Python lo stesso algoritmo su 4 casi rappresentativi: converge sempre a
~4.5:1 nella direzione corretta.

**Non ancora applicato:** altri punti che usano un colore semantico
direttamente come colore del testo (`MetricRing`, `StatItem.valueColor`)
condividono lo stesso rischio ma non sono stati toccati — `Pill` è l'unico
componente esplicitamente citato dal brief ed è quello con più punti di
utilizzo (18 call site in 6 file), quindi il fix lì ha l'impatto maggiore.

## 6. Checklist TalkBack — DA FARE MANUALMENTE

**Non eseguibile in questo ambiente**: nessun SDK Android, nessun
device/emulatore disponibile. La build APK è verificata solo per
bilanciamento sintassi/import; il pass reale con TalkBack va fatto da un
dispositivo o emulatore fisico. Checklist da compilare:

### Home
- [ ] Lo screen reader legge titolo e sottotitolo nell'ordine corretto
- [ ] La Today Workout Card annuncia decisione, prescrizione, nota del coach
- [ ] I 4 pulsanti azione (Fatto/Riduci/Sposta/Sto male) sono raggiungibili e
      annunciano l'etichetta corretta
- [ ] Il toggle "Mostra/Nascondi dettagli" annuncia lo stato corrente
- [ ] La riga di stato sync è leggibile senza ambiguità; il pulsante "Sincronizza
      ora" è distinguibile dal testo di stato
- [ ] La checklist di onboarding annuncia "Fatto"/"Da fare" per ogni step
- [ ] Le righe delle ultime corse sono navigabili singolarmente (non un blocco
      unico) e il glifo emoji non produce un doppio annuncio

### Today Workout Card (dettaglio)
- [ ] "Perché questa scelta?" espande/comprime e lo stato è annunciato
- [ ] Segnali/Alternative/Dati mancanti sono letti come liste distinte

### Piano
- [ ] Le sedute settimanali sono navigabili singolarmente
- [ ] Il calendario mensile: ogni giorno è un target separato, annuncia il
      numero del giorno + tipo di seduta (se presente)
- [ ] Lo spostamento seduta (drag/tap-to-move) è utilizzabile senza gesture
      complesse (tap sequenziali, non trascinamento)
- [ ] Lo snackbar "Annulla" dopo uno spostamento è raggiungibile e annunciato

### Generale
- [ ] Focus order logico su tutte e 4 le schermate (nessun salto illogico)
- [ ] Nessun testo troncato che nasconde informazione essenziale (vs. solo
      visiva)
- [ ] Contrasto verificato visivamente in tema chiaro E scuro (oltre allo
      script automatico sui `Pill`)

## Cosa NON è coperto da questo passo

- Plan screen (976 righe): stringhe non estratte.
- Settings, Activities, Calendar (fuori dai day-cell), Chat, Workout,
  Shoes, Strava screens: nessun controllo mirato (uno spot-check
  sull'intera app non ha trovato `IconButton` con `contentDescription =
  null`, ma non è un audit sistematico).
- `MetricRing`/`StatItem.valueColor`: stesso rischio di contrasto dei
  `Pill`, non corretto.
- Il pass TalkBack reale (checklist sopra, da compilare a mano).

**Criterio di accettazione dal brief** ("lint Android senza warning
`HardcodedText`/`ContentDescription` sulle schermate toccate"): il lint
Android stesso non è eseguibile in questo ambiente (serve Gradle+SDK); la
verifica qui è per lettura/grep mirata riga per riga sulle 4 schermate/
componenti toccati (Home, Today Workout Card, i due calendari, ActivityRow/
CrossTrainingScreen, Pill) — non è un lint automatico, va confermato con
`./gradlew lint` alla prima occasione con SDK disponibile.
