package com.runningcoach.app.ui.components

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.LinearGradient
import android.graphics.Paint
import android.graphics.Picture
import android.graphics.Shader
import com.runningcoach.app.data.model.RaceRecap
import com.runningcoach.app.data.model.WeeklyRecap
import kotlin.math.roundToLong

/**
 * Renders a shareable recap card (Roadmap A6) off-screen into a 1080×1350
 * bitmap, ready for a share intent. Deliberately built on plain
 * [android.graphics] (`Picture` → `Canvas` → `Bitmap`), not a Compose capture
 * API: it needs no Compose version beyond what the app already uses and no
 * Activity/window context, so it is trivial to call from anywhere (a
 * background worker, a notification action, a screen) and to keep fast
 * (simple 2D drawing, well under the <500ms target).
 *
 * The in-app *preview* the athlete sees before sharing is the separate
 * Compose [WeeklyRecapCard]/[RaceRecapCard] — same facts, same brand colors,
 * kept visually consistent by hand (see the color constants below, mirrored
 * from `ui/theme/Color.kt`).
 */
object RecapCardRenderer {

    private const val WIDTH = 1080
    private const val HEIGHT = 1350
    private const val PADDING = 80f

    // Mirrors ui/theme/Color.kt (BrandGreen/BrandGreenDeep/Coral/CoralBright).
    private const val BRAND_GREEN = 0xFF00C16E.toInt()
    private const val BRAND_GREEN_DEEP = 0xFF037A45.toInt()
    private const val CORAL = 0xFFFF5A1F.toInt()
    private const val CORAL_BRIGHT = 0xFFFF7E45.toInt()

    fun renderWeekly(recap: WeeklyRecap): Bitmap = render(
        gradient = intArrayOf(BRAND_GREEN_DEEP, BRAND_GREEN),
        eyebrow = "RIEPILOGO SETTIMANALE",
        headline = "${formatKm(recap.distanceKm)} km",
        subline = "${recap.runsCount} uscite" +
            (recap.adherencePct?.let { " · aderenza ${it.roundToLong()}%" } ?: ""),
        narrative = recap.narrative,
        footer = listOfNotNull(
            recap.avgExecutionScore?.let { "Execution medio ${it.roundToLong()}/100" },
            recap.bestMoment,
        ).joinToString("   ·   "),
    )

    fun renderRace(recap: RaceRecap): Bitmap = render(
        gradient = intArrayOf(CORAL, CORAL_BRIGHT),
        eyebrow = "RECAP GARA",
        headline = recap.actualTime,
        subline = "${formatKm(recap.distanceKm)} km" +
            (recap.deltaLabel?.let { " · $it" } ?: ""),
        narrative = recap.narrative,
        footer = recap.predictedTime?.let { "Previsto: $it" } ?: "",
    )

    private fun render(
        gradient: IntArray,
        eyebrow: String,
        headline: String,
        subline: String,
        narrative: String,
        footer: String,
    ): Bitmap {
        val picture = Picture()
        val canvas = picture.beginRecording(WIDTH, HEIGHT)
        val paint = Paint(Paint.ANTI_ALIAS_FLAG)

        // Brand gradient background.
        paint.shader = LinearGradient(
            0f, 0f, WIDTH.toFloat(), HEIGHT.toFloat(), gradient, null, Shader.TileMode.CLAMP,
        )
        canvas.drawRect(0f, 0f, WIDTH.toFloat(), HEIGHT.toFloat(), paint)
        paint.shader = null

        var y = 190f
        paint.color = Color.argb(230, 255, 255, 255)
        paint.textSize = 34f
        paint.isFakeBoldText = true
        paint.letterSpacing = 0.05f
        canvas.drawText(eyebrow, PADDING, y, paint)
        paint.letterSpacing = 0f

        y += 110f
        paint.color = Color.WHITE
        paint.textSize = 96f
        canvas.drawText(headline, PADDING, y, paint)

        y += 66f
        paint.textSize = 42f
        paint.isFakeBoldText = false
        canvas.drawText(subline, PADDING, y, paint)

        if (narrative.isNotBlank()) {
            y += 90f
            paint.textSize = 36f
            paint.color = Color.argb(245, 255, 255, 255)
            for (line in wrapText(narrative, paint, WIDTH - PADDING * 2)) {
                canvas.drawText(line, PADDING, y, paint)
                y += 48f
            }
        }

        if (footer.isNotBlank()) {
            paint.textSize = 30f
            paint.color = Color.argb(215, 255, 255, 255)
            canvas.drawText(footer, PADDING, HEIGHT - 140f, paint)
        }

        paint.textSize = 28f
        paint.color = Color.argb(180, 255, 255, 255)
        canvas.drawText("AI Running Coach", PADDING, HEIGHT - 70f, paint)

        picture.endRecording()

        val bitmap = Bitmap.createBitmap(WIDTH, HEIGHT, Bitmap.Config.ARGB_8888)
        Canvas(bitmap).drawPicture(picture)
        return bitmap
    }

    /** Greedy word-wrap so the narrative never overflows the card width. */
    private fun wrapText(text: String, paint: Paint, maxWidth: Float): List<String> {
        val words = text.split(" ")
        val lines = mutableListOf<String>()
        var current = StringBuilder()
        for (word in words) {
            val candidate = if (current.isEmpty()) word else "$current $word"
            if (paint.measureText(candidate) > maxWidth && current.isNotEmpty()) {
                lines.add(current.toString())
                current = StringBuilder(word)
            } else {
                current = StringBuilder(candidate)
            }
        }
        if (current.isNotEmpty()) lines.add(current.toString())
        return lines
    }

    private fun formatKm(value: Double): String =
        if (value == value.toLong().toDouble()) value.toLong().toString()
        else "%.1f".format(value)
}
