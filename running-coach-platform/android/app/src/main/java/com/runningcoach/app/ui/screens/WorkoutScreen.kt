package com.runningcoach.app.ui.screens

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.expandVertically
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.DirectionsRun
import androidx.compose.material.icons.filled.ExpandLess
import androidx.compose.material.icons.filled.ExpandMore
import androidx.compose.material.icons.filled.FitnessCenter
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.filled.KeyboardArrowUp
import androidx.compose.material.icons.filled.NightsStay
import androidx.compose.material.icons.filled.Save
import androidx.compose.material.icons.filled.Speed
import androidx.compose.material.icons.filled.Timer
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.runningcoach.app.data.model.WorkoutSegment
import com.runningcoach.app.data.model.WorkoutTemplate
import com.runningcoach.app.ui.components.SurfaceCard
import com.runningcoach.app.ui.components.ThinDivider
import com.runningcoach.app.ui.theme.BrandGreen
import com.runningcoach.app.ui.theme.Coral
import com.runningcoach.app.ui.theme.Zone1
import com.runningcoach.app.ui.viewmodel.WorkoutUiState

// ─── Segment type colours ──────────────────────────────────────────────────────

private fun segmentColor(type: String): Color = when (type.lowercase()) {
    "warmup" -> Zone1
    "interval_block" -> Coral
    "threshold" -> Color(0xFFFF6D00)
    "easy" -> BrandGreen
    "cooldown" -> Zone1
    "marathon_pace" -> Color(0xFF2196F3)
    "strides" -> Color(0xFFFFAB40)
    else -> Zone1
}

private fun segmentLabel(type: String): String = when (type.lowercase()) {
    "warmup" -> "Riscaldamento"
    "interval_block" -> "Ripetute"
    "threshold" -> "Soglia"
    "easy" -> "Facile"
    "cooldown" -> "Defaticamento"
    "marathon_pace" -> "Ritmo Maratona"
    "strides" -> "Allunghi"
    else -> type.replaceFirstChar { it.uppercase() }
}

private fun segmentIcon(type: String): ImageVector = when (type.lowercase()) {
    "warmup", "cooldown", "easy" -> Icons.Filled.DirectionsRun
    "interval_block" -> Icons.Filled.Timer
    "threshold" -> Icons.Filled.Speed
    "marathon_pace" -> Icons.Filled.DirectionsRun
    "strides" -> Icons.Filled.Speed
    else -> Icons.Filled.FitnessCenter
}

private fun segmentSummary(seg: WorkoutSegment): String {
    val parts = mutableListOf<String>()
    if (seg.repetitions > 1) parts.add("${seg.repetitions}×")
    seg.workDistanceKm?.let { parts.add("${"%.1f".format(it)} km") }
    seg.workDurationSec?.let {
        val min = (it / 60).toInt()
        parts.add("${min} min")
    }
    seg.workPace?.let { parts.add("@ $it") }
    seg.restDurationSec?.let {
        val sec = it.toInt()
        parts.add("+ ${sec}s ${seg.restType ?: "rec"}")
    }
    return parts.joinToString(" ")
}

