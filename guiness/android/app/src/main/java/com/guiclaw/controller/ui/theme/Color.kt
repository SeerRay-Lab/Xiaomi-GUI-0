package com.guiness.controller.ui.theme

import androidx.compose.ui.graphics.Color

// Brand primary — inherited from launcher background #1B1F3B (midnight indigo)
val BrandIndigo = Color(0xFF1E293B)
val BrandIndigoContainer = Color(0xFFDEE4F2)
val BrandAccent = Color(0xFF6366F1)       // electric indigo
val BrandAccentContainer = Color(0xFFE0E7FF)

// Semantic state colors (used for status chips)
val StateRunning = Color(0xFF22C55E)       // green — server running / ok
val StateRunningContainer = Color(0xFFDCFCE7)
val StateWarning = Color(0xFFF59E0B)       // amber — partial / missing permission
val StateWarningContainer = Color(0xFFFEF3C7)
val StateError = Color(0xFFEF4444)         // red — error / stopped
val StateErrorContainer = Color(0xFFFEE2E2)

// Neutral slate scale
val Slate50 = Color(0xFFF8FAFC)
val Slate100 = Color(0xFFF1F5F9)
val Slate200 = Color(0xFFE2E8F0)
val Slate300 = Color(0xFFCBD5E1)
val Slate400 = Color(0xFF94A3B8)
val Slate500 = Color(0xFF64748B)
val Slate600 = Color(0xFF475569)
val Slate700 = Color(0xFF334155)
val Slate800 = Color(0xFF1E293B)
val Slate900 = Color(0xFF0F172A)
val Slate950 = Color(0xFF020617)

// Dark-mode tonal variants (OLED friendly)
val DarkBg = Color(0xFF0B1220)
val DarkSurface = Color(0xFF111827)
val DarkSurfaceVariant = Color(0xFF1F2937)
val DarkOutline = Color(0xFF374151)

// Log-level semantic colors (usable in both themes)
val LogInfo = Color(0xFF3B82F6)
val LogWarn = Color(0xFFF59E0B)
val LogError = Color(0xFFEF4444)
