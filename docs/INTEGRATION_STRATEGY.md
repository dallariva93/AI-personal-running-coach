# Strategia integrazioni dati — Garmin (non ufficiale) vs alternative

**Domanda**: l'app oggi si regge sulle API Garmin **non ufficiali**
(`python-garminconnect`). Per un prodotto destinato a uno Store non è
percorribile. Quale direzione prendere?

**Risposta breve**: nessuna singola opzione copre tutto. La strada a minor
rischio è a **due binari**: (1) candidarsi subito al programma ufficiale
Garmin — costo di tentativo quasi nullo; (2) in parallelo promuovere **Health
Connect + registrazione live GPS** (entrambi già implementati) a percorso
primario della build Store. Strava resta secondaria ma **attenzione: le sue
condizioni API vietano l'uso dei dati con modelli AI** — per un coach AI è un
problema fondativo, non un dettaglio. Il Garmin non ufficiale sopravvive solo
come modalità self-host/dev, mai nella build Store.

> Le condizioni commerciali/legali citate (termini Strava, processo Garmin,
> prezzi aggregatori) riflettono lo stato alla conoscenza di chi scrive
> (inizio 2026) e **vanno riverificate sui testi ufficiali prima di decidere**
> — vedi la checklist in fondo.

---

## 1. Perché lo status quo non è difendibile in uno Store

Come funziona oggi (`app/collection/sources.py::GarminSource`): il **backend fa
login su Garmin Connect con email e password dell'utente**
(`settings.garmin_email/garmin_password`), simula il client web e chiama
endpoint interni non documentati.

