package com.runningcoach.app.ui.components

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.unit.dp
import kotlin.math.max

/**
 * One data series for [LineChart]. Generic on purpose: this is the reusable
 * foundation for any time-series view we add later (heart-rate, power, pace,
 * elevation traces) — just feed it the sampled values.
 */
data class ChartSeries(
    val values: List<Float>,
    val color: Color,
    val fill: Boolean = true,
    val strokeWidthDp: Float = 2.5f,
)

/**
 * Generic multi-series line chart with optional gradient fill. No external
 * dependencies — pure Compose Canvas, so it stays light and fully themeable.
 *
 * Future HR/power traces: build a [ChartSeries] per metric and drop it in.
 */
@Composable
fun LineChart(
    series: List<ChartSeries>,
    modifier: Modifier = Modifier,
    height: androidx.compose.ui.unit.Dp = 160.dp,
    minValue: Float? = null,
    maxValue: Float? = null,
) {
    val allValues = series.flatMap { it.values }
    if (allValues.isEmpty()) {
        Box(modifier.fillMaxWidth().height(height))
        return
    }
    val lo = minValue ?: allValues.min()
    val hi = maxValue ?: allValues.max()
    val span = max(hi - lo, 0.0001f)

    Canvas(modifier.fillMaxWidth().height(height)) {
        val w = size.width
        val h = size.height
        series.forEach { s ->
            if (s.values.size < 2) return@forEach
            val stepX = w / (s.values.size - 1)
            fun pointAt(i: Int): Offset {
                val v = s.values[i]
                val y = h - ((v - lo) / span) * h
                return Offset(i * stepX, y.coerceIn(0f, h))
            }

            val line = Path().apply {
                moveTo(0f, pointAt(0).y)
                for (i in 1 until s.values.size) {
                    val p = pointAt(i)
                    lineTo(p.x, p.y)
                }
            }

            if (s.fill) {
                val area = Path().apply {
                    addPath(line)
                    lineTo(w, h)
                    lineTo(0f, h)
                    close()
                }
                drawPath(
                    path = area,
                    brush = Brush.verticalGradient(
                        colors = listOf(s.color.copy(alpha = 0.35f), s.color.copy(alpha = 0f)),
                    ),
                )
            }
            drawPath(
                path = line,
                color = s.color,
                style = Stroke(width = s.strokeWidthDp.dp.toPx()),
            )
        }
    }
}

/**
 * Vertical bar chart (e.g. weekly volume). [highlightLast] tints the most recent
 * bar with the accent so "this week" pops.
 */
@Composable
fun BarChart(
    values: List<Float>,
    labels: List<String>,
    modifier: Modifier = Modifier,
    barColor: Color = MaterialTheme.colorScheme.primary,
    accentColor: Color = MaterialTheme.colorScheme.secondary,
    height: androidx.compose.ui.unit.Dp = 150.dp,
    highlightLast: Boolean = true,
) {
    if (values.isEmpty()) {
        Text("Nessun dato.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        return
    }
    val maxV = max(values.max(), 0.0001f)
    val trackColor = MaterialTheme.colorScheme.surfaceVariant
    Canvas(modifier.fillMaxWidth().height(height)) {
        drawBars(values, maxV, barColor, accentColor, trackColor, highlightLast)
    }
    Spacer(Modifier.height(6.dp))
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        labels.forEach {
            Text(
                it,
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

private fun DrawScope.drawBars(
    values: List<Float>,
    maxV: Float,
    barColor: Color,
    accentColor: Color,
    trackColor: Color,
    highlightLast: Boolean,
) {
    val gap = 10.dp.toPx()
    val barWidth = (size.width - gap * (values.size - 1)) / values.size
    val radius = androidx.compose.ui.geometry.CornerRadius(barWidth.coerceAtMost(16f) / 2f, barWidth.coerceAtMost(16f) / 2f)
    values.forEachIndexed { i, v ->
        val x = i * (barWidth + gap)
        // Track (faint full-height bar) for a polished look.
        drawRoundRect(
            color = trackColor,
            topLeft = Offset(x, 0f),
            size = Size(barWidth, size.height),
            cornerRadius = radius,
        )
        val barH = (v / maxV * size.height).coerceAtLeast(2f)
        val isLast = highlightLast && i == values.size - 1
        drawRoundRect(
            color = if (isLast) accentColor else barColor,
            topLeft = Offset(x, size.height - barH),
            size = Size(barWidth, barH),
            cornerRadius = radius,
        )
    }
}

/**
 * Horizontal stacked bar for an intensity / zone distribution (easy / moderate
 * / hard today; reusable for HR-zone time later).
 */
@Composable
fun StackedBar(
    segments: List<Pair<Float, Color>>,
    modifier: Modifier = Modifier,
    height: androidx.compose.ui.unit.Dp = 12.dp,
) {
    val total = segments.sumOf { it.first.toDouble() }.toFloat().coerceAtLeast(0.0001f)
    Row(
        modifier
            .fillMaxWidth()
            .height(height)
            .clip(RoundedCornerShape(50)),
    ) {
        segments.forEach { (value, color) ->
            if (value > 0f) {
                Box(
                    Modifier
                        .fillMaxHeight()
                        .weight((value / total).coerceAtLeast(0.001f))
                        .background(color),
                )
            }
        }
    }
}
