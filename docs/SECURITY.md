# Sicurezza & privacy

Questo è un progetto a uso personale; le credenziali restano sulla tua macchina.

## Segreti
- Le credenziali stanno **solo** in `.env`, che è in `.gitignore` e non viene
  mai committato. Usa `.env.example` come template (senza valori).
- I token di sessione Garmin sono messi in cache in `.garmin_tokens/`
  (anch'esso ignorato da git) per evitare login ripetuti e gestire il 2FA.
- La `ANTHROPIC_API_KEY` viene letta dall'ambiente e passata all'SDK; non viene
  loggata.

## Database
- `data/running_coach.db` (SQLite) contiene i tuoi dati di allenamento. È
  ignorato da git. Per un backup, copia il file.

## Esposizione di rete
- Di default la dashboard ascolta su `127.0.0.1` (solo locale).
- Se la esponi (es. su Raspberry Pi o tramite tunnel), aggiungi un reverse proxy
  con autenticazione: l'app **non** implementa login utente.

## Dati medici
- Il coach non fornisce diagnosi. I suggerimenti sono prudenziali e orientati
  alla prevenzione degli infortuni; per dolori persistenti, riposo e medico.

## Cifratura at rest (A10, Passo 8)

**Cosa è cifrato:** i token OAuth Strava (`strava_accounts.access_token` /
`refresh_token`) sono cifrati con Fernet prima di toccare il disco; nel DB
esiste solo ciphertext (prefisso `enc:`). La chiave viene da
`DATA_ENCRYPTION_KEY` (env) o, in assenza, da `data/.encryption_key` generato
al primo uso (permessi 600, in `.gitignore`) con un warning nei log.

**Modello di minaccia coperto:** furto/leak del file SQLite o di un suo backup
— incluso il replica Litestream su S3, che copia *solo* il DB, non la chiave.
Un attaccante col dump non ottiene i token Strava. **Non coperto:** accesso
completo al volume (prende DB *e* chiave-file, se non hai impostato l'env) o
alla macchina in esecuzione. In produzione: `fly secrets set
DATA_ENCRYPTION_KEY=...` e conservane una copia — senza chiave i token cifrati
sono irrecuperabili (basta riconnettere Strava, ma è una seccatura).

**Trade-off dichiarato:** i dati sanitari (HRV, check-in, attività) restano in
chiaro perché ogni calcolo di metriche li interroga direttamente; cifrarli
per-riga costringerebbe a decifrare tutto in Python a ogni request. La
copertura completa at-rest (SQLCipher o volume cifrato) è pianificata con la
migrazione multi-utente (G4 / Passo 22).

## Diritto all'oblio (GDPR art. 17)

`DELETE /api/me/data?confirm=DELETE` svuota **tutte** le tabelle (attività,
check-in, piani, decisioni, eventi, chat, scarpe, Strava, raw assets, profilo,
sync_state) in un'unica transazione e cancella best-effort gli oggetti raw su
S3. Sopravvive solo `alembic_version` (storia dello schema, non dato
personale). La cancellazione azzera anche l'eventuale token API ruotato (vive
in `sync_state`): dopo l'erasure torna attivo il token della env var.

## Rate limiting

Token-bucket in-process su `/api/*`: 120 req/min per IP (`RATE_LIMIT_PER_MINUTE`),
30 req/min sul webhook Strava (`RATE_LIMIT_STRAVA_PER_MINUTE`) perché è l'unico
endpoint di scrittura non autenticato. Health/ready esenti (probe di Fly).
Risposta oltre soglia: `429` con `Retry-After: 60`. Nota: con più worker
uvicorn ogni processo ha i suoi bucket (limite effettivo = N× quello
configurato) — come la cache Q5, lo store condiviso arriva con G4.

## Rotazione del token API

`POST /api/auth/rotate` (autenticato) genera un nuovo bearer token e ne salva
**solo l'hash SHA-256** in `sync_state` — mai il token, così un leak del DB
non rivela la credenziale. Il token è mostrato una sola volta nella risposta;
il precedente (env o rotazione precedente) smette di valere immediatamente.
Recupero da token perso: cancella la riga `api_token_hash` da `sync_state`
(o usa il diritto all'oblio) → torna valido `API_TOKEN` della env.

## Segnalazioni
Trattandosi di uso personale non c'è un processo formale: apri una issue per
problemi di sicurezza nella gestione dei segreti o delle dipendenze.