| Problema | Gravità | Dettaglio |
|---|---|---|
| **Violazione ToS Garmin** | Bloccante | Accesso automatizzato non autorizzato; Garmin può bannare l'account dell'utente (è successo ad altri progetti) |
| **Custodia delle password** | Bloccante | Il server detiene credenziali Garmin in chiaro/riutilizzabili. Per un prodotto multi-utente: responsabilità GDPR enorme, superficie d'attacco, e le policy Google Play vietano la raccolta di credenziali di servizi terzi fuori dai loro flussi ufficiali |
| **Fragilità tecnica** | Alto | La libreria si rompe a ogni cambio del sito Garmin (storicamente più volte l'anno); nessun SLA, nessun preavviso |
| **Scalabilità** | Alto | Garmin applica rate-limit e blocchi anti-bot (Cloudflare) sugli IP datacenter: con N utenti il pattern di traffico diventa indistinguibile da un attacco |
| **Review dello Store** | Medio | Un'app che chiede "inserisci la password Garmin" in un form proprio rischia il reject in review e la rimozione su segnalazione di Garmin |

**Conclusione**: per uso personale/self-host va bene; per lo Store va rimossa
dalla build o disattivata di default (feature-flag, vedi §7).

---

## 2. Opzione A — API ufficiali Garmin (Connect Developer Program)

### Cosa offre

Garmin ha un programma sviluppatori gratuito con più API distinte:

- **Activity API** — push (webhook) delle attività con **file FIT completo**:
  tutti gli stream per-secondo (HR, passo, cadenza, quota, potenza, dinamica
  di corsa), lap/ripetute, e i campi calcolati che il FIT contiene (incluso il
  Training Effect numerico).
- **Health API** — riepiloghi giornalieri push: **sonno (con fasi), stress,
  Body Battery, HRV, RHR, passi**, più "User Metrics" (**VO2max**, fitness age).
- **Training API** — permette di **inviare allenamenti strutturati al
  dispositivo** (il nostro workout builder direttamente sull'orologio: feature
  che oggi non possiamo offrire in alcun modo).
- **Courses API** — percorsi da/verso il dispositivo.

Modello: OAuth (l'utente autorizza, noi non vediamo mai la password), consegna
via **webhook push** (stesso pattern già costruito per Strava in
`strava_sync.py`: inbox durevole + worker), backfill storico su richiesta.

### Cosa si perde comunque rispetto al non ufficiale

Le metriche **solo-Connect** non esposte ufficialmente: **Training Readiness,
Stamina, Race Predictor di Garmin, messaggi testuali del TE, GAP di Garmin**.
Mitigazione: molte le calcoliamo già o possiamo calcolarle noi in
`app/processing/` (race prediction nostra esiste già; GAP derivabile da
stream quota+passo; zone HR calcolabili dagli stream + max HR profilo).

### Probabilità, costi, tempi

- **Costo di candidatura**: un form (descrizione app, entità sviluppatore,
  privacy policy, finalità d'uso dei dati). Gratuito.
- **Probabilità**: media. Garmin approva anche sviluppatori piccoli/singoli con
  app legittime (precedenti noti: intervals.icu, Runalyze e molte app di
  nicchia hanno l'accesso). Non è garantito e la review può chiedere
  chiarimenti; un'app "AI coach" con privacy policy seria e uso dati chiaro è
  un caso normale, non anomalo.
- **Tempi**: settimane (tipicamente 2–6) per l'evaluation access; poi
  production access.
- **Requisiti da preparare**: privacy policy pubblica, descrizione del
  trattamento dati, un'entità (anche ditta individuale) a cui intestare
  l'accordo.

### Impatto sul codebase

Sorprendentemente contenuto, perché l'architettura è già pronta:

| Pezzo | Oggi | Con API ufficiali |
|---|---|---|
| Trasporto | Polling con login credenziali | OAuth + webhook inbox — **pattern identico a Strava già implementato** (`strava_sync.py`) |
| Dati attività | JSON interni (`get_activity_details`) | **File FIT** → parser (`fitdecode`) — coerente con `GARMIN_DATA_PLAN.md` A10 che già eleva il FIT a formato canonico |
| Serie per-secondo | `extract_sample_streams` dal JSON | Stessa funzione, alimentata dal FIT (Fase 1 del piano dati sopravvive, cambia solo la sorgente) |
| Wellness | Snapshot da endpoint non ufficiali (Fase 0c) | Health API push → stessa tabella `daily_wellness` |
| Archivio grezzo | `GarminRawFetcher` (endpoint interni) | Archivia i FIT ricevuti via webhook — più semplice di oggi |

Stima: 2–4 settimane di lavoro una volta ottenuto l'accesso, in gran parte
riuso di pattern esistenti.

---

## 3. Opzione B — Solo Strava

### Cosa copre

- Attività da **qualsiasi marca** di orologio (i Garmin sincronizzano su
  Strava in automatico): summary, splits, polyline — già implementato — e
  **stream per-secondo** (HR, velocità, cadenza, potenza, quota) via endpoint
  `/streams` che oggi non usiamo ma è disponibile.
- OAuth + webhook: **già costruiti e funzionanti** nel nostro backend.

### Cosa NON copre (strutturale, non colmabile)

**Zero wellness**: niente sonno, HRV, RHR, Body Battery, stress, readiness.
Niente TE/VO2max/training load. Strava è un social di attività, non una
piattaforma salute. Il "coach che ti conosce" perderebbe l'intero contesto
recupero (Tier B di `GARMIN_DATA_PLAN.md` §A5) — colmabile solo affiancando
Health Connect (a quel punto non è più "solo Strava").

### ⚠️ Il problema fondativo: la clausola AI

Dalla revisione delle condizioni API Strava (novembre 2024), l'accordo
**vieta l'uso dei dati ottenuti via API con modelli di intelligenza
artificiale o applicazioni simili**, e Strava ha attivamente revocato
l'accesso ad app nel 2024–2025 su queste basi.

Il cuore di questo prodotto è **mandare i dati dell'atleta a Claude** per
analisi e coaching: esattamente il caso vietato. Le opzioni sarebbero:

1. chiedere a Strava un permesso scritto (improbabile per un'app piccola, e
   comunque revocabile);
2. escludere i dati di origine Strava dal contesto passato all'LLM (tenerli
   solo per grafici/statistiche) — tecnicamente fattibile col nostro campo
   `source`, ma **azzoppa il prodotto** proprio sulla sua feature distintiva;
3. ignorare la clausola — non è un'opzione: revoca API + esposizione legale.

**Conclusione**: "rimuovere Garmin e usare solo Strava" è l'opzione che
*sembra* più semplice ed è in realtà la **più pericolosa** per questo
specifico prodotto. Strava può restare come fonte *secondaria e opzionale*
(comodità di aggregazione multi-marca), con i suoi dati esclusi dal contesto
LLM finché non c'è chiarezza scritta sulla clausola. **Da riverificare sul
testo vigente dell'API Agreement prima di ogni decisione.**

Nota operativa: rate limit di default bassi per app nuove (~100 richieste/15
min, ~1.000/giorno; aumenti su richiesta) — gestibile col nostro modello
webhook, ma un backfill storico massiccio va rateato.

---

## 4. Opzione C — Health Connect come fonte primaria (già implementata, A2)

### Cosa copre

L'app Garmin Connect (e Samsung Health, Fitbit, Polar Flow, Amazfit/Zepp…)
**scrive su Health Connect** sul telefono: sessioni di corsa (con serie HR e
percorso), sonno, passi, frequenza cardiaca, e su device recenti HRV. Il
nostro `HealthConnectSyncWorker` + `app/services/health_connect.py` già
importa corse e wellness (sonno/HRV) nel contratto `RunSummary`/`DailyCheckin`.

Vantaggi decisivi per lo Store:

- **API ufficiale Google, zero approvazioni di terzi**: serve solo la
  dichiarazione permessi salute nella Play Console (form standard).
- **L'utente autorizza sul proprio telefono**: i dati arrivano a noi
  direttamente dall'utente, **nessun vincolo contrattuale di terzi sull'uso
  (LLM incluso)** — a differenza di Strava.
- **Multi-marca gratis**: si aprono Samsung/Fitbit/Polar/Amazfit senza
  scrivere un'integrazione per ciascuno.

### Limiti

| Limite | Impatto | Mitigazione |
|---|---|---|
| Solo Android | Per ora il prodotto È Android-only | Diventa un vincolo solo con un futuro iOS (lì: HealthKit, stesso pattern) |
| Storia limitata (~30 giorni prima del consenso) | Niente backfill profondo | Export GDPR Garmin una tantum (l'utente scarica il proprio archivio FIT completo e lo importa — vedi Opzione E) |
| Niente metriche proprietarie Garmin (TE, VO2max, BB, readiness, stamina) | Il gap più grosso | In parte derivabili in `processing/` (zone HR, drift, decoupling, la nostra race prediction); il resto si perde davvero |
| Serve il telefono con l'app della marca installata | UX: sync non server-side | Il nostro worker già gestisce il sync in foreground/periodico |
| Fedeltà stream variabile per marca | HR campionato, non sempre 1s | Sufficiente per grafici e feature derivate |

### Impatto sul codebase

Basso: l'integrazione esiste. Il lavoro è **arricchirla** (splits reali dagli
stream HC invece del passo medio derivato, più tipi di record: RHR, stress se
disponibili) e promuoverla nella UX di onboarding come percorso principale.

---

## 5. Opzione D — Aggregatori commerciali (Terra API, Rook, Spike…)

Wrappano le API ufficiali di decine di marche (Garmin inclusa, tramite le loro
partnership) dietro un'unica API: accesso "ufficiale" a Garmin **senza
approvazione diretta di Garmin**.

- **Pro**: attivazione immediata, multi-marca, webhook, wellness inclusa.
- **Contro**: **costo ricorrente per utente/mese** (ordine di grandezza:
  centinaia di €/mese di minimi + scaglioni a volume — da preventivare), lock-in
  su un intermediario, e le loro condizioni d'uso dei dati vanno comunque
  lette (alcune vietano a loro volta certi usi).
- **Quando ha senso**: se la candidatura Garmin (Opzione A) fallisce **e** il
  prodotto ha un modello di ricavo che sostiene il costo per utente. Non ora.

---

## 6. Opzione E — Import file (FIT/GPX) e export GDPR

- L'utente esporta manualmente da Garmin Connect (singola attività o
  **l'intero archivio via export GDPR/takeout**, che è un diritto, non una
  API) e lo carica nell'app.
- **Pro**: zero rischio legale, perfetto per il **backfill storico una
  tantum** che Health Connect non può dare; il parser FIT serve comunque per
  l'Opzione A.
- **Contro**: UX pessima come flusso quotidiano.
- **Ruolo**: complemento, non alternativa. Da costruire quando c'è il parser
  FIT (già previsto da `GARMIN_DATA_PLAN.md` A10).

---

## 7. Matrice di confronto

Copertura dati (rispetto a ciò che l'app usa oggi):

| Dato | Non uff. (oggi) | A: Garmin uff. | B: Strava | C: Health Connect | D: Aggregatore |
|---|---|---|---|---|---|
| Attività + GPS | ✅ | ✅ (FIT) | ✅ | ✅ | ✅ |
| Stream per-secondo (HR/passo/quota/potenza) | ✅ | ✅ (FIT) | ✅ (streams) | ⚠️ parziale | ✅ |
| Ripetute/lap | ✅ | ✅ | ✅ | ⚠️ | ✅ |
| Training Effect / VO2max | ✅ | ✅ TE nel FIT / VO2max in Health API | ❌ | ❌ | ✅ |
| Sonno / HRV / RHR / stress / Body Battery | ✅ (piano 0c) | ✅ (Health API) | ❌ | ⚠️ sonno/HRV sì, BB no | ✅ |
| Training Readiness / Stamina / Race Predictor Garmin | ✅ | ❌ | ❌ | ❌ | ❌ |
| Push workout all'orologio | ❌ | ✅ (Training API) | ❌ | ❌ | ⚠️ dipende |
| Multi-marca (non-Garmin) | ❌ | ❌ | ✅ | ✅ | ✅ |

Rischio/costo:

| Criterio | Non uff. | A | B | C | D |
|---|---|---|---|---|---|
| Legale per Store | ❌ | ✅ | ⚠️ **clausola AI** | ✅ | ✅ |
| Dati usabili con l'LLM | ⚠️ (di fatto sì, ma base illegittima) | ✅ | ❌ senza deroga | ✅ | ⚠️ da contratto |
| Dipendenza da approvazione terzi | No | **Sì (rischio rifiuto)** | Sì (già ottenuta) | No | No (ma €) |
| Costo monetario | 0 | 0 | 0 | 0 | €€/utente |
| Lavoro di sviluppo | 0 | 2–4 settimane | ~1 settimana (streams) | ~1–2 settimane (arricchimento) | ~2 settimane |
| Stabilità nel tempo | ❌ | ✅ | ⚠️ (termini mutevoli) | ✅ | ⚠️ vendor |

---

## 8. Raccomandazione: strategia a due binari

**Binario 1 — subito, costo ~zero**: preparare e inviare la candidatura al
**Garmin Connect Developer Program** (privacy policy + descrizione app +
entità). È l'unica opzione che restituisce quasi tutto ciò che abbiamo oggi,
legalmente, e aggiunge il push dei workout all'orologio. Anche in caso di
rifiuto si è perso solo il tempo del form.

**Binario 2 — in parallelo, è il percorso Store**: promuovere **Health
Connect + registrazione live GPS (G1)** a percorso primario dell'app
pubblicata:
1. arricchire l'import HC (splits/serie HR reali, più record wellness);
2. onboarding che guida a installare Garmin Connect/altra app e collegare HC;
3. import FIT da export GDPR per il backfill storico;
4. colmare in `processing/` le metriche derivabili (zone HR, GAP, drift) —
   il coach resta pienamente funzionante, perde solo le metriche proprietarie
   Garmin non esposte da nessuna via ufficiale.

**Strava**: resta integrata ma **secondaria e opt-in**, con i suoi dati
**esclusi dal contesto LLM** (abbiamo già `source` per attività: un filtro nel
builder del contesto coach) finché la clausola AI non è chiarita per iscritto.
Non diventa mai la fondazione.

**Garmin non ufficiale**: retrocessa a **modalità self-host/sviluppo** dietro
feature-flag (`GARMIN_UNOFFICIAL_ENABLED`, default off in produzione), esclusa
dalla build Store e dalla documentazione utente. Per l'uso personale
dell'autore resta il ponte finché il Binario 1 o 2 non copre tutto.

**Aggregatori**: piano C, solo se la candidatura Garmin fallisce e c'è revenue.

### Effetto sulla roadmap dati (`GARMIN_DATA_PLAN.md`)

Il piano sopravvive con il trasporto sostituito: Fase 0a (bucket) invariata;
Fase 0c (wellness) si ri-basa su Health API (A) o Health Connect (C); Fase 1
(serie per-secondo) si ri-basa su FIT (A) o stream HC/Strava (C/B); la Fase 0b
(FIT canonico) diventa ancora più centrale. Nessuna fase va buttata.

---

## 9. Checklist di verifica prima di decidere (fatti da confermare)

- [ ] Leggere il testo **vigente** dello Strava API Agreement (sezione AI/ML e
      display dei dati) e le rate limit correnti dell'app registrata.
- [ ] Aprire il form del Garmin Connect Developer Program e verificarne i
      requisiti attuali (entità richiesta? tempi dichiarati? costi?).
- [ ] Verificare su un device reale **cosa scrive davvero** Garmin Connect in
      Health Connect oggi (route? serie HR a che frequenza? HRV? fasi sonno?) —
      15 minuti con l'app demo di HC Toolbox.
- [ ] Confermare che il FIT Garmin contenga i campi TE/VO2max che ci servono
      (aprire un proprio FIT con `fitdecode`).
- [ ] Preventivo reale di 1–2 aggregatori (Terra, Rook) come piano C.
- [ ] Bozza di privacy policy (serve comunque per Store, Garmin e Play
      Console health permissions).
