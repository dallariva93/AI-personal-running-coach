package com.runningcoach.app.ui.components

import android.graphics.Paint
import android.graphics.drawable.Drawable
import android.graphics.drawable.ShapeDrawable
import android.graphics.drawable.shapes.OvalShape
import android.view.MotionEvent
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import org.osmdroid.config.Configuration
import org.osmdroid.tileprovider.tilesource.TileSourceFactory
import org.osmdroid.util.BoundingBox
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.CustomZoomButtonsController
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Marker
import org.osmdroid.views.overlay.Polyline

/**
 * Real OpenStreetMap route map (free, no API key) — the same class of map
 * Garmin Connect and Strava render. Draws the GPS track on live OSM tiles with
 * coloured start/finish dots and auto-fits the camera to the route.
 *
 * [points] are ``(lat, lon)`` pairs. osmdroid is a classic Android View, so we
 * bridge it into Compose with [AndroidView]; the tile cache is app-private
 * (minSdk 26) and the user-agent is set to our package, as OSM's tile policy
 * requires.
 */
@Composable
fun RouteMap(
    points: List<Pair<Double, Double>>,
    lineColorArgb: Int,
    startColorArgb: Int,
    endColorArgb: Int,
    modifier: Modifier = Modifier,
    height: Dp = 240.dp,
) {
    AndroidView(
        modifier = modifier.fillMaxWidth().height(height),
        factory = { ctx ->
            Configuration.getInstance().userAgentValue = ctx.packageName
            // Non-interactive map: onTouchEvent returns false so vertical drags
            // fall through to the page scroll instead of panning the map. The
            // route is rendered as a clean static preview on real OSM tiles.
            val map: MapView = object : MapView(ctx) {
                override fun onTouchEvent(event: MotionEvent?): Boolean = false
            }
            map.setTileSource(TileSourceFactory.MAPNIK)
            map.setMultiTouchControls(false)
            map.zoomController.setVisibility(CustomZoomButtonsController.Visibility.NEVER)
            map.setUseDataConnection(true)
            map
        },
        update = { map ->
            map.overlays.clear()
            if (points.size >= 2) {
                val geo = points.map { GeoPoint(it.first, it.second) }

                val line = Polyline(map).apply {
                    setPoints(geo)
                    outlinePaint.color = lineColorArgb
                    outlinePaint.strokeWidth = 12f
                    outlinePaint.isAntiAlias = true
                    outlinePaint.strokeCap = Paint.Cap.ROUND
                    outlinePaint.strokeJoin = Paint.Join.ROUND
                    infoWindow = null
                }
                map.overlays.add(line)

                map.overlays.add(dotMarker(map, geo.first(), startColorArgb))
                map.overlays.add(dotMarker(map, geo.last(), endColorArgb))

                val bbox = BoundingBox.fromGeoPoints(geo).increaseByScale(1.25f)
                map.addOnFirstLayoutListener { _, _, _, _, _ ->
                    runCatching { map.zoomToBoundingBox(bbox, false, 56) }
                }
                map.post { runCatching { map.zoomToBoundingBox(bbox, false, 56) } }
            }
            map.invalidate()
        },
        onRelease = { it.onDetach() },
    )
}

/** A clean coloured circle marker (start = green, finish = red), no asset files. */
private fun dotMarker(map: MapView, at: GeoPoint, colorArgb: Int): Marker =
    Marker(map).apply {
        position = at
        icon = circleDrawable(colorArgb)
        setAnchor(Marker.ANCHOR_CENTER, Marker.ANCHOR_CENTER)
        infoWindow = null
        setOnMarkerClickListener { _, _ -> true } // no info bubble
    }

private fun circleDrawable(colorArgb: Int, sizePx: Int = 34): Drawable =
    ShapeDrawable(OvalShape()).apply {
        paint.color = colorArgb
        paint.isAntiAlias = true
        intrinsicWidth = sizePx
        intrinsicHeight = sizePx
    }
