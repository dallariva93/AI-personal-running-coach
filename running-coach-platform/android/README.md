# Running Coach — App Android

App nativa **Kotlin + Jetpack Compose** (Material 3) per visualizzare allenamenti,
stato di forma e il **piano di allenamento generato dall'AI**. Consuma il backend
FastAPI via REST.

## Requisiti
- Android Studio (Giraffe 2022.3+), JDK 17
- Un emulatore o dispositivo con **Android 8.0+ (API 26)**
- Il backend in esecuzione e raggiungibile (è la radice del repo, vedi `../../README.md`)

## Build & run
1. Apri la cartella `android/` in Android Studio (genera in automatico il
   `gradle-wrapper.jar` — vedi `gradle/wrapper/README.md`).
2. Avvia un emulatore e premi **Run ▶**.

Da riga di comando (richiede il wrapper generato e l'Android SDK):
```bash
./gradlew assembleDebug      # produce app/build/outputs/apk/debug/app-debug.apk
```

## Configurazione del backend
Apri la scheda **Impostazioni** nell'app:
- **URL del backend**:
  - Emulatore + backend sul PC: `http://10.0.2.2:8000/`
  - Dispositivo reso sulla stessa rete: `http://<ip-del-pc>:8000/`
  - Backend online: `https://<tuo-host>/`
- **Token**: se il backend ha `API_TOKEN`, inseriscilo qui.

Le impostazioni sono salvate con DataStore e usate per tutte le chiamate.

## Struttura
```
app/src/main/java/com/runningcoach/app/
├── MainActivity.kt              # entry, applica il tema e l'AppScaffold
├── RunningCoachApp.kt           # Application + container DI minimale
├── data/
│   ├── model/Models.kt          # DTO (Gson) allineati al JSON del backend
│   ├── remote/ApiService.kt     # interfaccia Retrofit
│   ├── remote/ApiClient.kt      # builder Retrofit/OkHttp (auth + cache)
│   ├── repository/CoachRepository.kt
│   └── settings/SettingsStore.kt
├── ui/
│   ├── navigation/AppScaffold.kt   # bottom nav + NavHost
│   ├── screens/                    # Home, Activities, Plan, Settings
│   ├── components/Components.kt     # card forma, grafico, righe, report
│   ├── theme/                       # colori, tema Material 3
│   └── viewmodel/                   # OverviewViewModel, SettingsViewModel
```

## Architettura
MVVM: gli `ViewModel` espongono `StateFlow`, il `CoachRepository` risolve le
impostazioni correnti e chiama il backend via Retrofit. La schermata **Oggi** e
**Piano** condividono lo stesso `OverviewViewModel`, alimentato da una sola
chiamata `/api/mobile/overview`.

## Note
- HTTP in chiaro è permesso solo verso host locali/LAN (vedi
  `res/xml/network_security_config.xml`); in produzione usa HTTPS.
- Le chiamate AI possono richiedere alcuni secondi: il read timeout è 90s e la UI
  mostra un indicatore di avanzamento.
