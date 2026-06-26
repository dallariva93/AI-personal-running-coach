# Gradle wrapper

Il file binario `gradle-wrapper.jar` non è incluso nel repository (è un binario).
Viene generato automaticamente quando apri il progetto in **Android Studio**,
oppure manualmente con Gradle installato:

```bash
gradle wrapper --gradle-version 8.7
```

Dopodiché `./gradlew assembleDebug` funzionerà da riga di comando.