// ─── Root composable ─────────────────────────────────────────────────────────

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun WorkoutScreen(
    state: WorkoutUiState,
    onBack: () -> Unit,
    onAddSegment: (WorkoutSegment) -> Unit,
    onRemoveSegment: (Int) -> Unit,
    onMoveUp: (Int) -> Unit,
    onMoveDown: (Int) -> Unit,
    onUpdateSegment: (Int, WorkoutSegment) -> Unit,
    onSetName: (String) -> Unit,
    onSetType: (String) -> Unit,
    onSave: () -> Unit,
    onSuggest: (String, String?, String?, String?) -> Unit,
    onDelete: (Int) -> Unit,
    onLoadIntoBuilder: (WorkoutTemplate) -> Unit,
    onClearBuilder: () -> Unit,
) {
    val snackbar = remember { SnackbarHostState() }
    LaunchedEffect(state.error, state.successMessage) {
        val msg = state.error ?: state.successMessage
        if (msg != null) snackbar.showSnackbar(msg)
    }

    var selectedTab by rememberSaveable { mutableIntStateOf(0) }

    Scaffold(
        containerColor = MaterialTheme.colorScheme.background,
        snackbarHost = { SnackbarHost(snackbar) },
        topBar = {
            TopAppBar(
                title = { Text("Allenamenti", fontWeight = FontWeight.Bold) },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Indietro")
                    }
                },
            )
        },
    ) { padding ->
        Column(
            Modifier
                .fillMaxSize()
                .padding(padding),
        ) {
            TabRow(selectedTabIndex = selectedTab) {
                Tab(
                    selected = selectedTab == 0,
                    onClick = { selectedTab = 0 },
                    text = { Text("Builder") },
                )
                Tab(
                    selected = selectedTab == 1,
                    onClick = { selectedTab = 1 },
                    text = { Text("Libreria (${state.library.size})") },
                )
            }

            when (selectedTab) {
                0 -> BuilderTab(
                    state = state,
                    onAddSegment = onAddSegment,
                    onRemoveSegment = onRemoveSegment,
                    onMoveUp = onMoveUp,
                    onMoveDown = onMoveDown,
                    onUpdateSegment = onUpdateSegment,
                    onSetName = onSetName,
                    onSetType = onSetType,
                    onSave = onSave,
                    onSuggest = onSuggest,
                    onClearBuilder = onClearBuilder,
                )

                1 -> LibraryTab(
                    state = state,
                    onDelete = onDelete,
                    onLoadIntoBuilder = { template ->
                        onLoadIntoBuilder(template)
                        selectedTab = 0
                    },
                )
            }
        }
    }
}

// ─── Builder tab ─────────────────────────────────────────────────────────────

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun BuilderTab(
    state: WorkoutUiState,
    onAddSegment: (WorkoutSegment) -> Unit,
    onRemoveSegment: (Int) -> Unit,
    onMoveUp: (Int) -> Unit,
    onMoveDown: (Int) -> Unit,
    onUpdateSegment: (Int, WorkoutSegment) -> Unit,
    onSetName: (String) -> Unit,
    onSetType: (String) -> Unit,
    onSave: () -> Unit,
    onSuggest: (String, String?, String?, String?) -> Unit,
    onClearBuilder: () -> Unit,
) {
    val types = listOf("custom", "interval", "threshold", "easy", "long")
    val typeLabels = listOf("Custom", "Intervalli", "Soglia", "Facile", "Lungo")

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            OutlinedTextField(
                value = state.currentName,
                onValueChange = onSetName,
                label = { Text("Nome allenamento") },
                placeholder = { Text("es. Ripetute 5×1000m") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
            )
        }

        item {
            var typeExpanded by remember { mutableStateOf(false) }
            val currentIdx = types.indexOf(state.currentType).coerceAtLeast(0)
            ExposedDropdownMenuBox(
                expanded = typeExpanded,
                onExpandedChange = { typeExpanded = it },
            ) {
                OutlinedTextField(
                    value = typeLabels[currentIdx],
                    onValueChange = {},
                    readOnly = true,
                    label = { Text("Tipo") },
                    trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = typeExpanded) },
                    modifier = Modifier
                        .menuAnchor()
                        .fillMaxWidth(),
                )
                ExposedDropdownMenu(
                    expanded = typeExpanded,
                    onDismissRequest = { typeExpanded = false },
                ) {
                    typeLabels.forEachIndexed { idx, label ->
                        DropdownMenuItem(
                            text = { Text(label) },
                            onClick = {
                                onSetType(types[idx])
                                typeExpanded = false
                            },
                        )
                    }
                }
            }
        }

        item { ThinDivider() }

        if (state.currentBuilder.isEmpty()) {
            item {
                Box(
                    Modifier
                        .fillMaxWidth()
                        .padding(vertical = 16.dp),
                    contentAlignment = Alignment.Center,
                ) {
                    Text(
                        "Aggiungi segmenti con i pulsanti qui sotto.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        } else {
            itemsIndexed(state.currentBuilder) { idx, seg ->
                SegmentCard(
                    segment = seg,
                    position = idx,
                    total = state.currentBuilder.size,
                    onRemove = { onRemoveSegment(idx) },
                    onMoveUp = { onMoveUp(idx) },
                    onMoveDown = { onMoveDown(idx) },
                    onUpdate = { updated -> onUpdateSegment(idx, updated) },
                )
            }
        }

        item {
            WorkoutSummaryRow(state.currentBuilder)
        }

        item {
            QuickAddRow(onAddSegment)
        }

        item { ThinDivider() }

        item {
            AISuggestSection(
                suggesting = state.suggesting,
                onSuggest = onSuggest,
            )
        }

        item { ThinDivider() }

        item {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                OutlinedButton(onClick = onClearBuilder, modifier = Modifier.weight(1f)) {
                    Text("Pulisci")
                }
                Button(
                    onClick = onSave,
                    modifier = Modifier.weight(2f),
                    enabled = state.currentName.isNotBlank() && state.currentBuilder.isNotEmpty(),
                ) {
                    Icon(Icons.Filled.Save, contentDescription = null)
                    Spacer(Modifier.width(6.dp))
                    Text("Salva in libreria")
                }
            }
        }

        item { Spacer(Modifier.height(24.dp)) }
    }
}

