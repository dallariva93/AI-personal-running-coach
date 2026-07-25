# Attivare il connettore Claude — guida passo passo

Guida operativa per accendere il server MCP e collegarlo a claude.ai, così che
Claude possa fare da allenatore sui tuoi dati veri.

**Tempo necessario:** ~15 minuti. **Serve scrivere codice?** No, solo copiare
e incollare comandi.

> **Il codice è già online.** Il deploy su Fly parte da solo a ogni push (il
> workflow `deploy-fly.yml`), e quello del server MCP è già andato a buon fine.
> Non devi quindi "installare" niente: devi solo **accendere** la funzione, che
> di proposito nasce spenta.

---

## Prima di iniziare: cosa ti serve

| Cosa | Come verificare di averlo |
|---|---|
| Un abbonamento **claude.ai Pro o Max** | I connettori personalizzati non ci sono nel piano gratuito |
| Accesso al tuo account **Fly.io** | È dove gira l'app |
| Il **terminale** del tuo computer | Su Mac: `Applicazioni → Utility → Terminale`. Su Windows: `PowerShell`. Su Linux: il tuo terminale abituale |

Non serve avere il progetto scaricato sul computer: tutti i comandi qui sotto
parlano con Fly, non con i file locali.

---

## PARTE 1 — Fase 0: controllare che l'app sia sana

Obiettivo: assicurarsi che tutto funzioni **prima** di aggiungere il
connettore. Se qualcosa è rotto, è molto meglio scoprirlo adesso.

### Passo 1.1 — Installa il comando `fly` (solo la prima volta)

`fly` è il programma che comanda il tuo server. Se lo hai già usato in passato,
salta al passo 1.2.

Apri il terminale, incolla questo e premi Invio:

```sh
curl -L https://fly.io/install.sh | sh
```

Al termine chiudi e riapri il terminale (serve perché il sistema si accorga del
nuovo comando).

**Su Windows**, se il comando sopra non funziona, usa PowerShell con:

```powershell
pwsh -Command "iwr https://fly.io/install.ps1 -useb | iex"
```

### Passo 1.2 — Entra nel tuo account Fly

```sh
fly auth login
```

Si apre il browser: fai il login. Poi torna al terminale.

### Passo 1.3 — Controlla che l'app sia accesa

```sh
fly status --app ai-running-coach
```

**Cosa devi vedere:** una tabella con almeno una macchina in stato `started`.

- ✅ `started` → tutto bene, vai avanti.
- ⚠️ `stopped` → accendila con `fly machine start --app ai-running-coach`.
- ❌ *"Could not find App"* → sei entrato con l'account Fly sbagliato: rifai
  `fly auth login` con l'account giusto.

### Passo 1.4 — Controlla che l'app risponda davvero

Questo è il controllo più importante: chiede all'app "come stai?".

```sh
curl https://ai-running-coach.fly.dev/api/health
```

