# Analisi feature di Fase 2 — priorità di implementazione

> Documento di analisi prodotto come Product Owner + Architect.
> Obiettivo: decidere **cosa implementare e in che ordine** dopo l'MVP esteso,
> restando nei vincoli del progetto (infrastruttura gratuita, minimo intervento
> umano, manutenibilità). Data: 2026-06-23.

---

## 1. Metodo di valutazione

Ogni feature è valutata su 5 criteri, punteggio **1–5** (5 = migliore).
I criteri sono pesati per riflettere gli obiettivi dichiarati: *prodotto reale
utile* + *minor intervento umano* + *costo zero* + *manutenibilità*.

| Criterio | Peso | Cosa misura |
|---|---|---|
| **Valore utente** | 30% | Quanto rende il prodotto più utile al runner |
| **Sforzo (inverso)** | 25% | Quanto è veloce da costruire (5 = poco lavoro) |
| **Costo** | 15% | Impatto economico (5 = gratis) |
| **Rischio/manutenibilità** | 20% | Fragilità, dipendenza da API instabili (5 = robusto) |
| **Autonomia** | 10% | Funziona senza nuove credenziali/blocchi (5 = nessun blocco) |

**Punteggio finale** = media pesata. Più alto = priorità più alta.

---

## 2. Classifica (dalla migliore alla peggiore)

| # | Feature | Valore | Sforzo | Costo | Rischio | Autonomia | **Totale** |
|---|---|:---:|:---:|:---:|:---:|:---:|:---:|
| 1 | **Input RPE + note da UI/CLI** | 4 | 5 | 5 | 5 | 5 | **4.65** |
| 2 | **Scheduling automatico (GitHub Action/cron)** | 5 | 4 | 5 | 4 | 3 | **4.40** |
| 3 | **Notifiche Telegram (workout del giorno)** | 5 | 4 | 5 | 4 | 3 | **4.40** |
| 4 | **Metriche di forma avanzate (efficienza FC/passo, deriva)** | 4 | 3 | 5 | 4 | 4 | **3.95** |
| 5 | **Export/Import dati (CSV/FIT) + backup** | 3 | 5 | 5 | 5 | 5 | **3.95** |
| 6 | **Migrazioni schema (Alembic)** | 2 | 4 | 5 | 5 | 5 | **3.45** |
| 7 | **Obiettivo gara + taper (periodizzazione)** | 5 | 2 | 4 | 3 | 4 | **3.55** |
| 8 | **Pianificazione settimanale "deep" con Opus** | 3 | 4 | 3 | 4 | 4 | **3.50** |
| 9 | **Push workout sull'orologio Garmin** | 5 | 1 | 5 | 1 | 2 | **2.95** |
| 10 | **Autenticazione dashboard** | 2 | 3 | 5 | 4 | 5 | **3.15** |
| 11 | **Self-tuning del prompt** | 3 | 1 | 2 | 1 | 4 | **2.20** |

