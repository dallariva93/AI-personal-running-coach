package com.runningcoach.app.ui.screens

import android.graphics.Paint
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import com.runningcoach.app.data.model.HeatmapRoute
import com.runningcoach.app.data.repository.CoachRepository
import com.runningcoach.app.ui.theme.BrandGreen
import org.osmdroid.config.Configuration
import org.osmdroid.tileprovider.tilesource.TileSourceFactory
import org.osmdroid.util.BoundingBox
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.CustomZoomButtonsController
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Polyline

@Composable
fun HeatmapScreen(
    repository: CoachRepository,
    onBack: () -> Unit,
) {
    var routes by remember { mutableStateOf<List<HeatmapRoute>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(Unit) {
        runCatching { repository.getHeatmap() }
            .onSuccess { resp ->
                routes = resp.routes
                loading = false
            }
            .onFailure { err ->
                error = err.localizedMessage
                loading = false
            }
    }

    Box(Modifier.fillMaxSize()) {
        if (loading) {
            CircularProgressIndicator(Modifier.align(Alignment.Center))
        } else if (routes.isEmpty()) {
            Column(
                Modifier
                    .align(Alignment.Center)
                    .padding(32.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Text("Nessuna corsa con GPS", style = MaterialTheme.typography.titleMedium)
                Spacer(Modifier.height(8.dp))
                Text(
                    "Sincronizza le corse con il GPS attivato per vedere la heatmap.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        } else {
            AndroidView(
                modifier = Modifier.fillMaxSize(),
                factory = { ctx ->
                    Configuration.getInstance().userAgentValue = ctx.packageName
                    val map = MapView(ctx)
                    map.setTileSource(TileSourceFactory.MAPNIK)
                    map.setMultiTouchControls(true)
                    map.zoomController.setVisibility(CustomZoomButtonsController.Visibility.SHOW_AND_FADEOUT)
                    map.setUseDataConnection(true)
                    map
                },
                update = { map ->
                    map.overlays.clear()
                    val allGeoPoints = mutableListOf<GeoPoint>()
                    val baseColor = BrandGreen.toArgb()
                    // Semitransparent overlapping lines → heatmap effect
                    val alpha = (0x55).coerceIn(0x20, 0xFF)
                    val lineColor = (alpha shl 24) or (baseColor and 0x00FFFFFF)

                    routes.forEach { route ->
                        val pts = route.points.mapNotNull { pt ->
                            if (pt.size >= 2) GeoPoint(pt[0], pt[1]) else null
                        }
                        if (pts.size >= 2) {
                            allGeoPoints.addAll(pts)
                            val line = Polyline(map).apply {
                                setPoints(pts)
                                outlinePaint.color = lineColor
                                outlinePaint.strokeWidth = 8f
                                outlinePaint.isAntiAlias = true
                                outlinePaint.strokeCap = Paint.Cap.ROUND
                                outlinePaint.strokeJoin = Paint.Join.ROUND
                                infoWindow = null
                            }
                            map.overlays.add(line)
                        }
                    }

                    if (allGeoPoints.isNotEmpty()) {
                        val bbox = BoundingBox.fromGeoPoints(allGeoPoints).increaseByScale(1.15f)
                        map.addOnFirstLayoutListener { _, _, _, _, _ ->
                            runCatching { map.zoomToBoundingBox(bbox, false, 80) }
                        }
                        map.post { runCatching { map.zoomToBoundingBox(bbox, false, 80) } }
                    }
                    map.invalidate()
                },
                onRelease = { it.onDetach() },
            )

            // Stats overlay in top-right
            Surface(
                modifier = Modifier
                    .align(Alignment.TopEnd)
                    .statusBarsPadding()
                    .padding(top = 56.dp, end = 12.dp),
                color = MaterialTheme.colorScheme.surface.copy(alpha = 0.88f),
                shape = MaterialTheme.shapes.small,
                shadowElevation = 4.dp,
            ) {
                Text(
                    "${routes.size} corse con GPS",
                    style = MaterialTheme.typography.labelMedium,
                    modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
                )
            }
        }

        // Back button
        IconButton(
            onClick = onBack,
            modifier = Modifier
                .align(Alignment.TopStart)
                .statusBarsPadding()
                .padding(12.dp)
                .size(40.dp),
        ) {
            Surface(
                Modifier.fillMaxSize(),
                shape = MaterialTheme.shapes.small,
                color = MaterialTheme.colorScheme.surface.copy(alpha = 0.88f),
                shadowElevation = 4.dp,
            ) {
                Icon(
                    Icons.AutoMirrored.Filled.ArrowBack,
                    contentDescription = "Indietro",
                    modifier = Modifier.padding(8.dp),
                    tint = MaterialTheme.colorScheme.onSurface,
                )
            }
        }

        error?.let {
            Surface(
                Modifier
                    .align(Alignment.BottomCenter)
                    .padding(16.dp),
                color = MaterialTheme.colorScheme.errorContainer,
                shape = MaterialTheme.shapes.small,
            ) {
                Text(
                    "Errore: $it",
                    modifier = Modifier.padding(12.dp),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onErrorContainer,
                )
            }
        }
    }
}
