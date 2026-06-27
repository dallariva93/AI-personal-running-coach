package com.runningcoach.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Divider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import com.runningcoach.app.data.model.AthleteProfile
import com.runningcoach.app.data.settings.AppSettings

@Composable
fun SettingsScreen(
    settings: AppSettings?,
    profile: AthleteProfile?,
    onSave: (String, String) -> Unit,
    onSaveCoach: (String, String, String, String, String) -> Unit,
    onCheckin: (Double?, Int?, Int?, Int?) -> Unit,
) {
    var baseUrl by remember { mutableStateOf("") }
    var token by remember { mutableStateOf("") }
    var saved by remember { mutableStateOf(false) }

    LaunchedEffect(settings) {
        settings?.let {
            baseUrl = it.baseUrl
            token = it.token
        }
    }

    Column(
        Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
    ) {
        Text(
            "Impostazioni",
            style = MaterialTheme.typography.headlineMedium,
            fontWeight = FontWeight.Bold,
        )
        Spacer(Modifier.height(16.dp))
        Text(
            "Collega l'app al tuo backend AI Running Coach.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Spacer(Modifier.height(16.dp))

        OutlinedTextField(
            value = baseUrl,
            onValueChange = { baseUrl = it; saved = false },
            label = { Text("URL del backend") },
            placeholder = { Text("https://il-tuo-host/") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        Spacer(Modifier.height(12.dp))
        OutlinedTextField(
            value = token,
            onValueChange = { token = it; saved = false },
            label = { Text("Token di accesso (opzionale)") },
            singleLine = true,
            visualTransformation = PasswordVisualTransformation(),
            modifier = Modifier.fillMaxWidth(),
        )
        Spacer(Modifier.height(20.dp))
        val isInsecureUrl = baseUrl.startsWith("http://", ignoreCase = true) &&
            !baseUrl.contains("localhost") &&
            !baseUrl.contains("10.0.2.2") &&
            !baseUrl.contains("127.0.0.1")
        if (isInsecureUrl) {
            Spacer(Modifier.height(6.dp))
            Text(
                "⚠ Usa https:// — l'app correggerà automaticamente http:// in https://.",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.error,
            )
        }
        Spacer(Modifier.height(12.dp))
        Button(
            onClick = { onSave(baseUrl, token); saved = true },
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text("Salva connessione")
        }
        if (saved) {
            Spacer(Modifier.height(10.dp))
            Text("Salvato ✓", color = MaterialTheme.colorScheme.primary)
        }

        Spacer(Modifier.height(24.dp))
        Divider()
        Spacer(Modifier.height(16.dp))
        CoachSetupSection(profile = profile, onSaveCoach = onSaveCoach)

        Spacer(Modifier.height(24.dp))
        Divider()
        Spacer(Modifier.height(16.dp))
        CheckinSection(onCheckin = onCheckin)

        Spacer(Modifier.height(24.dp))
        Text(
            "Suggerimento: con l'emulatore Android usa http://10.0.2.2:8000/ " +
                "per raggiungere un backend in esecuzione sul tuo PC.",
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun CoachSetupSection(
    profile: AthleteProfile?,
    onSaveCoach: (String, String, String, String, String) -> Unit,
) {
    var goalType by remember { mutableStateOf("") }
    var targetDate by remember { mutableStateOf("") }
    var targetTime by remember { mutableStateOf("") }
    var level by remember { mutableStateOf("intermediate") }
    var risk by remember { mutableStateOf("moderate") }

    LaunchedEffect(profile) {
        profile?.let {
            level = it.level
            risk = it.riskTolerance
            it.goal?.let { g ->
                goalType = g.goalType
                targetDate = g.targetDate.orEmpty()
                targetTime = g.targetTime.orEmpty()
            }
        }
    }

    Text(
        "Obiettivo & calibrazione",
        style = MaterialTheme.typography.titleMedium,
        fontWeight = FontWeight.Bold,
    )
    Spacer(Modifier.height(4.dp))
    Text(
        "La gara obiettivo abilita previsione e periodizzazione; livello e " +
            "tolleranza al rischio tarano le soglie del coach.",
        style = MaterialTheme.typography.bodySmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
    Spacer(Modifier.height(12.dp))
    OutlinedTextField(
        value = goalType,
        onValueChange = { goalType = it },
        label = { Text("Tipo gara") },
        placeholder = { Text("marathon | half | 10k | 5k | general") },
        singleLine = true,
        modifier = Modifier.fillMaxWidth(),
    )
    Spacer(Modifier.height(10.dp))
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        OutlinedTextField(
            value = targetDate,
            onValueChange = { targetDate = it },
            label = { Text("Data (YYYY-MM-DD)") },
            singleLine = true,
            modifier = Modifier.weight(1f),
        )
        OutlinedTextField(
            value = targetTime,
            onValueChange = { targetTime = it },
            label = { Text("Tempo (HH:MM:SS)") },
            singleLine = true,
            modifier = Modifier.weight(1f),
        )
    }
    Spacer(Modifier.height(10.dp))
    ChoiceRow("Livello", listOf("beginner", "intermediate", "advanced"), level) { level = it }
    Spacer(Modifier.height(8.dp))
    ChoiceRow("Rischio", listOf("conservative", "moderate", "aggressive"), risk) { risk = it }
    Spacer(Modifier.height(14.dp))
    Button(
        onClick = { onSaveCoach(goalType, targetDate, targetTime, level, risk) },
        modifier = Modifier.fillMaxWidth(),
    ) {
        Text("Salva obiettivo e calibrazione")
    }
}

@Composable
private fun CheckinSection(onCheckin: (Double?, Int?, Int?, Int?) -> Unit) {
    var sleep by remember { mutableStateOf("") }
    var fatigue by remember { mutableStateOf("") }
    var soreness by remember { mutableStateOf("") }
    var motivation by remember { mutableStateOf("") }

    Text(
        "Check-in di oggi",
        style = MaterialTheme.typography.titleMedium,
        fontWeight = FontWeight.Bold,
    )
    Spacer(Modifier.height(4.dp))
    Text(
        "Sonno in ore; fatica, dolori e motivazione da 1 a 10.",
        style = MaterialTheme.typography.bodySmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
    Spacer(Modifier.height(12.dp))
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        OutlinedTextField(
            value = sleep,
            onValueChange = { sleep = it },
            label = { Text("Sonno h") },
            singleLine = true,
            modifier = Modifier.weight(1f),
        )
        OutlinedTextField(
            value = fatigue,
            onValueChange = { fatigue = it },
            label = { Text("Fatica") },
            singleLine = true,
            modifier = Modifier.weight(1f),
        )
    }
    Spacer(Modifier.height(10.dp))
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        OutlinedTextField(
            value = soreness,
            onValueChange = { soreness = it },
            label = { Text("Dolori") },
            singleLine = true,
            modifier = Modifier.weight(1f),
        )
        OutlinedTextField(
            value = motivation,
            onValueChange = { motivation = it },
            label = { Text("Motivazione") },
            singleLine = true,
            modifier = Modifier.weight(1f),
        )
    }
    Spacer(Modifier.height(14.dp))
    Button(
        onClick = {
            onCheckin(
                sleep.toDoubleOrNull(),
                fatigue.toIntOrNull(),
                soreness.toIntOrNull(),
                motivation.toIntOrNull(),
            )
        },
        modifier = Modifier.fillMaxWidth(),
    ) {
        Text("Salva check-in di oggi")
    }
}

/** A compact single-choice row rendered as a set of toggle buttons. */
@Composable
private fun ChoiceRow(
    label: String,
    options: List<String>,
    selected: String,
    onSelect: (String) -> Unit,
) {
    Text(label, style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.Bold)
    Spacer(Modifier.height(6.dp))
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        options.forEach { opt ->
            if (opt == selected) {
                Button(onClick = { onSelect(opt) }, modifier = Modifier.weight(1f)) {
                    Text(opt, style = MaterialTheme.typography.labelSmall)
                }
            } else {
                OutlinedButton(onClick = { onSelect(opt) }, modifier = Modifier.weight(1f)) {
                    Text(opt, style = MaterialTheme.typography.labelSmall)
                }
            }
        }
    }
}
