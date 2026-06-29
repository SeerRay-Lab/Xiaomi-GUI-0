package com.guiness.controller.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

enum class StatusTone { OK, Warning, Error, Neutral }

/**
 * Dot + label chip. Replaces the emoji-based status indicators that used to sit in StatusScreen.
 * Meets the "no emoji icons" + "color-not-only" rules: the label text always states the meaning.
 */
@Composable
fun StatusChip(
    label: String,
    tone: StatusTone,
    modifier: Modifier = Modifier,
) {
    val (container, content, dot) = when (tone) {
        StatusTone.OK -> Triple(
            MaterialTheme.colorScheme.tertiaryContainer,
            MaterialTheme.colorScheme.onTertiaryContainer,
            MaterialTheme.colorScheme.tertiary,
        )
        StatusTone.Warning -> Triple(
            Color(0xFFFEF3C7).copy(alpha = if (isDark()) 0.2f else 1f),
            if (isDark()) Color(0xFFFDE68A) else Color(0xFF92400E),
            Color(0xFFF59E0B),
        )
        StatusTone.Error -> Triple(
            MaterialTheme.colorScheme.errorContainer,
            MaterialTheme.colorScheme.onErrorContainer,
            MaterialTheme.colorScheme.error,
        )
        StatusTone.Neutral -> Triple(
            MaterialTheme.colorScheme.surfaceVariant,
            MaterialTheme.colorScheme.onSurfaceVariant,
            MaterialTheme.colorScheme.outline,
        )
    }

    Row(
        modifier = modifier
            .clip(RoundedCornerShape(100))
            .background(container)
            .padding(horizontal = 10.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Box(
            Modifier
                .size(8.dp)
                .clip(CircleShape)
                .background(dot),
        )
        Text(
            label,
            style = MaterialTheme.typography.labelMedium,
            color = content,
        )
    }
}

@Composable
private fun isDark(): Boolean {
    // Heuristic: background luminance. Avoids a dependency on isSystemInDarkTheme at the chip level
    // so previews and forced themes stay correct.
    val bg = MaterialTheme.colorScheme.background
    val luminance = (0.299 * bg.red + 0.587 * bg.green + 0.114 * bg.blue)
    return luminance < 0.5
}
