package com.runningcoach.app.ui.theme

import androidx.compose.ui.graphics.Color

// Brand palette: energetic green (Garmin/Strava-like, distinct).
val Primary = Color(0xFF1B7A3D)
val PrimaryDark = Color(0xFF0F5227)
val Accent = Color(0xFFFF6F00)

// Form-state colors used across cards and badges.
val FormFresh = Color(0xFF2E7D32)
val FormBalanced = Color(0xFF1565C0)
val FormFatigued = Color(0xFFC62828)
val FormDetraining = Color(0xFFF9A825)
val FormUnknown = Color(0xFF607D8B)

fun formColor(state: String): Color = when (state.lowercase()) {
    "fresh" -> FormFresh
    "balanced" -> FormBalanced
    "fatigued" -> FormFatigued
    "detraining" -> FormDetraining
    else -> FormUnknown
}