> Nota: la classifica per **totale pesato** mette il taper (#7) sopra Alembic
> (#6) e auth (#10) nonostante il numero di riga; l'ordinamento "ufficiale"
> consigliato è quello del §4 (roadmap), che tiene conto anche delle dipendenze.

---

## 3. Schede di analisi

### 🥇 1. Input RPE + note manuali — *quick win assoluto*
**Cosa**: campo "sforzo percepito" (1–10) e note testuali per ogni corsa, da
dashboard (form HTMX) e da CLI (`analyze --rpe 7 --note "..."`).
- **Perché prima di tutto**: il campo `rpe` *esiste già* nel modello e negli
  schemi, manca solo l'input. Il documento originale lo cita come dato che
  "migliora l'analisi". Garmin non fornisce l'RPE: è l'unico modo per dare al
  coach il segnale soggettivo (FC alta + RPE basso = forma; FC normale + RPE
  alto = affaticamento nascosto).
- **Sforzo**: ~mezza giornata. Aggiungere `PATCH /api/activities/{id}`, un
  form nella tabella corse, ed estendere la logica dell'`OfflineCoach` per
  usare l'RPE.
- **Rischio**: nullo. Nessuna dipendenza esterna.
- **Verdetto**: **fare subito**. Massimo ritorno, minimo costo.

### 🥈 2. Scheduling automatico
**Cosa**: esecuzione pianificata di `ingest` + `analyze` a ogni nuova corsa.
Due varianti: **GitHub Action** schedulata (cron) o **cron locale/Raspberry**.
- **Perché**: è il cuore dell'obiettivo "minor intervento umano". Trasforma il
  tool da "lancio manuale" a "report che mi aspetta".
- **Sforzo**: basso. Un workflow `schedule:` che gira la CLI; i secret Garmin/
  Anthropic come *GitHub Secrets*. Il DB può essere committato come artifact o
  su branch dati (oppure, su Raspberry, persiste localmente).
- **Rischio/Autonomia**: medio — richiede i tuoi secret e una strategia di
  persistenza del DB nel runner effimero (artifact o commit). Su Raspberry è
  banale (cron + file locale).
- **Verdetto**: alto impatto. Consigliata subito dopo l'RPE.

### 🥉 3. Notifiche Telegram
**Cosa**: bot Telegram che, dopo l'analisi, invia "Analisi di oggi + prossimo
allenamento" sul telefono.
- **Perché**: chiude il loop dell'automazione (#2 produce, #3 consegna). Alto
  valore percepito, l'utente non deve aprire nulla.
- **Sforzo**: basso-medio. Telegram Bot API è gratuita e stabile; una funzione
  `notify()` + token in `.env`.
- **Costo**: zero. **Autonomia**: serve creare un bot (token) — credenziale
  semplice, una tantum.
- **Verdetto**: ottima in coppia con lo scheduling. Email come alternativa
  (SMTP) ma più attritosa.

### 4. Metriche di forma avanzate
**Cosa**: **efficienza aerobica** (FC media / passo medio nel tempo) e
**deriva cardiaca** (decoupling Pa:HR sulla seconda metà della corsa).
- **Perché**: arricchisce la diagnosi di forma oltre l'ACWR.
- **Sforzo**: l'efficienza FC/passo è *bassa* (dati già disponibili). La
  **deriva cardiaca vera** è *media-alta*: richiede le **serie temporali HR**,
  che oggi **non** sintetizziamo (teniamo solo avg/max). Va esteso
  `synthesize()` per estrarre gli split/stream ridotti.
- **Verdetto**: spaccare in due — fare *subito* l'efficienza FC/passo (quick
  win), rimandare la deriva cardiaca a quando servono gli stream.

### 5. Export/Import dati (CSV/FIT) + backup
**Cosa**: `GET /api/export.csv`, import da file FIT/GPX come fallback se la
libreria Garmin si rompe.
- **Perché**: portabilità e resilienza (il documento cita l'export manuale come
  fallback al rischio "libreria non ufficiale").
- **Sforzo**: basso (CSV); medio (parsing FIT).
- **Verdetto**: utile come rete di sicurezza, non urgente. CSV export è un
  quick win opzionale.

### 6. Migrazioni schema (Alembic)
**Cosa**: versionamento dello schema DB.
- **Perché**: abilitante per tutte le feature che aggiungono colonne (taper,
  metriche). Oggi `create_all` basta ma non gestisce evoluzioni.
- **Verdetto**: igiene tecnica. Introdurla *quando* la prima feature cambia lo
  schema in modo non banale, non prima.

### 7. Obiettivo gara + taper
**Cosa**: data gara target → periodizzazione con scarico finale.
- **Perché**: altissimo valore per chi prepara una gara (5/10k, mezza, FIASP).
- **Sforzo**: alto. Richiede modello "obiettivo", logica di periodizzazione e
  prompt dedicati. Cambia lo schema (→ serve #6).
- **Verdetto**: feature "bandiera" della Fase 3, ma pesante. Dopo che
  automazione e RPE sono in produzione.

### 8. Pianificazione settimanale "deep" con Opus
**Cosa**: enhancement del piano settimanale con `claude-opus-4-8` + extended
thinking. La base **è già implementata** (`run_weekly_plan`).
- **Verdetto**: incrementale, costo token leggermente maggiore. Si attiva già
  via `PLANNER_MODEL`; vale come tuning, non come nuova feature.

### 9. Push workout sull'orologio Garmin
**Cosa**: creare workout strutturati e schedularli sul calendario Garmin.
- **Perché**: chiude *davvero* il cerchio (il workout arriva sul device).
- **Rischio**: **il più alto**. API di scrittura non ufficiali, formato workout
  complesso e fragile, rischio di rompere/duplicare dati reali sull'account.
  Richiede credenziali Garmin con scrittura.
- **Verdetto**: massimo valore ma massimo rischio/sforzo. Da fare **per ultima**
  in Fase 2, con molta cautela e dietro feature-flag.

### 10. Autenticazione dashboard
**Cosa**: login sulla UI.
- **Verdetto**: rilevante **solo** se esponi la dashboard fuori da localhost
  (es. tunnel/Raspberry pubblico). Finché è locale, non serve. Basso valore ora.

### 🔻 11. Self-tuning del prompt
**Cosa**: il coach che riscrive la propria metodologia nel tempo.
- **Perché no (ora)**: alto rischio di degradare la qualità senza un sistema di
  valutazione, costo token, complessità elevata, beneficio incerto.
- **Verdetto**: ricerca esplorativa, non roadmap di prodotto. Ultima.

---

## 4. Roadmap consigliata (ordine di esecuzione)

L'ordine tiene conto di valore, sforzo **e dipendenze**:

1. **Input RPE + note** — quick win, sblocca analisi più ricche. *(½ giorno)*
2. **Efficienza FC/passo** (sottoinsieme della #4) — quick win sui dati esistenti.
3. **Scheduling automatico** (GitHub Action o cron) — automazione del flusso.
4. **Notifiche Telegram** — consegna automatica dei report.
5. **Export CSV + import FIT** — resilienza/backup.
6. **Alembic** — appena una feature cambia lo schema.
7. **Obiettivo gara + taper** — feature bandiera, su base solida.
8. **Deriva cardiaca** (resto della #4, richiede stream HR).
9. **Push workout su Garmin** — per ultima, dietro feature-flag.

**Pacchetto consigliato per il primo sprint di Fase 2**: #1 + #2 + #3 + #4.
Insieme realizzano il salto di qualità più grande verso un prodotto
"autonomo e utile" mantenendo costo ≈ zero e rischio basso.

---

## 5. Raccomandazione finale

Partire da **Input RPE** (sblocca valore immediato a sforzo quasi nullo, il
campo esiste già) e a seguire **Scheduling automatico + Notifiche Telegram**,
che insieme realizzano l'obiettivo chiave del progetto: *ricevere
automaticamente analisi e prossimo allenamento con il minimo intervento umano*.
Rimandare **push su Garmin** e **self-tuning** per rischio/beneficio sfavorevole
nel breve termine.
