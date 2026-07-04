package com.runningcoach.app.ui.screens

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Share
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import com.runningcoach.app.data.model.RaceRecap
import com.runningcoach.app.data.model.WeeklyRecap
import com.runningcoach.app.data.repository.CoachRepository
import com.runningcoach.app.ui.components.RaceRecapCard
import com.runningcoach.app.ui.components.RecapCardRenderer
import com.runningcoach.app.ui.components.ScreenTitle
import com.runningcoach.app.ui.components.WeeklyRecapCard
import kotlinx.coroutines.launch
import java.io.File
import java.io.FileOutputStream

/**
 * Shareable recap screen (Roadmap A6): fetches the weekly summary (or, when
 * [activityId] is given, a race recap), previews it, and shares a rendered
 * PNG through the same [FileProvider] already configured for CSV/JSON export.
 * Self-contained (repository-driven), following the same pattern as
 * [CoachLogScreen]/[ShoesScreen].
 */
@Composable
fun RecapScreen(
    repository: CoachRepository,
    activityId: Int?,
    onBack: () -> Unit,
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    var weekly by remember { mutableStateOf<WeeklyRecap?>(null) }
    var race by remember { mutableStateOf<RaceRecap?>(null) }
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(activityId) {
        loading = true
        error = null
        runCatching {
            if (activityId != null) race = repository.raceRecap(activityId)
            else weekly = repository.weeklyRecap()
        }.onFailure { error = it.localizedMessage }
        loading = false
    }

    fun share() {
        val bitmap = race?.let { RecapCardRenderer.renderRace(it) }
            ?: weekly?.let { RecapCardRenderer.renderWeekly(it) }
            ?: return
        scope.launch {
            runCatching {
                val file = File(context.cacheDir, "recap_${System.currentTimeMillis()}.png")
                FileOutputStream(file).use { out ->
                    bitmap.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, out)
                }
                val uri: Uri = FileProvider.getUriForFile(
                    context, "${context.packageName}.fileprovider", file,
                )
                val intent = Intent(Intent.ACTION_SEND).apply {
                    type = "image/png"
                    putExtra(Intent.EXTRA_STREAM, uri)
                    addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                }
                context.startActivity(Intent.createChooser(intent, "Condividi recap"))
            }
        }
    }

    Column(
        Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .padding(horizontal = 16.dp, vertical = 12.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = onBack) {
                Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Indietro")
            }
            ScreenTitle(
                if (activityId != null) "Recap gara" else "Riepilogo settimanale",
                if (activityId != null) "Previsione vs reale" else "La tua settimana in breve",
                Modifier.weight(1f),
            )
        }
        Spacer(Modifier.height(12.dp))

        when {
            loading -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
            error != null -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Text(
                    "Errore: $error",
                    color = MaterialTheme.colorScheme.error,
                    modifier = Modifier.padding(24.dp),
                )
            }
            race != null -> {
                RaceRecapCard(race!!, Modifier.fillMaxWidth())
                Spacer(Modifier.height(20.dp))
                Button(onClick = { share() }, modifier = Modifier.fillMaxWidth()) {
                    Icon(Icons.Filled.Share, contentDescription = null)
                    Spacer(Modifier.height(0.dp))
                    Text("  Condividi")
                }
            }
            weekly != null -> {
                WeeklyRecapCard(weekly!!, Modifier.fillMaxWidth())
                Spacer(Modifier.height(20.dp))
                Button(onClick = { share() }, modifier = Modifier.fillMaxWidth()) {
                    Icon(Icons.Filled.Share, contentDescription = null)
                    Spacer(Modifier.height(0.dp))
                    Text("  Condividi")
                }
            }
        }
    }
}
