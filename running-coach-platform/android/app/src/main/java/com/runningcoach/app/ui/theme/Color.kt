package com.runningcoach.app.ui.theme

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb
import androidx.core.graphics.ColorUtils

// ─────────────────────────────────────────────────────────────────────────────
// Brand palette — energetic, premium, distinct from Strava (orange) and Garmin
// (blue): a vivid "volt" green paired with a warm coral accent. Designed to read
// great on a dark, near-black canvas (the look most fitness apps use to feel
// premium) while staying legible in light mode.
// ─────────────────────────────────────────────────────────────────────────────

// Primary brand (green) and its gradient partner.
val BrandGreen = Color(0xFF00C16E)
val BrandGreenBright = Color(0xFF2BE38C)
val BrandGreenDeep = Color(0xFF037A45)

// Warm accent for CTAs / highlights.
val Coral = Color(0xFFFF5A1F)
val CoralBright = Color(0xFFFF7E45)

// Dark theme surfaces (near-black, slightly cool).
val DarkBackground = Color(0xFF0D1014)
val DarkSurface = Color(0xFF161B22)
val DarkSurfaceElevated = Color(0xFF1D232C)
val DarkSurfaceVariant = Color(0xFF242C37)
val DarkOutline = Color(0xFF323B47)
val DarkOnSurface = Color(0xFFE7ECF2)
val DarkOnSurfaceMuted = Color(0xFF9AA6B4)

// Light theme surfaces.
val LightBackground = Color(0xFFF5F7FA)
val LightSurface = Color(0xFFFFFFFF)
val LightSurfaceVariant = Color(0xFFEDF1F5)
val LightOutline = Color(0xFFD7DEE6)
val LightOnSurface = Color(0xFF11161C)
val LightOnSurfaceMuted = Color(0xFF5C6773)

// ─────────────────────────────────────────────────────────────────────────────
// Semantic form-state colors (used by cards, badges and the form ring).
// ─────────────────────────────────────────────────────────────────────────────
val FormFresh = Color(0xFF22C55E)
val FormBalanced = Color(0xFF38BDF8)
val FormFatigued = Color(0xFFF43F5E)
val FormDetraining = Color(0xFFFBBF24)
val FormUnknown = Color(0xFF64748B)

fun formColor(state: String): Color = when (state.lowercase()) {
    "fresh" -> FormFresh
    "balanced" -> FormBalanced
    "fatigued" -> FormFatigued
    "detraining" -> FormDetraining
    else -> FormUnknown
}

// ─────────────────────────────────────────────────────────────────────────────
// Intensity / HR-zone palette. Shared by the 80/20 bar today and ready for the
// future per-second HR/power traces (zone-colored line charts).
// ─────────────────────────────────────────────────────────────────────────────
val Zone1 = Color(0xFF64748B) // recovery / grey-blue
val Zone2 = Color(0xFF38BDF8) // easy aerobic / blue
val Zone3 = Color(0xFF22C55E) // moderate / green
val Zone4 = Color(0xFFFB923C) // threshold / orange
val Zone5 = Color(0xFFF43F5E) // VO2 / red

val IntensityEasy = Zone2
val IntensityModerate = Zone4
val IntensityHard = Zone5

fun zoneColor(zone: Int): Color = when (zone) {
    1 -> Zone1
    2 -> Zone2
    3 -> Zone3
    4 -> Zone4
    5 -> Zone5
    else -> FormUnknown
}

// Risk / readiness traffic-light helpers.
val RiskLow = Color(0xFF22C55E)
val RiskModerate = Color(0xFFFBBF24)
val RiskHigh = Color(0xFFF43F5E)

fun riskColor(level: String?): Color = when (level?.lowercase()) {
    "low", "green" -> RiskLow
    "moderate", "amber" -> RiskModerate
    "high", "red" -> RiskHigh
    else -> FormUnknown
}

// ─────────────────────────────────────────────────────────────────────────────
// Activity-type intensity colors for list row badges.
// Ordered easy → hard so the user reads effort at a glance.
// ─────────────────────────────────────────────────────────────────────────────
val ActivityEasy = Color(0xFF22C55E)          // green  — easy / recupero
val ActivityModerate = Color(0xFF38BDF8)       // sky    — medio / lungo
val ActivityTempo = Color(0xFFFB923C)          // orange — tempo
val ActivityHard = Color(0xFFF43F5E)           // red    — intervalli / gara
val ActivityTrail = Color(0xFF10B981)          // emerald — trail

fun activityColor(type: String): Color = when (type.lowercase()) {
    "easy", "recupero" -> ActivityEasy
    "medio", "lungo" -> ActivityModerate
    "tempo" -> ActivityTempo
    "intervalli", "gara" -> ActivityHard
    "trail" -> ActivityTrail
    else -> FormUnknown
}

// ─────────────────────────────────────────────────────────────────────────────
// WCAG contrast helper (Roadmap Q7). The semantic palette above is tuned to pop
// on the near-black dark theme; several of those same colors fall well under
// the 4.5:1 AA threshold for normal text once used on a *light* surface — a
// contrast audit script run against every color/surface combination in this
// file found the failure is systemic (light mode), not a couple of edge cases.
// Rather than hand-author a light-mode "*Deep" twin for every color (easy to
// forget for new colors, and to let drift out of sync), text-bearing components
// call [textSafeOn] once, which darkens (or, on a dark surface, lightens) the
// color just enough to clear the ratio — provably correct for any color, not
// just the ones audited today.
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Returns [this], adjusted in lightness if necessary, so it reaches at least
 * [minRatio] contrast (WCAG AA normal text = 4.5:1) against [background]. Used
 * for text/icon color; leave decorative fills (dots, chip backgrounds) using
 * the original vivid color — only legibility of text needs the guarantee.
 */
fun Color.textSafeOn(background: Color, minRatio: Double = 4.5): Color {
    val fgArgb = this.toArgb()
    val bgArgb = background.toArgb()
    if (ColorUtils.calculateContrast(fgArgb, bgArgb) >= minRatio) return this

    val hsl = FloatArray(3)
    ColorUtils.colorToHSL(fgArgb, hsl)
    val bgIsDark = ColorUtils.calculateLuminance(bgArgb) < 0.5
    // Lighten toward 1 on a dark background, darken toward 0 on a light one.
    var lo = if (bgIsDark) hsl[2] else 0f
    var hi = if (bgIsDark) 1f else hsl[2]
    var result = this
    repeat(16) {
        val mid = (lo + hi) / 2f
        val candidateHsl = hsl.copyOf()
        candidateHsl[2] = mid
        val candidateArgb = ColorUtils.HSLToColor(candidateHsl)
        if (ColorUtils.calculateContrast(candidateArgb, bgArgb) >= minRatio) {
            result = Color(candidateArgb)
            // This lightness clears the bar — search back towards the original
            // hue/lightness for the *least* adjustment that still passes.
            if (bgIsDark) hi = mid else lo = mid
        } else {
            if (bgIsDark) lo = mid else hi = mid
        }
    }
    return result
}
