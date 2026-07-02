package com.runningcoach.app.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import com.runningcoach.app.ui.theme.textSafeOn

/** A muted, all-caps eyebrow label used above sections. */
@Composable
fun SectionTitle(text: String, modifier: Modifier = Modifier) {
    Text(
        text = text.uppercase(),
        style = MaterialTheme.typography.labelMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        modifier = modifier.padding(vertical = 8.dp),
    )
}

/** A big section heading (screen titles, card headers). */
@Composable
fun ScreenTitle(text: String, subtitle: String? = null, modifier: Modifier = Modifier) {
    Column(modifier) {
        Text(text, style = MaterialTheme.typography.headlineMedium)
        if (subtitle != null) {
            Text(
                subtitle,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

/** A single labelled stat (value on top, caption below). Long-press shows a tooltip if provided. */
@Composable
fun StatItem(
    label: String,
    value: String,
    modifier: Modifier = Modifier,
    valueColor: Color = MaterialTheme.colorScheme.onSurface,
    tooltip: MetricInfo? = null,
) {
    var showTooltip by remember { mutableStateOf(false) }
    Column(
        modifier.then(
            if (tooltip != null) Modifier.pointerInput(Unit) {
                detectTapGestures(onLongPress = { showTooltip = true })
            } else Modifier
        ),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(
            value,
            style = MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.Bold,
            color = valueColor,
        )
        Text(
            label,
            style = MaterialTheme.typography.labelSmall.copy(
                textDecoration = if (tooltip != null) TextDecoration.Underline else null,
            ),
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
        )
    }
    if (showTooltip && tooltip != null) {
        MetricInfoDialog(tooltip) { showTooltip = false }
    }
}

/**
 * Small rounded status chip with a leading dot. The dot and background tint
 * keep the vivid brand [color]; the text uses [Color.textSafeOn] against the
 * surrounding surface so every pill clears WCAG AA contrast (Roadmap Q7),
 * whichever semantic color a call site passes in.
 */
@Composable
fun Pill(
    text: String,
    color: Color,
    modifier: Modifier = Modifier,
) {
    val textColor = color.textSafeOn(MaterialTheme.colorScheme.surface)
    Row(
        modifier
            .clip(RoundedCornerShape(50))
            .background(color.copy(alpha = 0.16f))
            .padding(horizontal = 10.dp, vertical = 5.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(7.dp).clip(RoundedCornerShape(50)).background(color))
        Spacer(Modifier.size(6.dp))
        Text(
            text,
            style = MaterialTheme.typography.labelMedium,
            color = textColor,
            fontWeight = FontWeight.SemiBold,
        )
    }
}

/**
 * Circular gauge used for the headline form signal. [progress] is 0..1, [label]
 * is the big centered value, [caption] the small text underneath it.
 */
@Composable
fun MetricRing(
    progress: Float,
    color: Color,
    label: String,
    caption: String,
    modifier: Modifier = Modifier,
    ringSize: androidx.compose.ui.unit.Dp = 116.dp,
    tooltip: MetricInfo? = null,
) {
    var showTooltip by remember { mutableStateOf(false) }
    val track = MaterialTheme.colorScheme.surfaceVariant
    Box(
        modifier
            .size(ringSize)
            .then(
                if (tooltip != null) Modifier.pointerInput(Unit) {
                    detectTapGestures(onLongPress = { showTooltip = true })
                } else Modifier
            ),
        contentAlignment = Alignment.Center,
    ) {
        Canvas(Modifier.size(ringSize)) {
            val stroke = 11.dp.toPx()
            val inset = stroke / 2f
            val arcSize = Size(size.width - stroke, size.height - stroke)
            drawArc(
                color = track,
                startAngle = 0f,
                sweepAngle = 360f,
                useCenter = false,
                topLeft = androidx.compose.ui.geometry.Offset(inset, inset),
                size = arcSize,
                style = Stroke(width = stroke, cap = StrokeCap.Round),
            )
            drawArc(
                color = color,
                startAngle = -90f,
                sweepAngle = 360f * progress.coerceIn(0f, 1f),
                useCenter = false,
                topLeft = androidx.compose.ui.geometry.Offset(inset, inset),
                size = arcSize,
                style = Stroke(width = stroke, cap = StrokeCap.Round),
            )
        }
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text(
                label,
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.Black,
                color = color,
            )
            Text(
                caption,
                style = MaterialTheme.typography.labelSmall.copy(
                    textDecoration = if (tooltip != null) TextDecoration.Underline else null,
                ),
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
    if (showTooltip && tooltip != null) {
        MetricInfoDialog(tooltip) { showTooltip = false }
    }
}

/** Trend arrow + label, colored by direction. */
@Composable
fun TrendBadge(trend: String, modifier: Modifier = Modifier) {
    val (text, color) = when (trend.lowercase()) {
        "rising", "improving" -> "↑ in crescita" to MaterialTheme.colorScheme.primary
        "falling", "declining" -> "↓ in calo" to MaterialTheme.colorScheme.error
        else -> "→ stabile" to MaterialTheme.colorScheme.onSurfaceVariant
    }
    Text(text, style = MaterialTheme.typography.labelMedium, color = color, modifier = modifier)
}

/** Standard elevated surface card used everywhere for visual consistency. */
@Composable
fun SurfaceCard(
    modifier: Modifier = Modifier,
    content: @Composable () -> Unit,
) {
    Card(
        modifier = modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        elevation = CardDefaults.cardElevation(defaultElevation = 0.dp),
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant),
    ) {
        Column(Modifier.padding(16.dp)) { content() }
    }
}

/** A vivid gradient hero card (used for the prediction / headline blocks). */
@Composable
fun GradientCard(
    colors: List<Color>,
    modifier: Modifier = Modifier,
    content: @Composable () -> Unit,
) {
    Box(
        modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(24.dp))
            .background(Brush.linearGradient(colors))
            .padding(18.dp),
    ) {
        Column(Modifier.fillMaxWidth()) { content() }
    }
}

/** A thin divider used inside cards. */
@Composable
fun ThinDivider(modifier: Modifier = Modifier) {
    Box(
        modifier
            .fillMaxWidth()
            .height(1.dp)
            .background(MaterialTheme.colorScheme.outlineVariant),
    )
}
