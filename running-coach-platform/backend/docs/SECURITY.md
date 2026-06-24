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

## Segnalazioni
Trattandosi di uso personale non c'è un processo formale: apri una issue per
problemi di sicurezza nella gestione dei segreti o delle dipendenze.