**Cosa devi vedere:** una riga di testo tipo questa (l'ordine può variare):

```json
{"status":"ok","version":"0.2.0","env":"production","garmin_enabled":true,
 "ai_enabled":false,"auth_enabled":true,"mode":"garmin","coach":"offline"}
```

Come leggerla:

| Campo | Valore atteso | Cosa significa |
|---|---|---|
| `status` | `ok` | L'app è viva |
| `env` | `production` | Sta girando in modalità produzione |
| `garmin_enabled` | `true` | Le credenziali Garmin ci sono (se `false` vedi passo 1.5) |
| `auth_enabled` | `true` | L'API è protetta da password (giusto così) |
| `ai_enabled` | `false` | Nessuna chiamata a pagamento verso Claude dal server — **è voluto**: l'intelligenza è Claude dalla chat, ed è già inclusa nel tuo abbonamento |

- ❌ Se non risponde nulla o dà errore, l'app è giù: guarda i log con
  `fly logs --app ai-running-coach` e fermati qui.

### Passo 1.5 — Controlla quali password (secret) sono configurate

```sh
fly secrets list --app ai-running-coach
```

Vedrai solo i **nomi**, mai i valori (è normale e giusto).

**Cosa dovresti trovare:**

| Nome | Serve per | Se manca |
|---|---|---|
| `GARMIN_EMAIL` e `GARMIN_PASSWORD` | Scaricare le corse da Garmin | Le corse non si aggiornano più |
| `API_TOKEN` | Proteggere dashboard e API | Chiunque può leggere i tuoi dati |
| `DATA_ENCRYPTION_KEY` | Cifrare i segreti salvati nel database | Ne viene creata una automaticamente |

Se ti manca `API_TOKEN`, creane uno adesso:

```sh
# 1. genera una password lunga a caso
python3 -c "import secrets; print(secrets.token_urlsafe(24))"

# 2. impostala (incolla il risultato del comando sopra al posto di INCOLLA_QUI)
fly secrets set API_TOKEN="INCOLLA_QUI" --app ai-running-coach
```

> **Nota:** ogni volta che imposti un secret, Fly riavvia l'app da solo. È
> normale che per ~30 secondi non risponda.

✅ **Fase 0 completata.** Se sei arrivato qui senza errori, l'app è sana.

---

## PARTE 2 — Fase 4: accendere il connettore

### Passo 2.1 — Genera la chiave segreta del connettore

Questa chiave finirà **dentro l'indirizzo web** del connettore. Chi conosce
l'indirizzo può leggere i tuoi dati di allenamento: trattala come una password.

```sh
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Ti stampa qualcosa tipo:

```
kJ8mN2pQ7vR4tL9wZ3bY6cF1hD5gS0aXyU7iO2eK4nM
```

**Copiala e tienila da parte** (incollala temporaneamente in una nota). Ti
serve due volte: adesso e al passo 2.4.

> Se `python3` non esiste sul tuo computer, va bene qualsiasi password lunga e
> casuale: almeno 30 caratteri fra lettere e numeri, senza spazi né simboli
> strani (`-` e `_` vanno bene).

### Passo 2.2 — Accendi il connettore sul server

Un unico comando, con **due** impostazioni. Sostituisci `INCOLLA_QUI` con la
chiave del passo 2.1:

```sh
fly secrets set \
  MCP_PATH_TOKEN="INCOLLA_QUI" \
  MCP_ALLOWED_HOSTS="ai-running-coach.fly.dev" \
  --app ai-running-coach
```

Cosa fanno le due impostazioni:

- **`MCP_PATH_TOKEN`** — accende il connettore e decide il suo indirizzo
  segreto. Senza questa, l'endpoint **non esiste proprio** (è il
  comportamento di default: spento e invisibile).
- **`MCP_ALLOWED_HOSTS`** — dice al server quale indirizzo è legittimo. Senza
  questa il connettore rifiuterebbe le richieste con un errore `421`
  incomprensibile, perché la libreria MCP di default accetta solo `localhost`.

L'app si riavvia da sola. Aspetta ~30 secondi.

### Passo 2.3 — Verifica che il connettore risponda

Sostituisci `INCOLLA_QUI` con la solita chiave. **Attenzione alla `/` finale**,
serve davvero:

```sh
curl -sS -X POST "https://ai-running-coach.fly.dev/mcp-INCOLLA_QUI/" \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{
       "protocolVersion":"2025-06-18","capabilities":{},
       "clientInfo":{"name":"curl","version":"1"}}}'
