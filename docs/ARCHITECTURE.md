# Architettura

## Principio guida

Tre responsabilità separate in moduli indipendenti, come richiesto:
**raccolta dati**, **elaborazione**, **coaching**. Ogni modulo è testabile in
isolamento e comunica solo tramite gli schemi Pydantic in `app/schemas.py`.

```
┌──────────────┐   RunSummary   ┌──────────────┐  TrainingMetrics  ┌──────────────┐
│ collection/  │ ─────────────► │ processing/  │ ────────────────► │  coaching/   │
│ Garmin/Demo  │                │  metriche    │                   │  AI / regole │
└──────────────┘                └──────────────┘                   └──────────────┘
        \                              │                                  /
         \                             ▼                                 /
          └────────────────► services/ingest.py ◄───────────────────────┘
                                       │
                 ┌─────────────────────┼─────────────────────┐
                 ▼                     ▼                      ▼
            db/ (SQLite)         api/ (REST)          main.py (dashboard)
```

## Moduli

### `app/collection/` — raccolta dati
- `sources.py`: due implementazioni dietro il protocollo `ActivitySource`.
  - `GarminSource`: live via `python-garminconnect`, con cache dei token.
  - `DemoSource`: dati di esempio bundled (`data/demo_activities.json`).
  - `get_source()` sceglie in base alla presenza di credenziali.
- `synthesize.py`: trasforma il payload grezzo Garmin in `RunSummary` compatto
  (solo i campi informativi, niente stream secondo-per-secondo).

### `app/processing/` — elaborazione
- `metrics.py`: funzioni pure, niente I/O. Calcola:
  - **carico acuto** (7gg) e **cronico** (media settimanale su 28gg);
  - **ACWR** = acuto / cronico;
  - **monotonia** = media/deviazione del carico giornaliero (7gg);
  - **quota 80/20** = volume facile / volume totale;
  - **stato di forma** e **trend** del carico;
  - aggregazione settimanale per il grafico (`weekly_buckets`).

### `app/coaching/` — coaching
- `prompts.py`: la metodologia (system prompt) per analisi singola e settimanale.
- `coach.py`: due backend con la stessa interfaccia `Coach`:
  - `AICoach`: chiama Claude (modello configurabile);
  - `OfflineCoach`: logica a regole deterministica (fallback senza costi).
  - `get_coach()` sceglie in base alla presenza della API key.

### `app/services/ingest.py` — orchestrazione
L'unico punto che conosce tutti i layer: esegue ingest, persiste, calcola le
metriche e invoca il coach, salvando i `CoachingReport`.

### `app/db/` — persistenza
SQLAlchemy 2.0 su SQLite. Due tabelle: `activities` e `coaching_reports`.
L'astrazione tiene aperta la porta a Postgres/Turso senza toccare il resto.

### `app/api/` + `app/main.py` — interfacce
- REST API JSON sotto `/api`.
- Dashboard HTMX/Jinja/Bootstrap servita da `main.py`; gli endpoint `/ui/*`
  restituiscono frammenti HTML aggiornati in-place via HTMX.

## Modalità di esecuzione

| | Sorgente dati | Coach |
|---|---|---|
| Default (no chiavi) | `DemoSource` | `OfflineCoach` |
| Solo Garmin | `GarminSource` | `OfflineCoach` |
| Solo Anthropic | `DemoSource` | `AICoach` |
| Completo | `GarminSource` | `AICoach` |

Questo rende l'app sempre eseguibile e testabile in CI senza segreti.

## Scelte di design

- **SQLite invece di JSON**: query e trend reali, transazioni, una sola fonte di
  verità, costo zero.
- **Coach offline**: garantisce che il prodotto sia utile e dimostrabile anche
  a costo zero; l'AI è un potenziamento, non una dipendenza bloccante.
- **HTMX invece di React**: dashboard reattiva senza build frontend, niente
  Node, deploy banale.
- **Schemi Pydantic come contratto**: i moduli non si conoscono tra loro,
  solo i dati.
