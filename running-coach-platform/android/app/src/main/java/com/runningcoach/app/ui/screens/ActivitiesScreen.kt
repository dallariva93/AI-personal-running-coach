package com.runningcoach.app.ui.screens

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.runningcoach.app.ui.components.ActivityRow
import com.runningcoach.app.ui.viewmodel.OverviewUiState

@Composable
fun ActivitiesScreen(state: OverviewUiState) {
    val activities = state.overview?.activities.orEmpty()
    Column(Modifier.fillMaxSize().padding(horizontal = 16.dp)) {
        Text(
            "Allenamenti",
            style = MaterialTheme.typography.headlineSmall,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.padding(vertical = 16.dp),
        )
        if (activities.isEmpty()) {
            Text(
                "Nessuna corsa. Vai su Oggi e premi Sincronizza.",
                style = MaterialTheme.typography.bodyMedium,
            )
        } else {
            LazyColumn(Modifier.fillMaxSize()) {
                items(activities) { ActivityRow(it) }
            }
        }
    }
}