// ─── Segment card ─────────────────────────────────────────────────────────────

@Composable
private fun SegmentCard(
    segment: WorkoutSegment,
    position: Int,
    total: Int,
    onRemove: () -> Unit,
    onMoveUp: () -> Unit,
    onMoveDown: () -> Unit,
    onUpdate: (WorkoutSegment) -> Unit,
) {
    var expanded by rememberSaveable(position) { mutableStateOf(false) }
    val color = segmentColor(segment.segmentType)

    SurfaceCard {
        Row(
            Modifier
                .fillMaxWidth()
                .clickable { expanded = !expanded },
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Box(
                Modifier
                    .size(40.dp)
                    .clip(CircleShape)
                    .background(color.copy(alpha = 0.18f)),
                contentAlignment = Alignment.Center,
            ) {
                Icon(
                    segmentIcon(segment.segmentType),
                    contentDescription = null,
                    tint = color,
                    modifier = Modifier.size(20.dp),
                )
            }
            Spacer(Modifier.width(10.dp))
            Column(Modifier.weight(1f)) {
                Text(
                    segmentLabel(segment.segmentType),
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = FontWeight.SemiBold,
                    color = color,
                )
                val summary = segmentSummary(segment)
                if (summary.isNotBlank()) {
                    Text(
                        summary,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
            }
            if (position > 0) {
                IconButton(onClick = onMoveUp, modifier = Modifier.size(32.dp)) {
                    Icon(Icons.Filled.KeyboardArrowUp, contentDescription = "Su", modifier = Modifier.size(18.dp))
                }
            }
            if (position < total - 1) {
                IconButton(onClick = onMoveDown, modifier = Modifier.size(32.dp)) {
                    Icon(Icons.Filled.KeyboardArrowDown, contentDescription = "Giù", modifier = Modifier.size(18.dp))
                }
            }
            IconButton(onClick = onRemove, modifier = Modifier.size(32.dp)) {
                Icon(Icons.Filled.Delete, contentDescription = "Rimuovi", tint = MaterialTheme.colorScheme.error, modifier = Modifier.size(18.dp))
            }
            Icon(
                if (expanded) Icons.Filled.ExpandLess else Icons.Filled.ExpandMore,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.size(20.dp),
            )
        }

        AnimatedVisibility(
            visible = expanded,
            enter = expandVertically(),
            exit = shrinkVertically(),
        ) {
            SegmentDetailFields(segment = segment, onUpdate = onUpdate)
        }
    }
}

@Composable
private fun SegmentDetailFields(segment: WorkoutSegment, onUpdate: (WorkoutSegment) -> Unit) {
    Column(
        Modifier
            .fillMaxWidth()
            .padding(top = 12.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        val isInterval = segment.segmentType.lowercase() == "interval_block"

        if (isInterval) {
            Row(
                Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Text(
                    "Ripetizioni",
                    style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier.weight(1f),
                )
                IconButton(
                    onClick = {
                        if (segment.repetitions > 1) onUpdate(segment.copy(repetitions = segment.repetitions - 1))
                    },
                ) { Text("−", style = MaterialTheme.typography.titleMedium) }
                Text(
                    "${segment.repetitions}",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                )
                IconButton(
                    onClick = { onUpdate(segment.copy(repetitions = segment.repetitions + 1)) },
                ) { Text("+", style = MaterialTheme.typography.titleMedium) }
            }
        }

        OutlinedTextField(
            value = segment.workDistanceKm?.let { "%.2f".format(it) } ?: "",
            onValueChange = { v ->
                onUpdate(segment.copy(workDistanceKm = v.toDoubleOrNull()))
            },
            label = { Text("Distanza lavoro (km)") },
            placeholder = { Text("es. 1.0") },
            modifier = Modifier.fillMaxWidth(),
            singleLine = true,
        )

        OutlinedTextField(
            value = segment.workDurationSec?.let { "${(it / 60).toInt()}" } ?: "",
            onValueChange = { v ->
                onUpdate(segment.copy(workDurationSec = v.toDoubleOrNull()?.times(60)))
            },
            label = { Text("Durata lavoro (min)") },
            placeholder = { Text("es. 10") },
            modifier = Modifier.fillMaxWidth(),
            singleLine = true,
        )

        OutlinedTextField(
            value = segment.workPace ?: "",
            onValueChange = { v -> onUpdate(segment.copy(workPace = v.ifBlank { null })) },
            label = { Text("Passo obiettivo (M:SS/km)") },
            placeholder = { Text("es. 4:30/km") },
            modifier = Modifier.fillMaxWidth(),
            singleLine = true,
        )

        if (isInterval) {
            OutlinedTextField(
                value = segment.restDurationSec?.let { "${it.toInt()}" } ?: "",
                onValueChange = { v ->
                    onUpdate(segment.copy(restDurationSec = v.toDoubleOrNull()))
                },
                label = { Text("Recupero (sec)") },
                placeholder = { Text("es. 90") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
            )
        }

        OutlinedTextField(
            value = segment.notes ?: "",
            onValueChange = { v -> onUpdate(segment.copy(notes = v.ifBlank { null })) },
            label = { Text("Note (opzionale)") },
            modifier = Modifier.fillMaxWidth(),
            singleLine = true,
        )
    }
}

// ─── Quick-add row ────────────────────────────────────────────────────────────

@Composable
private fun QuickAddRow(onAddSegment: (WorkoutSegment) -> Unit) {
    val quickAdds = listOf(
        "warmup" to "Riscaldamento",
        "interval_block" to "Ripetute",
        "threshold" to "Soglia",
        "cooldown" to "Defaticamento",
    )
    Column {
        Text(
            "AGGIUNGI SEGMENTO",
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(bottom = 8.dp),
        )
        Row(
            Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            quickAdds.forEach { (type, label) ->
                val color = segmentColor(type)
                FilledTonalButton(
                    onClick = {
                        onAddSegment(
                            WorkoutSegment(
                                position = 0,
                                segmentType = type,
                                repetitions = if (type == "interval_block") 5 else 1,
                                workDurationSec = if (type in listOf("warmup", "cooldown")) 600.0 else null,
                                workDistanceKm = if (type == "interval_block") 1.0 else null,
                            )
                        )
                    },
                    modifier = Modifier.weight(1f),
                    colors = ButtonDefaults.filledTonalButtonColors(
                        containerColor = color.copy(alpha = 0.15f),
                        contentColor = color,
                    ),
                ) {
                    Text(label, style = MaterialTheme.typography.labelSmall, maxLines = 1)
                }
            }
        }
    }
}

// ─── Workout summary ─────────────────────────────────────────────────────────

@Composable
private fun WorkoutSummaryRow(segments: List<WorkoutSegment>) {
    if (segments.isEmpty()) return
    val totalDistKm = computeEstimatedDistance(segments)
    val totalDurMin = computeEstimatedDuration(segments)
    Row(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(10.dp))
            .background(MaterialTheme.colorScheme.surfaceVariant)
            .padding(horizontal = 16.dp, vertical = 10.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text(
                totalDistKm?.let { "%.1f km".format(it) } ?: "–",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
                color = BrandGreen,
            )
            Text("Distanza est.", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text(
                totalDurMin?.let { "${it.toInt()} min" } ?: "–",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
                color = BrandGreen,
            )
            Text("Durata est.", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text(
                "${segments.size}",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
            )
            Text("Segmenti", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

private fun computeEstimatedDistance(segments: List<WorkoutSegment>): Double? {
    val easyPaceMinPerKm = 6.0
    var total = 0.0
    for (seg in segments) {
        val reps = maxOf(1, seg.repetitions)
        val paceMin = seg.workPace?.let { parsePaceMinPerKm(it) } ?: easyPaceMinPerKm
        val dist = when {
            seg.workDistanceKm != null -> seg.workDistanceKm * reps
            seg.workDurationSec != null -> (seg.workDurationSec / 60.0) / paceMin * reps
            else -> 0.0
        }
        total += dist
    }
    return if (total > 0) total else null
}

private fun computeEstimatedDuration(segments: List<WorkoutSegment>): Double? {
    val easyPaceMinPerKm = 6.0
    var total = 0.0
    for (seg in segments) {
        val reps = maxOf(1, seg.repetitions)
        val paceMin = seg.workPace?.let { parsePaceMinPerKm(it) } ?: easyPaceMinPerKm
        val dur = when {
            seg.workDistanceKm != null -> seg.workDistanceKm * paceMin * reps
            seg.workDurationSec != null -> (seg.workDurationSec / 60.0) * reps
            else -> 0.0
        }
        val rest = (seg.restDurationSec ?: 0.0) / 60.0 * reps
        total += dur + rest
    }
    return if (total > 0) total else null
}

private fun parsePaceMinPerKm(pace: String): Double {
    return try {
        val p = pace.replace("/km", "").trim()
        val parts = p.split(":")
        parts[0].toInt() + parts[1].toInt() / 60.0
    } catch (_: Exception) {
        6.0
    }
}

// ─── AI suggest section ───────────────────────────────────────────────────────

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun AISuggestSection(
    suggesting: Boolean,
    onSuggest: (String, String?, String?, String?) -> Unit,
) {
    val sessionTypes = listOf("intervals", "tempo", "long", "easy", "strides")
    val sessionLabels = listOf("Ripetute", "Soglia", "Lungo", "Facile", "Allunghi")
    var expanded by remember { mutableStateOf(false) }
    var selectedIdx by rememberSaveable { mutableIntStateOf(0) }
    var notes by rememberSaveable { mutableStateOf("") }

    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(
                Icons.Filled.AutoAwesome,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.primary,
                modifier = Modifier.size(18.dp),
            )
            Spacer(Modifier.width(6.dp))
            Text(
                "Suggerisci con AI",
                style = MaterialTheme.typography.labelLarge,
                fontWeight = FontWeight.SemiBold,
            )
        }
        ExposedDropdownMenuBox(
            expanded = expanded,
            onExpandedChange = { expanded = it },
        ) {
            OutlinedTextField(
                value = sessionLabels[selectedIdx],
                onValueChange = {},
                readOnly = true,
                label = { Text("Tipo sessione") },
                trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = expanded) },
                modifier = Modifier
                    .menuAnchor()
                    .fillMaxWidth(),
            )
            ExposedDropdownMenu(
                expanded = expanded,
                onDismissRequest = { expanded = false },
            ) {
                sessionLabels.forEachIndexed { idx, label ->
                    DropdownMenuItem(
                        text = { Text(label) },
                        onClick = {
                            selectedIdx = idx
                            expanded = false
                        },
                    )
                }
            }
        }
        OutlinedTextField(
            value = notes,
            onValueChange = { notes = it },
            label = { Text("Note per il coach (opzionale)") },
            placeholder = { Text("es. obiettivo 5K, gamba stanca...") },
            modifier = Modifier.fillMaxWidth(),
            singleLine = true,
        )
        Button(
            onClick = {
                onSuggest(sessionTypes[selectedIdx], null, null, notes.ifBlank { null })
            },
            modifier = Modifier.fillMaxWidth(),
            enabled = !suggesting,
        ) {
            if (suggesting) {
                CircularProgressIndicator(
                    modifier = Modifier.size(18.dp),
                    strokeWidth = 2.dp,
                    color = MaterialTheme.colorScheme.onPrimary,
                )
                Spacer(Modifier.width(8.dp))
            } else {
                Icon(Icons.Filled.AutoAwesome, contentDescription = null)
                Spacer(Modifier.width(6.dp))
            }
            Text("Genera")
        }
    }
}

// ─── Library tab ─────────────────────────────────────────────────────────────

@Composable
private fun LibraryTab(
    state: WorkoutUiState,
    onDelete: (Int) -> Unit,
    onLoadIntoBuilder: (WorkoutTemplate) -> Unit,
) {
    if (state.loading && state.library.isEmpty()) {
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            CircularProgressIndicator()
        }
        return
    }
    if (state.library.isEmpty()) {
        EmptyLibraryCard()
        return
    }
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        itemsIndexed(state.library) { _, template ->
            WorkoutCard(
                template = template,
                onDelete = { onDelete(template.id) },
                onLoad = { onLoadIntoBuilder(template) },
            )
        }
    }
}

@Composable
private fun EmptyLibraryCard() {
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        SurfaceCard(modifier = Modifier.padding(32.dp)) {
            Column(
                Modifier.fillMaxWidth(),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Icon(
                    Icons.Filled.FitnessCenter,
                    contentDescription = null,
                    modifier = Modifier.size(56.dp),
                    tint = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Spacer(Modifier.height(12.dp))
                Text(
                    "Nessun allenamento salvato",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                )
                Spacer(Modifier.height(4.dp))
                Text(
                    "Crea un allenamento nel tab Builder o usa AI per generarne uno.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

@Composable
private fun WorkoutCard(
    template: WorkoutTemplate,
    onDelete: () -> Unit,
    onLoad: () -> Unit,
) {
    SurfaceCard {
        Row(
            Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(Modifier.weight(1f)) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    Text(
                        template.name,
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.Bold,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.weight(1f, fill = false),
                    )
                    Box(
                        Modifier
                            .clip(RoundedCornerShape(4.dp))
                            .background(BrandGreen.copy(alpha = 0.15f))
                            .padding(horizontal = 6.dp, vertical = 2.dp),
                    ) {
                        Text(
                            template.type.uppercase(),
                            style = MaterialTheme.typography.labelSmall,
                            color = BrandGreen,
                            fontWeight = FontWeight.SemiBold,
                        )
                    }
                }
                val stats = buildList {
                    template.estimatedDistanceKm?.let { add("${"%.1f".format(it)} km") }
                    template.estimatedDurationMin?.let { add("${it.toInt()} min") }
                }
                if (stats.isNotEmpty()) {
                    Text(
                        stats.joinToString(" · "),
                        style = MaterialTheme.typography.labelMedium,
                        color = BrandGreen,
                        fontWeight = FontWeight.Medium,
                    )
                }
                val preview = template.segments
                    .sortedBy { it.position }
                    .joinToString(" → ") {
                        val label = when (it.segmentType.lowercase()) {
                            "warmup" -> "risc."
                            "cooldown" -> "defat."
                            "interval_block" -> "${it.repetitions}×${it.workDistanceKm?.let { d -> "${"%.0f".format(d * 1000)}m" } ?: "rep"}"
                            "threshold" -> "soglia"
                            "easy" -> "facile"
                            "strides" -> "${it.repetitions}×all."
                            else -> it.segmentType
                        }
                        label
                    }
                Text(
                    preview,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            Spacer(Modifier.width(8.dp))
            Column(horizontalAlignment = Alignment.End) {
                FilledTonalButton(onClick = onLoad) {
                    Icon(Icons.Filled.Add, contentDescription = null, modifier = Modifier.size(16.dp))
                    Spacer(Modifier.width(4.dp))
                    Text("Carica", style = MaterialTheme.typography.labelSmall)
                }
                Spacer(Modifier.height(4.dp))
                IconButton(onClick = onDelete, modifier = Modifier.size(32.dp)) {
                    Icon(
                        Icons.Filled.Delete,
                        contentDescription = "Elimina",
                        tint = MaterialTheme.colorScheme.error,
                        modifier = Modifier.size(18.dp),
                    )
                }
            }
        }
    }
}
