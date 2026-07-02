# AGENT_PROMPT — template per sviluppare la FINAL_ROADMAP un passo alla volta

**Uso:** il prompt operativo per ogni passo è una riga:

> *Esegui il Passo {N} seguendo docs/AGENT_PROMPT.md*

L'agent sostituisce `{N}` e applica il template qui sotto. La specifica vera del
passo vive in `docs/FINAL_ROADMAP.md` §5-bis: questo file governa solo *come*
lavorare, non *cosa* costruire.

---

## Template

```text
Esegui il Passo {N} della sequenza di sviluppo in docs/FINAL_ROADMAP.md, sezione 5-bis.

FONTI (in quest'ordine, prima di scrivere codice):
1. `git pull` sul branch corrente: altri flussi committano in parallelo.
2. Leggi il brief del Passo {N} in §5-bis. Obiettivo e Criteri di accettazione sono
   VINCOLANTI; "Da costruire" è il design di riferimento.
3. Verifica lo "Stato attuale" dichiarato dal brief contro il codice REALE: il codebase
   evolve e il brief può essere arretrato. Se divergono, adatta il design allo stato
   reale mantenendo l'obiettivo, e documenta la deviazione nel commit e nel report.
4. Rispetta CLAUDE.md e lo stile del codice circostante.

DIPENDENZE: verifica nel codice che le dipendenze dure del passo (elencate in testa
alla §5-bis) siano già implementate. Se una manca, FERMATI e segnalalo: non
svilupparla tu.

PERIMETRO:
- Implementa SOLO il Passo {N}. Niente refactoring opportunistici, niente feature
  adiacenti "già che ci sono".
- Se trovi il branch rotto per cause preesistenti (test rossi, lint, alembic fuori
  sync): riparalo in un COMMIT SEPARATO prima del tuo, spiegando cosa era rotto e
  perché la tua riparazione è fedele all'intento di chi l'ha rotto; se non è banale,
  segnala invece di riparare.
- L'app deve restare eseguibile senza credenziali (demo/offline). I moduli in
  app/processing/ restano funzioni pure (no I/O, no rete).

QUALITÀ (gate bloccanti, tutti verdi PRIMA del commit):
- pytest --cov=app --cov-report=term --cov-fail-under=80
- ruff check app tests
- alembic upgrade head && alembic check (se tocchi i modelli: ORM e migrazione
  perfettamente in sync)
- Ogni criterio di accettazione del brief coperto da almeno un test automatico.
  Se un criterio non è automatizzabile (UI, batteria, device reale), dichiara nel
  report COME l'hai verificato e cosa resta da verificare a mano.
- Android: in questo ambiente non c'è SDK — verifica bilanciamento sintassi, import,
  esistenza delle icone/dipendenze usate, coerenza coi pattern esistenti, e dichiara
  esplicitamente nel report che la build non è stata eseguita.

CHIUSURA:
1. Aggiorna docs/FINAL_ROADMAP.md marcando il Passo {N} "✅ FATTO — <data>" con 2-3
   righe su cosa è stato implementato e le eventuali deviazioni dal brief. Se il passo
   completa una feature di docs/WORLD_CLASS_ROADMAP.md, marca anche quella.
2. Commit descrittivo (cosa/perché/deviazioni) e push su
   claude/running-analytics-platform-a017s4, con retry e backoff sui soli errori di rete.
3. Report finale: cosa hai costruito; verifica punto-per-punto contro i criteri di
   accettazione; cosa NON hai fatto e perché; rischi residui.

Non chiedere conferme durante il lavoro: prendi decisioni ragionevoli e documentale.
Fermati solo se un criterio di accettazione è irrealizzabile o una dipendenza manca.
```

---

## Varianti obbligatorie

### Passi grossi — 18 (G1+G5 live GPS/offline) e 22 (G4 multi-user)

Aggiungere in coda al template:

```text
Questo passo è troppo grande per una sessione: prima produci un piano di milestone
committabili singolarmente (ognuno lascia il branch verde), salvalo in coda al brief
del Passo {N} in docs/FINAL_ROADMAP.md, poi implementa SOLO il primo milestone.
```

Per le sessioni successive il prompt diventa:

> *Continua il Passo {N} dal milestone successivo, secondo il piano registrato nel
> brief e lo stato dell'ultimo commit.*

### Passi che toccano prompt/AI — 11 (voce LLM), 12 (voice debrief), 15 (recap)

Aggiungere in coda al template:

```text
Ogni modifica a prompt o comportamento LLM passa dall'eval harness (Passo 9) prima
del commit: estendi gli scenari se il comportamento nuovo non è coperto.
```

---

## Perché il template è fatto così (per chi lo manutiene)

1. **"Verifica lo stato attuale contro il codice reale"** — la clausola più
   importante: i brief invecchiano in ore quando ci sono flussi paralleli; un agent
   che segue ciecamente la spec scritta produce codice che non si integra.
   L'obiettivo è vincolante, il design è di riferimento.
2. **Riparazione preesistente in commit separato** — senza questa regola l'agent
   o si blocca sul branch rosso o mescola riparazione e feature rendendo il diff
   irrivedibile.
3. **Dipendenze: fermati, non svilupparle** — evita che un passo si trascini dentro
   mezzo passo precedente fatto male.
4. **"Non chiedere conferme"** — per un agent autonomo le domande a metà lavoro sono
   punti morti; meglio decisioni documentate nel report, riviste a posteriori.
