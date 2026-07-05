# Guida Completa Configurazione Firebase per AI Running Coach

**Scopo:** Configurare Firebase Cloud Messaging (FCM) per le notifiche push dell'app Android  
**Prerequisiti:** Account Google (nessun costo per il piano Spark gratuito)  
**Tempo stimato:** 15-20 minuti

---

## Panoramica

Firebase Cloud Messaging (FCM) permette all'app di ricevere notifiche push reali anche quando chiusa. L'app usa FCM per:
- Notifiche del coach dopo ogni corsa (execution score)
- Promemoria giornalieri delle sedute
- Alert importanti (rischio infortunio, cambiamenti piano)

---

## PASSO 1: Creare Progetto Firebase

### 1.1 Accedi alla Firebase Console
1. Vai su https://console.firebase.google.com/
2. Accedi con il tuo account Google
3. Clicca su **"Aggiungi progetto"** (o "Create a project" se in inglese)

### 1.2 Configura il progetto
1. **Nome progetto:** `AI Running Coach` (o quello che preferisci)
2. **Non abilitare Google Analytics** per questo progetto (non necessario per FCM)
3. Clicca **"Crea progetto"** (Create project)
4. Attendi che il progetto venga creato (30-60 secondi)
5. Clicca **"Continua"** (Continue)

---

## PASSO 2: Aggiungi App Android al Progetto

### 2.1 Registra l'app Android
1. Nella dashboard del progetto, guarda nel menu laterale sinistro
2. Cerca la sezione **"Build"** o **"Sviluppo"** (Build/Development)
3. Sotto questa sezione, cerca **"Android"** o clicca sull'icona **+** per aggiungere una nuova piattaforma
4. Se non trovi l'opzione, prova a cercare "Android" nella barra di ricerca in alto a sinistra
5. Una volta trovata l'opzione Android, cliccaci per iniziare la registrazione
6. **Nome pacchetto Android:** `com.runningcoach.app` (è nel file `android/app/build.gradle.kts`)
7. **Nome app (opzionale):** `AI Running Coach`
8. **Firma debug (opzionale):** Lascia vuoto per ora
9. Clicca **"Registra app"** (Register app)

### 2.2 Scarica il file di configurazione
1. Dopo la registrazione, vedrai un pulsante **"Scarica google-services.json"** (Download google-services.json)
2. Cliccalo per scaricare il file
3. **NON chiudere ancora la pagina** - ti servirà per i passi successivi

### 2.3 Posiziona google-services.json nel progetto
1. Copia il file `google-services.json` scaricato
2. Posizionalo in:
   ```
   /Users/sammy/PycharmProjects/AI-personal-running-coach/running-coach-platform/android/app/google-services.json
   ```
3. Assicurati che il percorso sia esattamente questo: `android/app/google-services.json`

### 2.4 Aggiungi il Firebase SDK (già fatto nel progetto)
Il progetto ha già le dipendenze necessarie nel `build.gradle.kts`:
- Plugin `google-services` è configurato in modo condizionale (si applica solo se `google-services.json` è presente)
- Dipendenza `firebase-messaging` è già presente
- Dipendenza `androidx.health.connect` è già presente (per Health Connect)

**Nota importante:** Il plugin google-services è configurato per applicarsi solo quando il file `google-services.json` è presente. Questo significa che:
- **Senza il file:** L'app compila normalmente, ma FCM è disabilitato (le notifiche funzionano via polling)
- **Con il file:** L'app compila con FCM abilitato per notifiche push reali

Puoi saltare questo passo e cliccare **"Avanti"** (Next) nella console Firebase.

### 2.5 Esegui l'app per verificare
1. Clicca **"Avanti"** (Next) per saltare il passo di verifica
2. Clicca **"Salta questo passaggio"** (Skip this step) per ora
3. Verrai reindirizzato alla dashboard del progetto

---

## PASSO 3: Configura Cloud Messaging

> **Nota:** Il menu laterale **"Messaging"** serve principalmente per creare campagne
> di notifiche grafiche. Per la configurazione tecnica (API, chiavi, certificati)
> devi usare le **Impostazioni progetto**, come descritto sotto.

### 3.1 Verifica Cloud Messaging
1. Clicca sull'icona **ingranaggio** ⚙️ in alto a sinistra, accanto a **"Panoramica del progetto"** (Project Overview)
2. Seleziona **"Impostazioni progetto"** (Project settings)
3. Vai alla scheda **"Cloud Messaging"**
4. **Buona notizia:** per i nuovi progetti Firebase l'API moderna e sicura (**FCM HTTP v1**) è **già abilitata di default**. Nella maggior parte dei casi non devi fare nulla.
5. **API Legacy (solo se serve):** se un servizio richiede la vecchia API legacy e la vedi disabilitata sotto "Cloud Messaging API (Legacy)", clicca sui **tre puntini verticali** accanto ad essa → **"Gestisci API in Google Cloud Console"** → **"Abilita"**. Per questo progetto **non è necessaria**.

### 3.2 Cosa fare adesso

