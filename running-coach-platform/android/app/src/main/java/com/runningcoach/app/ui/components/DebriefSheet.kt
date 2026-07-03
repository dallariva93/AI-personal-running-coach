package com.runningcoach.app.ui.components

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import com.runningcoach.app.data.repository.CoachRepository
import kotlinx.coroutines.launch

/**
 * Post-run voice debrief (Roadmap A4). "Com'è andata?" — 20 seconds of the
 * athlete's own voice replace the crude Garmin proxies. On-device
 * [SpeechRecognizer] (free, no network) transcribes into an editable field;
 * typing is always available as a fallback. Sending POSTs to `/api/debrief`.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DebriefSheet(
    activityId: Int?,
    repository: CoachRepository,
    onDismiss: () -> Unit,
    onSent: (String) -> Unit,
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)

    var text by remember { mutableStateOf("") }
    var listening by remember { mutableStateOf(false) }
    var sending by remember { mutableStateOf(false) }

    val recognizerAvailable = remember { SpeechRecognizer.isRecognitionAvailable(context) }
    val recognizer = remember {
        if (recognizerAvailable) SpeechRecognizer.createSpeechRecognizer(context) else null
    }

    DisposableEffect(Unit) {
        onDispose { recognizer?.destroy() }
    }

    fun startListening() {
        val r = recognizer ?: return
        r.setRecognitionListener(object : RecognitionListener {
            override fun onReadyForSpeech(params: Bundle?) {}
            override fun onBeginningOfSpeech() {}
            override fun onRmsChanged(rmsdB: Float) {}
            override fun onBufferReceived(buffer: ByteArray?) {}
            override fun onEndOfSpeech() { listening = false }
            override fun onError(error: Int) { listening = false }
            override fun onPartialResults(partialResults: Bundle?) {}
            override fun onEvent(eventType: Int, params: Bundle?) {}
            override fun onResults(results: Bundle?) {
                val hyp = results
                    ?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                    ?.firstOrNull()
                    .orEmpty()
                text = if (text.isBlank()) hyp else "$text $hyp".trim()
                listening = false
            }
        })
        val intent = android.content.Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(
                RecognizerIntent.EXTRA_LANGUAGE_MODEL,
                RecognizerIntent.LANGUAGE_MODEL_FREE_FORM,
            )
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, "it-IT")
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, false)
        }
        listening = true
        r.startListening(intent)
    }

    val micPermission = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted -> if (granted) startListening() }

    fun onMicTap() {
        if (listening) {
            recognizer?.stopListening()
            listening = false
            return
        }
        val granted = ContextCompat.checkSelfPermission(
            context, Manifest.permission.RECORD_AUDIO,
        ) == PackageManager.PERMISSION_GRANTED
        if (granted) startListening() else micPermission.launch(Manifest.permission.RECORD_AUDIO)
    }

    fun send() {
        val payload = text.trim()
        if (payload.isEmpty() || sending) return
        sending = true
        scope.launch {
            runCatching { repository.postDebrief(payload, activityId) }
                .onSuccess {
                    onSent("Grazie! Ho aggiornato i tuoi numeri.")
                    onDismiss()
                }
                .onFailure {
                    onSent("Non sono riuscito a inviare il debrief, riprova.")
                    sending = false
                }
        }
    }

    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = sheetState) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 24.dp, vertical = 8.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text("Com'è andata?", style = androidx.compose.material3.MaterialTheme.typography.titleLarge)
            Text(
                "Raccontami in due parole la corsa: fatica, sensazioni, eventuali fastidi.",
                style = androidx.compose.material3.MaterialTheme.typography.bodyMedium,
            )

            if (recognizerAvailable) {
                FilledTonalButton(
                    onClick = { onMicTap() },
                    modifier = Modifier.fillMaxWidth(),
                    enabled = !sending,
                ) {
                    Icon(
                        if (listening) Icons.Filled.Stop else Icons.Filled.Mic,
                        contentDescription = null,
                    )
                    Spacer(Modifier.height(0.dp))
                    Text(if (listening) "  Sto ascoltando… tocca per fermare" else "  Parla")
                }
            }

            OutlinedTextField(
                value = text,
                onValueChange = { text = it },
                modifier = Modifier.fillMaxWidth(),
                label = { Text("Oppure scrivi qui") },
                minLines = 2,
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
                enabled = !sending,
            )

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.End,
            ) {
                Button(onClick = { send() }, enabled = text.isNotBlank() && !sending) {
                    if (sending) {
                        CircularProgressIndicator(
                            modifier = Modifier.height(18.dp),
                            strokeWidth = 2.dp,
                        )
                    } else {
                        Text("Invia")
                    }
                }
            }
            Spacer(Modifier.height(8.dp))
        }
    }
}
