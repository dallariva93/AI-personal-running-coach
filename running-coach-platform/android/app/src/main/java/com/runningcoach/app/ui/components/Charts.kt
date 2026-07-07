package com.runningcoach.app.ui.components

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
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

/** One headline figure above a [MetricAreaChart] (e.g. "5:23 /km · Media"). */
data class ChartStat(val value: String, val unit: String, val caption: String)

/**
 * A production-ready, Garmin-style area chart for a per-sample metric trace
 * (pace, elevation, heart rate…). Renders, in one card-friendly block:
 *
 * * a title and a row of headline stats (value + unit + caption);
 * * a gradient-filled area under a solid line, in the metric's colour;
 * * a labelled Y axis **with units** and evenly-spaced gridlines;
 * * an X axis with a few markers plus a caption (e.g. "km");
 * * an optional dashed average reference line (the way Garmin marks the mean).
 *
 * ``inverted`` flips the Y axis so that *smaller* values sit at the top — the
 * convention for pace, where a faster (smaller) pace is "higher". All axis text
 * is measured and placed with [rememberTextMeasurer] so labels align exactly to
 * their gridlines at any size. Pure Compose Canvas, no external dependencies.
 */
@Composable
fun MetricAreaChart(
    title: String,
    values: List<Float>,
    color: Color,
    stats: List<ChartStat>,
    yFormatter: (Float) -> String,
    xLabels: List<String>,
    modifier: Modifier = Modifier,
    xCaption: String? = null,
    inverted: Boolean = false,
    average: Float? = null,
    height: Dp = 168.dp,
    ticks: Int = 5,
) {
    val axisColor = MaterialTheme.colorScheme.onSurfaceVariant
    val gridColor = axisColor.copy(alpha = 0.14f)
    val avgColor = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.55f)
    val measurer = rememberTextMeasurer()
    val axisStyle = TextStyle(color = axisColor, fontSize = 11.sp)

    Column(modifier.fillMaxWidth()) {
        Text(
            title,
            style = MaterialTheme.typography.titleSmall,
            color = MaterialTheme.colorScheme.onSurface,
        )
        Spacer(Modifier.height(10.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(28.dp)) {
            stats.forEach { StatBlock(it) }
        }
        Spacer(Modifier.height(14.dp))

        if (values.size < 2) {
            Text(
                "Dati insufficienti per il grafico.",
                style = MaterialTheme.typography.bodySmall,
                color = axisColor,
            )
            return@Column
        }

        // Pad the value range a touch so the trace never hugs the top/bottom.
        val rawLo = values.min()
        val rawHi = values.max()
        val pad = ((rawHi - rawLo) * 0.12f).let { if (it <= 0f) 1f else it }
        val lo = rawLo - pad
        val hi = rawHi + pad
        val span = max(hi - lo, 0.0001f)

        Canvas(Modifier.fillMaxWidth().height(height)) {
            val yGutter = 44.dp.toPx()
            val xAxisH = (if (xCaption != null) 34 else 18).dp.toPx()
            val plotLeft = yGutter
            val plotTop = 8.dp.toPx()
            val plotRight = size.width
            val plotBottom = size.height - xAxisH
            val plotW = (plotRight - plotLeft).coerceAtLeast(1f)
            val plotH = (plotBottom - plotTop).coerceAtLeast(1f)

            // Vertical fraction (0=top,1=bottom) → data value, honouring inversion.
            fun valueAtFraction(t: Float): Float =
                if (inverted) lo + t * (hi - lo) else hi - t * (hi - lo)

            fun yOf(v: Float): Float {
                val frac = (v - lo) / span // 0 at lo … 1 at hi
                return if (inverted) plotTop + frac * plotH else plotBottom - frac * plotH
            }

            // Gridlines + Y labels (with units baked into the formatter output).
            for (i in 0 until ticks) {
                val t = i / (ticks - 1f)
                val y = plotTop + t * plotH
                drawLine(gridColor, Offset(plotLeft, y), Offset(plotRight, y), strokeWidth = 1f)
                val label = measurer.measure(yFormatter(valueAtFraction(t)), axisStyle)
                drawText(
                    label,
                    topLeft = Offset(
                        plotLeft - 8.dp.toPx() - label.size.width,
                        (y - label.size.height / 2f).coerceIn(0f, size.height - label.size.height),
                    ),
                )
            }

            // Build the trace.
            val stepX = plotW / (values.size - 1)
            fun pointAt(i: Int) = Offset(plotLeft + i * stepX, yOf(values[i]))
            val line = Path().apply {
                moveTo(pointAt(0).x, pointAt(0).y)
                for (i in 1 until values.size) lineTo(pointAt(i).x, pointAt(i).y)
            }
            // Gradient fill down to the axis.
            val area = Path().apply {
                addPath(line)
                lineTo(plotRight, plotBottom)
                lineTo(plotLeft, plotBottom)
                close()
            }
            drawPath(
                area,
                brush = Brush.verticalGradient(
                    colors = listOf(color.copy(alpha = 0.32f), color.copy(alpha = 0.04f)),
                    startY = plotTop,
                    endY = plotBottom,
                ),
            )
            drawPath(line, color = color, style = Stroke(width = 2.5.dp.toPx()))

            // Average reference line (dashed), the way Garmin marks the mean.
            average?.let { avg ->
                val y = yOf(avg).coerceIn(plotTop, plotBottom)
                drawLine(
                    avgColor,
                    Offset(plotLeft, y),
                    Offset(plotRight, y),
                    strokeWidth = 1.5.dp.toPx(),
                    pathEffect = PathEffect.dashPathEffect(floatArrayOf(10f, 8f)),
                )
            }

            // X labels, evenly spaced: first left-aligned, last right-aligned.
            xLabels.forEachIndexed { i, text ->
                val t = if (xLabels.size == 1) 0f else i / (xLabels.size - 1f)
                val cx = plotLeft + t * plotW
                val m = measurer.measure(text, axisStyle)
                val x = (cx - m.size.width / 2f).coerceIn(plotLeft, plotRight - m.size.width)
                drawText(m, topLeft = Offset(x, plotBottom + 4.dp.toPx()))
            }
            xCaption?.let {
                val m = measurer.measure(it, axisStyle)
                drawText(
                    m,
                    topLeft = Offset(
                        plotLeft + (plotW - m.size.width) / 2f,
                        size.height - m.size.height,
                    ),
                )
            }
        }
    }
}

@Composable
private fun StatBlock(stat: ChartStat) {
    Column {
        Row(verticalAlignment = Alignment.Bottom) {
            Text(
                stat.value,
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.SemiBold,
                color = MaterialTheme.colorScheme.onSurface,
            )
            if (stat.unit.isNotEmpty()) {
                Spacer(Modifier.width(3.dp))
                Text(
                    stat.unit,
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(bottom = 3.dp),
                )
            }
        }
        Text(
            stat.caption,
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
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
