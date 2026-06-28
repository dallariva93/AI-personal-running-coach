package com.runningcoach.app.ui.screens

import android.graphics.Paint
import android.graphics.drawable.ShapeDrawable
import android.graphics.drawable.shapes.OvalShape
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import com.runningcoach.app.ui.theme.BrandGreen
import com.runningcoach.app.ui.theme.Coral
import org.osmdroid.config.Configuration
import org.osmdroid.tileprovider.tilesource.TileSourceFactory
import org.osmdroid.util.BoundingBox
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.CustomZoomButtonsController
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Marker
import org.osmdroid.views.overlay.Polyline

/**
 * Full-screen interactive route map. Supports pinch-to-zoom and pan.
 * Opened when the user taps the inline preview in ActivityDetailScreen.
 */
@Composable
fun MapFullscreenScreen(
    points: List<Pair<Double, Double>>,
    onBack: () -> Unit,
) {
    Box(Modifier.fillMaxSize()) {
        AndroidView(
            modifier = Modifier.fillMaxSize(),
            factory = { ctx ->
                Configuration.getInstance().userAgentValue = ctx.packageName
                val map = MapView(ctx)
                map.setTileSource(TileSourceFactory.MAPNIK)
                map.setMultiTouchControls(true)
                map.zoomController.setVisibility(
                    CustomZoomButtonsController.Visibility.SHOW_AND_FADEOUT,
                )
                map.setUseDataConnection(true)
                map
            },
            update = { map ->
                map.overlays.clear()
                if (points.size >= 2) {
                    val geo = points.map { GeoPoint(it.first, it.second) }
                    val line = Polyline(map).apply {
                        setPoints(geo)
                        outlinePaint.color = BrandGreen.toArgb()
                        outlinePaint.strokeWidth = 14f
                        outlinePaint.isAntiAlias = true
                        outlinePaint.strokeCap = Paint.Cap.ROUND
                        outlinePaint.strokeJoin = Paint.Join.ROUND
                        infoWindow = null
                    }
                    map.overlays.add(line)
                    map.overlays.add(fullscreenDot(map, geo.first(), BrandGreen.toArgb()))
                    map.overlays.add(fullscreenDot(map, geo.last(), Coral.toArgb()))
                    val bbox = BoundingBox.fromGeoPoints(geo).increaseByScale(1.25f)
                    map.addOnFirstLayoutListener { _, _, _, _, _ ->
                        runCatching { map.zoomToBoundingBox(bbox, false, 80) }
                    }
                    map.post { runCatching { map.zoomToBoundingBox(bbox, false, 80) } }
                }
                map.invalidate()
            },
            onRelease = { it.onDetach() },
        )

        // Floating back button with semi-transparent pill background for legibility
        // against any tile content.
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
    }
}

private fun fullscreenDot(map: MapView, at: GeoPoint, colorArgb: Int): Marker =
    Marker(map).apply {
        position = at
        icon = ShapeDrawable(OvalShape()).apply {
            paint.color = colorArgb
            paint.isAntiAlias = true
            intrinsicWidth = 42
            intrinsicHeight = 42
        }
        setAnchor(Marker.ANCHOR_CENTER, Marker.ANCHOR_CENTER)
        infoWindow = null
        setOnMarkerClickListener { _, _ -> true }
    }
