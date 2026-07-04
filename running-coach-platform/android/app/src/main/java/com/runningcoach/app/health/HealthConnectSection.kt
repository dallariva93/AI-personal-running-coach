package com.runningcoach.app.health

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.health.connect.client.PermissionController

/**
 * Onboarding/consent entry for Health Connect (Roadmap A2): "Non hai Garmin?".
 * Shows availability, requests the READ permissions and, once granted, kicks a
 * one-shot import. Fully self-contained: no plumbing from the parent screen.
 */
@Composable
fun HealthConnectSection() {
    val context = LocalContext.current
    val manager = remember { HealthConnectManager(context) }
    val available = remember { manager.isAvailable() }

    var granted by remember { mutableStateOf(false) }
    var status by remember { mutableStateOf<String?>(null) }

    val requestPermissions = rememberLauncherForPermissions(manager) { allGranted ->
        granted = allGranted
        if (allGranted) {
            status = "Health Connect collegato: importo le corse…"
            HealthConnectSyncWorker.syncNow(context)
        } else {
            status = "Permessi non concessi."
        }
    }

    LaunchedEffect(available) {
        if (available) granted = manager.hasAllPermissions()
    }

    Column(Modifier.fillMaxWidth()) {
        Text(
            "Health Connect",
            style = MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.Bold,
        )
        Spacer(Modifier.height(4.dp))
        Text(
            "Non hai Garmin? Collega Health Connect per importare corse, frequenza "
                + "cardiaca, sonno e HRV da qualsiasi app compatibile.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Spacer(Modifier.height(12.dp))

        when {
            !available -> Text(
                "Health Connect non è disponibile su questo dispositivo.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            granted -> Button(
                onClick = {
                    status = "Sincronizzo…"
                    HealthConnectSyncWorker.syncNow(context)
                },
                modifier = Modifier.fillMaxWidth(),
            ) { Text("Sincronizza ora da Health Connect") }
            else -> Button(
                onClick = { requestPermissions() },
                modifier = Modifier.fillMaxWidth(),
            ) { Text("Collega Health Connect") }
        }

        status?.let {
            Spacer(Modifier.height(8.dp))
            Text(it, style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.primary)
        }
    }
}

/**
 * Wraps Health Connect's permission-request contract in a Compose launcher and
 * returns a lambda that triggers it. On result, reports whether *all* requested
 * permissions were granted.
 */
@Composable
private fun rememberLauncherForPermissions(
    manager: HealthConnectManager,
    onResult: (Boolean) -> Unit,
): () -> Unit {
    val contract = remember { PermissionController.createRequestPermissionResultContract() }
    val launcher = androidx.activity.compose.rememberLauncherForActivityResult(contract) { granted ->
        onResult(granted.containsAll(manager.permissions))
    }
    return { launcher.launch(manager.permissions) }
}
