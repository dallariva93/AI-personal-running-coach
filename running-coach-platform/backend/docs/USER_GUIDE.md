# Guida utente — AI Running Coach

Questa guida ti accompagna dall'installazione all'uso quotidiano del tuo coach
di corsa personale. Non serve essere programmatori: i comandi sono copia-incolla.

---

## Indice
1. [Cosa fa l'app](#1-cosa-fa-lapp)
2. [Installazione in 5 minuti](#2-installazione-in-5-minuti)
3. [Modalità demo vs dati reali](#3-modalità-demo-vs-dati-reali)
4. [Collegare Garmin](#4-collegare-garmin)
5. [Attivare il coach AI (Claude)](#5-attivare-il-coach-ai-claude)
6. [Usare la dashboard](#6-usare-la-dashboard)
7. [Usare la riga di comando](#7-usare-la-riga-di-comando)
8. [Capire i numeri](#8-capire-i-numeri)
9. [Domande frequenti](#9-domande-frequenti)

---

## 1. Cosa fa l'app

1. **Legge** le tue corse da Garmin Connect.
2. **Analizza** carico, intensità e stato di forma (rischio di affaticamento).
3. **Consiglia** la prossima sessione e un piano settimanale, come farebbe un
   allenatore, in italiano.

Funziona **subito** con dati di esempio e un coach "offline" gratuito. Quando
vuoi, aggiungi le tue credenziali per i dati reali e l'intelligenza di Claude.

---

## 2. Installazione in 5 minuti

### Opzione A — sul tuo computer (consigliata per iniziare)

Requisiti: Python 3.11+ installato.

```bash
git clone <url-del-repo> && cd AI-personal-running-coach
./scripts/bootstrap.sh        # crea tutto e carica i dati demo
source .venv/bin/activate
python -m app.cli serve       # apri http://127.0.0.1:8000
```

### Opzione B — con Docker

```bash
docker compose up --build     # apri http://localhost:8000
```

Hai finito: la dashboard è online con dati di esempio.

---

## 3. Modalità demo vs dati reali

| | Sorgente corse | Coach | Costo |
|---|---|---|---|
| **Demo** (default) | dati di esempio inclusi | regole offline | €0 |
| **Garmin** | le tue corse reali | regole offline | €0 |
| **AI** | dati di esempio | Claude | ~€1-2/mese |
| **Completo** | le tue corse reali | Claude | ~€1-2/mese |

Per cambiare modalità basta compilare il file `.env` (vedi sotto). Senza nulla
da configurare, resti in demo e tutto funziona.

---

## 4. Collegare Garmin

1. Copia il file di esempio: `cp .env.example .env`
2. Apri `.env` e compila:
   ```
   GARMIN_EMAIL=la-tua-email@esempio.it
   GARMIN_PASSWORD=la-tua-password
   ```
3. Salva. Al primo avvio l'app fa il login e **memorizza un token** in
   `.garmin_tokens/`, così non devi rifare il login ogni volta.
4. Sincronizza le corse:
   ```bash
   python -m app.cli ingest
   ```
   oppure, nella dashboard, premi **"Sincronizza corse"**.

> **2FA (verifica in due passaggi)**: se è attiva sul tuo account Garmin, il
> primo login potrebbe chiedere un codice. Dopo, il token salvato evita di
> ripeterlo.

> Le credenziali restano **solo** sul tuo dispositivo, nel file `.env` che non
> viene mai caricato online.

---

## 5. Attivare il coach AI (Claude)

1. Crea una API key su <https://console.anthropic.com> (fatturazione a consumo,
   pochi euro al mese per questo uso) e carica un piccolo credito.
2. Aggiungila in `.env`:
   ```
   ANTHROPIC_API_KEY=sk-ant-...
   ```
3. Riavvia l'app. Ora analisi e piani sono generati da Claude.

> **Niente paura per i costi o i guasti**: se la chiamata AI fallisce o la chiave
> manca, l'app passa **automaticamente** al coach offline a regole — non resti
> mai senza risposta.

---

## 6. Usare la dashboard

Apri <http://127.0.0.1:8000> (o l'indirizzo del tuo deploy). Trovi:

- **Stato di forma**: un semaforo (fresco / equilibrato / affaticato) con ACWR e
  quota di volume facile.
- **Andamento carico settimanale**: il grafico a barre dei km per settimana.
- I tre pulsanti in alto:
  - **Sincronizza corse** — scarica le ultime corse.
  - **Analizza ultima corsa** — analisi + prossimo allenamento.
  - **Piano settimanale** — analisi della settimana + piano dei prossimi giorni.
- **Report del coach**: lo storico delle analisi.
- **Ultime corse**: la tabella delle attività (puoi analizzarne una specifica).

I messaggi di conferma o di errore appaiono in cima all'area centrale.

---

## 7. Usare la riga di comando

Utile per automatizzare o lavorare senza interfaccia.

```bash
python -m app.cli ingest                 # scarica e salva le corse
python -m app.cli analyze                # analizza l'ultima corsa
python -m app.cli analyze --save         # ...e salva un report .md in data/reports/
python -m app.cli weekly --save          # analisi e piano settimanale
python -m app.cli metrics                # mostra le metriche (JSON)
python -m app.cli serve                  # avvia la dashboard
python -m app.cli migrate                # aggiorna lo schema del database
```

---

## 8. Capire i numeri

- **ACWR** (rapporto carico acuto/cronico): confronta gli ultimi 7 giorni con la
  media delle ultime 4 settimane.
  - sotto 0.8 → stai calando, hai margine per spingere;
  - tra 0.8 e 1.3 → zona ideale (basso rischio);
  - sopra 1.5 → stai aumentando troppo in fretta, meglio recuperare.
- **Quota facile (80/20)**: la percentuale di chilometri "facili". L'ideale è
  ~80% facile e 20% intenso.
- **Stato di forma**: traduzione "a semaforo" dell'ACWR e degli altri segnali.
- **Trend del carico**: se il volume settimanale sta salendo, è stabile o scende.

> Questi indicatori servono a prevenire gli infortuni. **Non sono diagnosi
> mediche**: per dolori persistenti, riposa e senti un medico.

---

## 9. Domande frequenti

**Devo pagare qualcosa?** No per l'infrastruttura. Solo, se vuoi l'AI, i token
di Claude (pochi euro al mese). Tutto il resto è gratuito.

**Funziona senza internet?** Sì in demo/offline. Per scaricare da Garmin e per
l'AI serve la connessione.

**I miei dati dove finiscono?** In un database SQLite locale
(`data/running_coach.db`). Le credenziali restano nel tuo `.env`.

**Posso usarlo dal telefono?** Sì, se fai il deploy online (vedi
[DEPLOYMENT.md](DEPLOYMENT.md)). Proteggi la dashboard con un token (`API_TOKEN`).

**Come faccio un backup?** Copia il file `data/running_coach.db`. Per i deploy
online vedi la sezione backup in [DEPLOYMENT.md](DEPLOYMENT.md).

**L'app ha smesso di leggere Garmin.** La libreria Garmin è non ufficiale e può
rompersi quando Garmin cambia il sito. Riprova più tardi; nel frattempo l'app
continua a funzionare sui dati già scaricati.