**Per l'app Android (già fatto):**
- Hai già scaricato `google-services.json` e posizionato in `android/app/` ✅
- Questo file basta per far funzionare l'app Android con FCM

**Per il backend (quando invierai notifiche dal server):**
1. Sempre in **Impostazioni progetto**, vai alla scheda **"Account di servizio"** (Service accounts)
2. Clicca su **"Genera nuova chiave privata"** (Generate new private key)
3. Conferma e scarica il file JSON delle credenziali
4. Questo file servirà al backend FastAPI per autenticarsi con i server Firebase e inviare push (vedi PASSO 6)

---

## PASSO 4: Verifica la Configurazione

### 4.1 Pulisci e rebuild il progetto Android
1. In Android Studio, vai su **Build** → **Clean Project**
2. Poi **Build** → **Rebuild Project**
3. Non dovresti più vedere l'errore `google-services.json is missing`

### 4.2 Verifica che l'app compili
1. Clicca su **Run** (▶️) in Android Studio
2. L'app dovrebbe compilare e avviarsi sull'emulatore o dispositivo
3. Se compila correttamente, Firebase è configurato correttamente

---

## PASSO 5: Test delle Notifiche (opzionale)

### 5.1 Invia una notifica di test dalla console
1. Nella Firebase Console, vai su **Cloud Messaging**
2. Clicca su **"Invia il tuo primo messaggio"** (Send your first message)
3. **Titolo notifica:** `Test AI Running Coach`
4. **Corpo notifica:** `Questa è una notifica di test`
5. Clicca **"Invia messaggio di test"** (Send test message)
6. Inserisci il **token di registrazione FCM** del tuo dispositivo (lo troverai nei log quando l'app avvia)
7. Clicca **"Test"**

---

## PASSO 6: Configurazione Backend (per il futuro)

Quando vorrai integrare FCM nel backend FastAPI:

### 6.1 Installa le dipendenze Python
```bash
pip install firebase-admin
```

### 6.2 Configura le credenziali nel backend
1. Nella Firebase Console, vai su **Impostazioni progetto** → **Account di servizio**
2. Clicca su **"Genera nuova chiave privata"** (Generate new private key)
3. Scarica il file JSON (chiamalo `firebase-service-account.json`)
4. Posizionalo nella root del progetto (o in una cartella `secrets/`)
5. Aggiungi il percorso al file nel `.env`:
   ```
   FIREBASE_SERVICE_ACCOUNT_PATH=secrets/firebase-service-account.json
   ```

### 6.3 Codice backend per inviare notifiche
Il backend avrà bisogno di:
- Un endpoint per registrare i token FCM dei dispositivi
- Un servizio per inviare notifiche push
- Integrazione con il sistema di decisioni del coach

---

## Risoluzione Problemi

### Errore: "google-services.json is missing"
- Verifica che il file sia in `android/app/google-services.json`
- Verifica che il nome del file sia esattamente `google-services.json` (non `google-services.json.txt`)
- Pulisci e rebuild il progetto
- **Nota:** Con la configurazione condizionale del plugin, questo errore non dovrebbe più verificarsi - l'app compila anche senza il file

### Errore: "Package name mismatch"
- Verifica che il package name in Firebase Console sia esattamente `com.runningcoach.app`
- Controlla nel file `android/app/build.gradle.kts` alla riga `applicationId`

### Le notifiche non arrivano
- Verifica che l'app abbia i permessi necessari nel manifest
- Controlla i log di Android Studio per errori FCM
- Assicurati che il dispositivo abbia connessione internet
- Verifica che le notifiche siano abilitate nelle impostazioni del sistema

---

## Costi

Il piano **Firebase Spark** è gratuito e include:
- Fino a 10.000 notifiche push al giorno
- Analytics gratuito
- Authentication gratuito
- Realtime Database gratuito

Per un'app personale o piccola, il piano gratuito è più che sufficiente.

---

## Note Importanti

1. **Non committare google-services.json** - Questo file contiene credenziali sensibili. È già nel `.gitignore` del progetto Android.

2. **Per ambiente di produzione:** Quando distribuirai l'app, dovrai:
   - Creare una variante release in Firebase Console
   - Firmare l'app con una keystore release
   - Scaricare il `google-services.json` per la release

3. **Per team di sviluppo:** Ogni sviluppatore dovrebbe avere il proprio file `google-services.json` dal proprio progetto Firebase o usare lo stesso progetto con configurazioni multiple.

---

## Riferimenti Utili

- [Documentazione Firebase Cloud Messaging](https://firebase.google.com/docs/cloud-messaging)
- [Guida Firebase per Android](https://firebase.google.com/docs/android/setup)
- [Setup FCM in Android](https://firebase.google.com/docs/cloud-messaging/android/client)

---

## Prossimi Passi

Una volta configurato Firebase:
1. Verifica che l'app compili senza errori
2. Testa le notifiche dalla console Firebase
3. Implementa il backend per inviare notifiche dal server
4. Integra le notifiche con il sistema di decisioni del coach