```

**Cosa devi vedere:** una risposta che contiene `"serverInfo"` e
`"running-coach"`. Anche se è illeggibile, va benissimo: significa che il
connettore parla.

Se invece vedi un errore, salta alla tabella *"Se qualcosa non va"* in fondo.

### Passo 2.4 — Collega il connettore a claude.ai

1. Apri **claude.ai** dal browser (sul computer, non dall'app telefono).
2. Vai in **Settings** (Impostazioni) → **Connectors** (Connettori).
3. Clicca **Add custom connector** (Aggiungi connettore personalizzato).
4. Nel campo dell'indirizzo incolla — con la `/` finale:

   ```
   https://ai-running-coach.fly.dev/mcp-INCOLLA_QUI/
   ```

5. Dai un nome riconoscibile, per esempio `Running Coach`.
6. Salva.

Claude si collega e mostra gli strumenti disponibili. **Devi vederne 8**:
`get_athlete_overview`, `get_training_metrics`, `list_activities`,
`get_activity_detail`, `get_current_training_plan`, `get_plan_week`,
`get_race_prediction`, `compare_periods`.

### Passo 2.5 — Attivalo in chat

Apri una chat nuova e assicurati che il connettore `Running Coach` sia attivo
(di solito c'è un'icona o un menù dei connettori vicino alla casella del
messaggio). A seconda della versione dell'interfaccia potrebbe essere già
acceso automaticamente.

---

## PARTE 3 — Il collaudo

Scrivi in chat:

> Come sta andando la mia preparazione?

**Cosa deve succedere:** Claude chiama `get_athlete_overview` (di solito lo
vedi comparire nell'interfaccia) e ti risponde citando i tuoi numeri veri —
volume settimanale, forma, fase del piano.

Altre domande per provare bene:

- *"Analizza la mia ultima corsa e dimmi com'è andata"*
- *"Confronta questo mese con il mese scorso"*
- *"Cosa ho in programma questa settimana?"*
- *"Il mio obiettivo di gara è realistico?"*

### Consiglio: crea un Progetto dedicato

Su claude.ai crea un **Progetto** chiamato `Running Coach` e incolla nelle sue
istruzioni:

> Sei il mio allenatore personale di corsa. Parti sempre da
> `get_athlete_overview` prima di rispondere. Ragiona sui dati veri e cita i
> numeri (TSB, ACWR, volume, readiness) spiegando cosa significano per me.
> Sii concreto e diretto come un allenatore esperto: una raccomandazione
> chiara, il perché in una riga, e i rischi se ci sono. Se i dati non bastano,
> dimmelo invece di inventare.

Così ogni chat dentro il progetto parte già calibrata, senza doverlo ripetere.

---

## Se qualcosa non va

| Cosa vedi | Perché | Cosa fare |
|---|---|---|
| `404` o *"Not Found"* | Il connettore è spento, o l'indirizzo è sbagliato | Controlla con `fly secrets list` che ci sia `MCP_PATH_TOKEN`; ricontrolla di aver incollato la chiave giusta e la `/` finale |
| `421 Misdirected Request` | `MCP_ALLOWED_HOSTS` manca o non combacia | Rifai il passo 2.2 assicurandoti che il valore sia esattamente `ai-running-coach.fly.dev` |
| `401 Unauthorized` | Stai chiamando un indirizzo che non è quello del connettore | L'indirizzo deve iniziare esattamente con `/mcp-` seguito dalla tua chiave |
| `429 Too Many Requests` | Troppe richieste in un minuto | Aspetta un minuto. Se ricapita: `fly secrets set RATE_LIMIT_MCP_PER_MINUTE=480 --app ai-running-coach` |
| Claude non vede nessuno strumento | Connettore non attivo in quella chat | Attivalo dal menù dei connettori, o apri una chat nuova |
| Claude risponde ma dice che non ha dati | Il database ha poche corse | Normale finché non fai il **backfill** (vedi sotto) |
| Non risponde niente / va in timeout | L'app è giù | `fly status --app ai-running-coach` e `fly logs --app ai-running-coach` |

### Come vedere cosa succede dal vivo

Utile mentre provi: lascia aperta una seconda finestra di terminale con

```sh
fly logs --app ai-running-coach
```

Vedrai comparire una riga per ogni chiamata di Claude.

---

## Cose importanti da sapere

**Se la chiave ti scappa** (la incolli per sbaglio da qualche parte pubblica),
cambiarla è immediato: rifai il passo 2.1 e il 2.2 con una chiave nuova. Il
vecchio indirizzo smette di funzionare all'istante. Poi aggiorna l'indirizzo
del connettore su claude.ai.

**Quanto è esposto?** Il connettore è di **sola lettura**: gli 8 strumenti
possono solo leggere. Nessuno può modificare il piano, cancellare corse o
cambiare impostazioni attraverso il connettore, nemmeno conoscendo
l'indirizzo. Le modifiche restano sull'API protetta da `API_TOKEN`.

**Costi:** zero in più. Il server non chiama mai l'API a pagamento di Claude
(`ai_enabled: false`); il ragionamento avviene nella chat, dentro il tuo
abbonamento claude.ai. Fly resta sul piano che usi già.

**Manca ancora una cosa:** al primo collegamento Claude vede solo le corse già
presenti nel database. Per avere **tutto lo storico (almeno un anno)** serve la
**Fase 1 — backfill** della roadmap (`docs/MCP_CONNECTOR_ROADMAP.md`), che non
è ancora stata implementata. Il connettore funziona lo stesso da subito, ma
sui confronti con l'anno scorso risponderà che non ha abbastanza dati.
