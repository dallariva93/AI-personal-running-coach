package com.runningcoach.app.ui.screens

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.runningcoach.app.data.model.Shoe
import com.runningcoach.app.data.model.ShoeIn
import com.runningcoach.app.data.repository.CoachRepository
import com.runningcoach.app.ui.viewmodel.ViewModelFactory
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ShoesScreen(
    repository: CoachRepository,
    onBack: () -> Unit,
) {
    val scope = rememberCoroutineScope()
    var shoes by remember { mutableStateOf<List<Shoe>>(emptyList()) }
    var loading by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var showAddDialog by remember { mutableStateOf(false) }
    var editingShoe by remember { mutableStateOf<Shoe?>(null) }

    fun loadShoes() {
        scope.launch {
            loading = true
            error = null
            try {
                shoes = repository.getShoes(includeRetired = false)
            } catch (e: Exception) {
                error = e.message
            } finally {
                loading = false
            }
        }
    }

    LaunchedEffect(Unit) { loadShoes() }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Scarpe") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Indietro")
                    }
                },
                actions = {
                    IconButton(onClick = { showAddDialog = true }) {
                        Icon(Icons.Default.Add, contentDescription = "Aggiungi scarpa")
                    }
                }
            )
        }
    ) { padding ->
        when {
            loading -> Box(
                modifier = Modifier.fillMaxSize().padding(padding),
                contentAlignment = Alignment.Center
            ) { CircularProgressIndicator() }
            error != null -> Box(
                modifier = Modifier.fillMaxSize().padding(padding),
                contentAlignment = Alignment.Center
            ) { Text("Errore: $error", color = MaterialTheme.colorScheme.error) }
            shoes.isEmpty() -> Box(
                modifier = Modifier.fillMaxSize().padding(padding),
                contentAlignment = Alignment.Center
            ) { Text("Nessuna scarpa registrata") }
            else -> LazyColumn(
                modifier = Modifier.fillMaxSize().padding(padding),
                contentPadding = PaddingValues(16.dp)
            ) {
                items(shoes) { shoe ->
                    ShoeCard(
                        shoe = shoe,
                        onClick = { editingShoe = shoe },
                        onRetire = {
                            scope.launch {
                                try {
                                    repository.updateShoe(
                                        shoe.id,
                                        ShoeIn(
                                            name = shoe.name,
                                            brand = shoe.brand,
                                            model = shoe.model,
                                            purchaseDate = shoe.purchaseDate,
                                            maxKm = shoe.maxKm,
                                            retired = true,
                                            notes = shoe.notes,
                                        ),
                                    )
                                    loadShoes()
                                } catch (e: Exception) {
                                    error = e.message
                                }
                            }
                        }
                    )
                }
            }
        }
    }

    if (showAddDialog) {
        ShoeDialog(
            onDismiss = { showAddDialog = false },
            onSave = { shoeIn ->
                scope.launch {
                    try {
                        repository.createShoe(shoeIn)
                        loadShoes()
                        showAddDialog = false
                    } catch (e: Exception) {
                        error = e.message
                    }
                }
            }
        )
    }

    editingShoe?.let { shoe ->
        ShoeDialog(
            existing = shoe,
            onDismiss = { editingShoe = null },
            onSave = { shoeIn ->
                scope.launch {
                    try {
                        repository.updateShoe(shoe.id, shoeIn)
                        loadShoes()
                        editingShoe = null
                    } catch (e: Exception) {
                        error = e.message
                    }
                }
            }
        )
    }
}

@Composable
fun ShoeCard(
    shoe: Shoe,
    onClick: () -> Unit,
    onRetire: () -> Unit,
) {
    Card(
        modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
        onClick = onClick
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(
                text = shoe.name,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold
            )
            if (shoe.brand != null || shoe.model != null) {
                Text(
                    text = listOfNotNull(shoe.brand, shoe.model).joinToString(" "),
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
            Spacer(modifier = Modifier.height(8.dp))
            Row(
                horizontalArrangement = Arrangement.SpaceBetween,
                modifier = Modifier.fillMaxWidth()
            ) {
                Text("${shoe.totalKm} km / ${shoe.maxKm} km")
                Text(
                    text = "${shoe.wearPct.toInt()}%",
                    color = when {
                        shoe.replacementDue -> MaterialTheme.colorScheme.error
                        shoe.wearPct > 80 -> MaterialTheme.colorScheme.tertiary
                        else -> MaterialTheme.colorScheme.primary
                    }
                )
            }
            if (shoe.replacementDue) {
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text = "Sostituzione consigliata",
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodySmall
                )
            }
        }
    }
}

@Composable
fun ShoeDialog(
    existing: Shoe? = null,
    onDismiss: () -> Unit,
    onSave: (ShoeIn) -> Unit,
) {
    var name by remember { mutableStateOf(existing?.name ?: "") }
    var brand by remember { mutableStateOf(existing?.brand ?: "") }
    var model by remember { mutableStateOf(existing?.model ?: "") }
    var maxKm by remember { mutableStateOf(existing?.maxKm?.toString() ?: "800") }
    var notes by remember { mutableStateOf(existing?.notes ?: "") }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(if (existing == null) "Nuova scarpa" else "Modifica scarpa") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(
                    value = name,
                    onValueChange = { name = it },
                    label = { Text("Nome") },
                    singleLine = true
                )
                OutlinedTextField(
                    value = brand,
                    onValueChange = { brand = it },
                    label = { Text("Marca") },
                    singleLine = true
                )
                OutlinedTextField(
                    value = model,
                    onValueChange = { model = it },
                    label = { Text("Modello") },
                    singleLine = true
                )
                OutlinedTextField(
                    value = maxKm,
                    onValueChange = { maxKm = it },
                    label = { Text("Max km") },
                    singleLine = true
                )
                OutlinedTextField(
                    value = notes,
                    onValueChange = { notes = it },
                    label = { Text("Note") },
                    minLines = 2
                )
            }
        },
        confirmButton = {
            TextButton(
                onClick = {
                    onSave(
                        ShoeIn(
                            name = name,
                            brand = brand.ifBlank { null },
                            model = model.ifBlank { null },
                            maxKm = maxKm.toDoubleOrNull() ?: 800.0,
                            notes = notes.ifBlank { null }
                        )
                    )
                },
                enabled = name.isNotBlank()
            ) { Text("Salva") }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("Annulla") }
        }
    )
}
